"""
Endpoints
  POST /api/auth/register | /api/auth/login   -> {token, username, email, full_name, created_at}
  GET  /api/auth/me                           -> who am I (validates the token) + profile
  GET | PUT | DELETE /api/profile             -> v1.1: view / edit / delete my account
  POST /api/profile/password                  -> v1.1: change my password
  POST /api/repos/analyze                     -> starts a background job, returns {job_id}
  GET  /api/jobs                              -> v1.1: my running / failed analyses
  GET | DELETE /api/jobs/{job_id}             -> progress {status, percent, message, repo_id}  |  dismiss a failed one
  GET  /api/repos                             -> v1.1: my analysed repos (= saved documentation)
  GET | DELETE /api/repos/{repo_id}/doc|...   -> {name, markdown} (preview + download)  |  delete repo + docs
  POST /api/chat                              -> asks self-RAG, returns {answer}
"""
import re
import threading
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import auth
from backend import rag_engine
from backend import storage
from backend.doc_generator import build_retriever, generate_documentation, load_retriever
from backend.repo_analyzer import analyze_repo, parse_repo_url

app = FastAPI(title="RepoLens")
auth.init_db()          
storage.init_storage()  


RETRIEVERS = {}  


rag_lock = threading.Lock()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
class Credentials(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):          
    username: str
    password: str
    email: str
    full_name: str = ""

class ProfileUpdate(BaseModel):
    username: str
    email: str
    full_name: str = ""

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class DeleteAccount(BaseModel):
    password: str

class AnalyzeRequest(BaseModel):
    repo_url: str

class ChatRequest(BaseModel):
    repo_id: str
    question: str


def session_response(username: str):
    return {"token": auth.create_token(username), **auth.get_profile(username)}

def check_email(raw: str) -> str:
    email = raw.strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 120:
        raise HTTPException(400, "Enter a valid email address")
    return email

@app.post("/api/auth/register")
def register(c: RegisterRequest):
    username = c.username.strip().lower()
    if len(username) < 3 or len(c.password) < 6:
        raise HTTPException(400, "Username needs 3+ characters and password 6+ characters")
    email = check_email(c.email)
    if auth.email_taken(email):
        raise HTTPException(409, "That email is already registered")
    if not auth.create_user(username, c.password, email, c.full_name.strip()[:60]):
        raise HTTPException(409, "That username is taken")
    return session_response(username)

@app.post("/api/auth/login")
def login(c: Credentials):
    username = c.username.strip().lower()
    if not auth.check_user(username, c.password): 
        raise HTTPException(401, "Wrong username or password")
    return session_response(username)

@app.get("/api/auth/me")
def me(user: str = Depends(auth.current_user)):
    return auth.get_profile(user) 

@app.get("/api/profile")
def get_profile(user: str = Depends(auth.current_user)):
    profile = auth.get_profile(user)
    profile["repo_count"] = len(storage.list_repos(user))
    profile["active_jobs"] = sum(1 for j in storage.list_jobs(user) if j["status"] == "running")
    return profile

@app.put("/api/profile")
def update_profile(p: ProfileUpdate, user: str = Depends(auth.current_user)):
    new_username = p.username.strip().lower()
    if len(new_username) < 3 or len(new_username) > 30:
        raise HTTPException(400, "Username needs 3 to 30 characters")
    email = check_email(p.email)
    try:
        final = auth.update_profile(user, new_username, email, p.full_name.strip()[:60])
    except ValueError as e:                     
        raise HTTPException(409, str(e))
    return session_response(final)

@app.post("/api/profile/password")
def change_password(p: PasswordChange, user: str = Depends(auth.current_user)):
    if len(p.new_password) < 6:
        raise HTTPException(400, "New password needs 6+ characters")
    if not auth.check_user(user, p.current_password):
        raise HTTPException(403, "Current password is wrong")
    auth.set_password(user, p.new_password)
    return {"ok": True}

@app.delete("/api/profile")
def delete_account(p: DeleteAccount, user: str = Depends(auth.current_user)):
    if not auth.check_user(user, p.password):
        raise HTTPException(403, "Password is wrong")
    for r in storage.list_repos(user):           
        RETRIEVERS.pop(r["id"], None)
        storage.delete_repo(r["id"], user)
    auth.delete_user(user)                       
    return {"ok": True}


