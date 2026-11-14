
import json
import os
import shutil
import time
import uuid

from backend.auth import db   

INDEX_DIR = os.path.join(os.path.dirname(__file__), "data", "indexes")

SCHEMA = """
CREATE TABLE IF NOT EXISTS repos (
    id         TEXT PRIMARY KEY,
    username   TEXT NOT NULL REFERENCES users(username) ON UPDATE CASCADE ON DELETE CASCADE,
    name       TEXT NOT NULL,                 -- "owner/repo"
    url        TEXT NOT NULL,                 -- canonical https://github.com/owner/repo
    markdown   TEXT NOT NULL,                 -- the full generated documentation
    overview   TEXT NOT NULL DEFAULT '',      -- kept so the index can be rebuilt if its folder is lost
    sections   TEXT NOT NULL DEFAULT '[]',    -- JSON list of [file_path, documentation_text]
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id         TEXT PRIMARY KEY,
    username   TEXT NOT NULL REFERENCES users(username) ON UPDATE CASCADE ON DELETE CASCADE,
    repo_url   TEXT NOT NULL,
    status     TEXT NOT NULL,                 -- running | done | error
    percent    INTEGER NOT NULL DEFAULT 0,
    message    TEXT NOT NULL DEFAULT '',
    repo_id    TEXT,                          -- filled in when the job is done
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_repos_user ON repos(username, created_at);
CREATE INDEX IF NOT EXISTS idx_jobs_user  ON jobs(username, created_at);
"""


def init_storage():
    """Create the tables on first run and clean up after a restart."""
    os.makedirs(INDEX_DIR, exist_ok=True)
    with db() as con:
        # WAL lets the background analysis write progress while other requests read.
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(SCHEMA)
        # A job still marked "running" at startup was killed by the restart (its thread
        # died with the old process), so show it as failed instead of "running" forever.
        con.execute(
            "UPDATE jobs SET status='error', updated_at=?, "
            "message='The server restarted while this analysis was running. Please analyse the repo again.' "
            "WHERE status='running'",
            (int(time.time()),),
        )


def new_id() -> str:
    return uuid.uuid4().hex


# ----------------------------------------------------------------------------
# Search-index folders (FAISS)
# ----------------------------------------------------------------------------
def index_path(repo_id: str) -> str:
    # basename() = belt and braces: a repo id can never point outside INDEX_DIR
    return os.path.join(INDEX_DIR, os.path.basename(repo_id))


def remove_index(repo_id: str):
    shutil.rmtree(index_path(repo_id), ignore_errors=True)


# ----------------------------------------------------------------------------
# Jobs
# ----------------------------------------------------------------------------
JOB_COLUMNS = "id, repo_url, status, percent, message, repo_id, created_at, updated_at"


def create_job(user: str, repo_url: str) -> str:
    job_id, now = new_id(), int(time.time())
    with db() as con:
        con.execute(
            "INSERT INTO jobs (id, username, repo_url, status, percent, message, created_at, updated_at) "
            "VALUES (?, ?, ?, 'running', 0, 'Starting', ?, ?)",
            (job_id, user, repo_url, now, now),
        )
    return job_id


def update_job(job_id: str, **fields):
    """update_job(id, percent=40, message='...', status='done', repo_id='...')"""
    allowed = {"status", "percent", "message", "repo_id"}      # whitelist = no SQL injection via keys
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    fields["updated_at"] = int(time.time())
    sets = ", ".join(f"{k}=?" for k in fields)
    with db() as con:
        con.execute(f"UPDATE jobs SET {sets} WHERE id=?", (*fields.values(), job_id))


def get_job(job_id: str, user: str):
    with db() as con:
        row = con.execute(
            f"SELECT {JOB_COLUMNS} FROM jobs WHERE id=? AND username=?", (job_id, user)
        ).fetchone()
    return dict(row) if row else None


def job_owner(job_id: str):
    """Who owns this job RIGHT NOW (the username can change while a job runs). None if gone."""
    with db() as con:
        row = con.execute("SELECT username FROM jobs WHERE id=?", (job_id,)).fetchone()
    return row["username"] if row else None


def list_jobs(user: str):
    """Jobs that still need the user's attention: running or failed (finished ones became repos)."""
    with db() as con:
        rows = con.execute(
            f"SELECT {JOB_COLUMNS} FROM jobs WHERE username=? AND status!='done' ORDER BY created_at DESC",
            (user,),
        ).fetchall()
    return [dict(r) for r in rows]


def find_running_job(user: str, repo_url: str):
    """If this user is already analysing this URL, return that job's id (no duplicate runs)."""
    with db() as con:
        row = con.execute(
            "SELECT id FROM jobs WHERE username=? AND repo_url=? AND status='running'", (user, repo_url)
        ).fetchone()
    return row["id"] if row else None


def delete_job(job_id: str, user: str) -> str:
    """Returns 'deleted', 'missing' or 'running' (a running job can't be removed)."""
    with db() as con:
        row = con.execute("SELECT status FROM jobs WHERE id=? AND username=?", (job_id, user)).fetchone()
        if row is None:
            return "missing"
        if row["status"] == "running":
            return "running"
        con.execute("DELETE FROM jobs WHERE id=?", (job_id,))
    return "deleted"


# ----------------------------------------------------------------------------
# Repos (= saved documentation + its chat index)
# ----------------------------------------------------------------------------
def save_repo(repo_id, user, name, url, markdown, overview, sections):
    with db() as con:
        con.execute(
            "INSERT INTO repos (id, username, name, url, markdown, overview, sections, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (repo_id, user, name, url, markdown, overview, json.dumps(sections), int(time.time())),
        )


def list_repos(user: str):
    """Light list for the UI (no Markdown body). doc_chars = size of the documentation."""
    with db() as con:
        rows = con.execute(
            "SELECT id, name, url, created_at, length(markdown) AS doc_chars "
            "FROM repos WHERE username=? ORDER BY created_at DESC",
            (user,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_repo(repo_id: str, user: str):
    """Full row (including markdown + sections) or None if it isn't this user's."""
    with db() as con:
        row = con.execute("SELECT * FROM repos WHERE id=? AND username=?", (repo_id, user)).fetchone()
    if row is None:
        return None
    repo = dict(row)
    repo["sections"] = json.loads(repo["sections"])
    return repo


def delete_repo(repo_id: str, user: str) -> bool:
    with db() as con:
        cur = con.execute("DELETE FROM repos WHERE id=? AND username=?", (repo_id, user))
        if cur.rowcount == 0:
            return False
        con.execute("DELETE FROM jobs WHERE repo_id=?", (repo_id,))   # drop the job that made it
    remove_index(repo_id)                                             # and its FAISS folder
    return True
