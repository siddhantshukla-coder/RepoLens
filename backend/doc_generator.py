
import time

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

import rag_engine              # re-use YOUR llm + embedding model (loaded only once)
from repo_analyzer import describe, describe_notebook

MAX_SRC_CHARS = 10000               # cap source sent per file (keeps us under token limits)

# ---- prompts used for WRITING the documentation (not the chatbot prompts) -----
FILE_PROMPT = """You are a senior engineer writing precise developer documentation.
You will receive ONE source file from a repository, plus a static-analysis summary
produced by Tree-sitter (imports, classes, functions, call lists, assigned variables
and control-flow counts).

Write Markdown documentation for this file using exactly these sections:
### Purpose
### How it fits in the project
### Walkthrough
Explain EVERY class and function: what it does, its inputs and outputs, its logic
step by step, and the reason behind any non-obvious decision.
### Data flow
How values move between functions and variables in this file.
### Dependencies and side effects
Imports, files, network calls, global state, environment variables.

Rules: describe only what the code actually shows and never invent behaviour. Use the
real names from the code. Keep code snippets short. Start directly with the sections
(no preamble) and do not repeat the file path as a heading."""

# v1.3: used for Jupyter notebooks instead of FILE_PROMPT. A notebook is a story (load data ->
# clean -> model -> evaluate), so the section analyses that workflow and its saved results
# rather than just walking through functions.
NOTEBOOK_PROMPT = """You are a senior data scientist writing an ANALYSIS of a Jupyter notebook for a developer
who has not opened it. You will receive: notebook statistics (cell counts, execution health,
data files, saved files), a Tree-sitter summary of its code (imports, functions, control flow),
and the notebook converted to text. In that text, cells are separated by '# %%' lines, markdown
cells are written as comments, and lines starting with '# [output]' are the saved results of the
cell above them. Long notebooks are shortened: '# ... more lines' marks cut code.

Write Markdown with exactly these sections:
### Purpose and summary
What problem the notebook tackles and what it concludes, in 3 to 5 sentences.
### Workflow
The notebook as an ordered pipeline. Group consecutive cells into stages (for example setup,
data loading, cleaning, feature engineering, modelling, evaluation, visualisation). For each
stage give the cell numbers it covers ('cells 3-7') and what happens there.
### Data
Datasets and files that are loaded (names and paths as written), their shape or columns when an
output shows them, and how the data is transformed.
### Methods and models
Algorithms, libraries and key parameters. Explain every function the notebook defines: inputs,
outputs and logic.
### Results
Metrics, numbers, tables and plots reported in the saved outputs, quoted exactly as shown.
Say so clearly when a cell has no saved output.
### Quality and reproducibility
Base this ONLY on the statistics and the code: cells never run, out-of-order execution, error
outputs, a missing random seed, hard-coded paths, packages installed inside the notebook, or
anything else that would stop someone re-running it and getting the same results.
### How to run
The dependencies and steps the notebook itself shows.

Rules: never invent numbers, results or behaviour. If something is not visible, say that it is
not visible. Refer to cells as 'cell N'. Start directly with the sections (no preamble) and do
not repeat the file path as a heading."""

OVERVIEW_PROMPT = """You are a senior engineer writing the top-level documentation of a repository.
You will receive its file tree, its README/config files, and a short summary of every
documented file. Write Markdown with these sections:
# <project name>
## What this project does
## Tech stack
## Architecture
How the main parts interact. Mention the real files involved.
## Project structure
An annotated list of the important files and folders.
## Notebooks
Only if the repository contains Jupyter notebooks: one or two lines per notebook with its goal and its key result.
## How to run
Only include this if the README or config files support it.

Rules: never invent features or commands that are not supported by the input."""