def run_job(job_id: str, repo_url: str):
    def progress(percent, message):
        storage.update_job(job_id, percent=percent, message=message)

    repo_id = None
    try:
        repo = analyze_repo(repo_url, lambda p, m: progress(int(p * 0.3), m))  # seperates config and code files, and returns a dict of owner, name, tree, files and config.
        
        docs = generate_documentation(repo, lambda p, m: progress(30 + int(p * 0.62), m))   # takes in info from repo, and then returns a dict, consisting of markdown(overview + section(per file info)), sections and overview, generated by giving config files and code to some llm
        
        progress(94, "Building the search index for the chatbot")
        repo_id = storage.new_id()
        retriever = build_retriever(docs["overview"], docs["sections"],
                                    save_dir=storage.index_path(repo_id))

        owner = storage.job_owner(job_id)
        if owner is None:                        
            storage.remove_index(repo_id)
            return
        storage.save_repo(repo_id, owner, f"{repo['owner']}/{repo['name']}", repo_url,
                          docs["markdown"], docs["overview"], docs["sections"])
        RETRIEVERS[repo_id] = retriever
        storage.update_job(job_id, status="done", percent=100, message="Done", repo_id=repo_id)
    except Exception as e:
        print(f"[job {job_id}] failed: {e}")
        if repo_id:
            storage.remove_index(repo_id)
        storage.update_job(job_id, status="error",
                           message=str(e) or "Something went wrong while analysing the repo")

@app.post("/api/repos/analyze")
def analyze(req: AnalyzeRequest, tasks: BackgroundTasks, user: str = Depends(auth.current_user)):
    try:
        owner, name = parse_repo_url(req.repo_url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    url = f"https://github.com/{owner}/{name}"
    existing = storage.find_running_job(user, url)
    if existing:
        return {"job_id": existing}
    job_id = storage.create_job(user, url)
    tasks.add_task(run_job, job_id, url)   
    return {"job_id": job_id}

@app.get("/api/jobs")
def list_jobs(user: str = Depends(auth.current_user)):
    return {"jobs": storage.list_jobs(user)}   # running + failed ones, newest first

@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, user: str = Depends(auth.current_user)):
    job = storage.get_job(job_id, user)
    if not job:                                # users can only see their own jobs
        raise HTTPException(404, "Analysis not found")
    return job

@app.delete("/api/jobs/{job_id}")
def dismiss_job(job_id: str, user: str = Depends(auth.current_user)):
    result = storage.delete_job(job_id, user)
    if result == "missing":
        raise HTTPException(404, "Analysis not found")
    if result == "running":
        raise HTTPException(409, "This analysis is still running")
    return {"ok": True}



def get_repo(repo_id: str, user: str):
    repo = storage.get_repo(repo_id, user)
    if not repo:
        raise HTTPException(404, "Repository not found. It may have been deleted.")
    return repo

def get_retriever(repo_id: str, repo: dict):
    """Cached retriever, else load the FAISS index from disk, else rebuild it from the saved docs."""
    retriever = RETRIEVERS.get(repo_id)
    if retriever is None:
        path = storage.index_path(repo_id)
        try:
            retriever = load_retriever(path)
        except Exception as e:                   # folder missing or damaged
            print(f"[chat] index for {repo_id} could not be loaded ({e}); rebuilding it")
            retriever = build_retriever(repo["overview"], repo["sections"], save_dir=path)
        RETRIEVERS[repo_id] = retriever
    return retriever

@app.get("/api/repos")
def list_repos(user: str = Depends(auth.current_user)):
    return {"repos": storage.list_repos(user)}

@app.get("/api/repos/{repo_id}/doc")
def get_doc(repo_id: str, user: str = Depends(auth.current_user)):
    repo = get_repo(repo_id, user)
    return {"name": repo["name"], "markdown": repo["markdown"],
            "url": repo["url"], "created_at": repo["created_at"]}

@app.delete("/api/repos/{repo_id}")
def delete_repo(repo_id: str, user: str = Depends(auth.current_user)):
    if not storage.delete_repo(repo_id, user):      # only succeeds for the owner
        raise HTTPException(404, "Repository not found")
    RETRIEVERS.pop(repo_id, None)                   # drop the cached retriever only AFTER the ownership check
    return {"ok": True}

@app.post("/api/chat")
def chat(req: ChatRequest, user: str = Depends(auth.current_user)):
    repo = get_repo(req.repo_id, user)
    question = req.question.strip()
    if not question:
        raise HTTPException(400, "Type a question first")
    try:
        retriever = get_retriever(req.repo_id, repo)
        with rag_lock:
            rag_engine.retriever = retriever      
            state = rag_engine.self_rag.invoke(
                {"question": question, "retry_count_support": 0, "retry_count_use": 0},
                config={"recursion_limit": 60},
            )
        answer = state.get("generated_answer") or "I couldn't find this in the documentation."
    except Exception as e:
        print(f"[chat] self-RAG failed: {e}")
        raise HTTPException(500, "The assistant hit an error. Please try again.")
    return {"answer": answer}



FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
else:
    print("[RepoLens] frontend/dist not found. Run `npm run build` in /frontend, or use `npm run dev`.")

if __name__ == "__main__":      # lets you also start it with:  python main.py
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000)