def ask_llm(system: str, human: str, retries: int = 3):
    for attempt in range(retries):
        try:
            out = rag_engine.llm.invoke([("system", system), ("human", human)])
            return out.content if isinstance(out.content, str) else str(out.content)
        except Exception as e:
            print(f"[doc_generator] LLM call failed (attempt {attempt + 1}/{retries}): {e}")
            time.sleep(8 * (attempt + 1))
    return None


def generate_documentation(repo: dict, progress) -> dict:
    """
    `repo` comes from repo_analyzer.analyze_repo().

    """
    files = repo["files"]
    sections = []

    # ---- 1) one documentation section per file --------------------------------
    for i, f in enumerate(files):
        progress(int(90 * i / (len(files) + 1)), f"Documenting {f['path']} ({i + 1}/{len(files)})")
        analysis = describe(f["analysis"])
        src = f["source"][:MAX_SRC_CHARS]
        if len(f["source"]) > MAX_SRC_CHARS:
            src += "\n... [file truncated]"
        if f.get("notebook"):
            human = (
                f"File: {f['path']} (Jupyter notebook)\n\n"
                f"## Notebook statistics\n{describe_notebook(f['notebook'])}\n\n"
                f"## Static analysis (Tree-sitter; line numbers refer to the converted text)\n{analysis}\n\n"
                f"## Notebook converted to text\n```{f['lang']}\n{src}\n```"
            )
            body = ask_llm(NOTEBOOK_PROMPT, human)
        else:
            human = (
                f"File: {f['path']}\nLanguage: {f['lang']}\n\n"
                f"## Static analysis (Tree-sitter)\n{analysis}\n\n"
                f"## Source code\n```{f['lang']}\n{src}\n```"
            )
            body = ask_llm(FILE_PROMPT, human)
        if body is None:
            # LLM failed even after retries: still keep the file in the docs
            # using the raw analysis so the final document is never incomplete.
            body = "_Automatic explanation unavailable. Static analysis:_\n\n" + analysis
        sections.append((f["path"], body))

    # ---- 2) the project-level overview ---------------------------------------
    progress(92, "Writing the project overview")
    tree_text = "\n".join(repo["tree"][:300])
    config_text = "\n\n".join(f"### {c['path']}\n{c['source'][:1500]}" for c in repo["configs"])
    summaries = "\n".join(f"- {p}: {b[:300].replace(chr(10), ' ')}" for p, b in sections)
    human = (
        f"Repository: {repo['owner']}/{repo['name']}\n\n"
        f"## File tree\n{tree_text}\n\n## Config files\n{config_text or '(none)'}\n\n"
        f"## Documented files\n{summaries}"
    )
    overview = ask_llm(OVERVIEW_PROMPT, human) or f"# {repo['name']}\n\n_Overview unavailable._"

    # ---- 3) stitch everything into one Markdown document ----------------------
    body = "\n\n".join(f"## `{p}`\n\n{b}" for p, b in sections)
    markdown = f"{overview}\n\n---\n\n# File-by-file reference\n\n{body}\n"
    progress(100, "Documentation ready")
    return {"markdown": markdown, "overview": overview, "sections": sections}


def build_retriever(overview: str, sections: list, save_dir: str = None):
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    docs = []
    for chunk in splitter.split_text(overview):
        docs.append(Document(page_content=f"[Project overview]\n{chunk}", metadata={"file": "overview"}))
    for path, body in sections:
        for chunk in splitter.split_text(body):
            docs.append(Document(page_content=f"[File: {path}]\n{chunk}", metadata={"file": path}))

    vector_store = FAISS.from_documents(docs, rag_engine.embedding)
    if save_dir:
        vector_store.save_local(save_dir)
    return vector_store.as_retriever(search_type="similarity", search_kwargs={"k": 4})


def load_retriever(save_dir: str):
    vector_store = FAISS.load_local(save_dir, rag_engine.embedding, allow_dangerous_deserialization=True)
    return vector_store.as_retriever(search_type="similarity", search_kwargs={"k": 4})
