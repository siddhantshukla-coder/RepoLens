
import json
import os
import re

import requests
from dotenv import load_dotenv
from tree_sitter_language_pack import get_parser

load_dotenv()

GITHUB_API = "https://api.github.com"
RAW_URL = "https://raw.githubusercontent.com"

# Optional token: raises GitHub's rate limit and lets you read YOUR private repos.
HEADERS = {"Accept": "application/vnd.github+json"}
if os.getenv("GITHUB_TOKEN"):
    HEADERS["Authorization"] = f"Bearer {os.getenv('GITHUB_TOKEN')}"

# ---- limits: keep the LLM bill / rate-limit under control ------------------
MAX_FILES = 30            # at most this many source files get documented
MAX_CONFIGS = 5           # extra README / config files, used only for the overview
MAX_FILE_BYTES = 80_000   
MAX_NOTEBOOK_BYTES = 5_000_000

# file extension -> Tree-sitter language name
CODE_EXT = {
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "tsx", ".java": "java", ".go": "go",
    ".rs": "rust", ".c": "c", ".cpp": "cpp", ".rb": "ruby",
    ".ipynb": "python",  
}
CONFIG_FILES = {
    "README.md", "package.json", "requirements.txt", "pyproject.toml",
    "Dockerfile", "docker-compose.yml", "Makefile", "go.mod", "Cargo.toml", "pom.xml",
}
SKIP_DIRS = {
    "node_modules", ".git", "dist", "build", "venv", ".venv", "__pycache__",
    "vendor", ".next", "target", "out", "coverage", ".ipynb_checkpoints",
}


FUNC = {"function_definition", "function_declaration", "method_definition",
        "method_declaration", "function_item", "arrow_function", "function_expression"}
CLASS = {"class_definition", "class_declaration", "struct_item", "impl_item",
         "interface_declaration", "class"}
BRANCH = {"if_statement", "switch_statement", "match_statement", "try_statement",
          "if_expression", "match_expression", "conditional_expression", "if", "case"}
LOOP = {"for_statement", "while_statement", "for_in_statement", "do_statement",
        "enhanced_for_statement", "for_expression", "while_expression", "for_range_loop"}
CALL = {"call", "call_expression", "method_invocation"}
RETURN = {"return_statement"}
ASSIGN = {"assignment", "assignment_expression", "variable_declarator",
          "short_var_declaration", "let_declaration"}
IMPORT = {"import_statement", "import_from_statement", "import_declaration",
          "use_declaration", "preproc_include"}

def parse_repo_url(url: str):
    """'https://github.com/owner/repo(.git)' -> ('owner', 'repo')"""
    m = re.match(r"https?://github\.com/([^/\s]+)/([^/\s#?]+)", url.strip())
    if not m:
        raise ValueError("Enter a valid GitHub URL, like https://github.com/owner/repo")
    return m.group(1), m.group(2).removesuffix(".git")


def list_repo_files(owner: str, repo: str):
    r = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}", headers=HEADERS, timeout=20)
    if r.status_code == 404:
        raise ValueError("Repository not found. It may be private or the URL is wrong.")
    if r.status_code in (403, 429):
        raise ValueError("GitHub rate limit hit. Add GITHUB_TOKEN to .env and retry.")
    r.raise_for_status()
    branch = r.json()["default_branch"]

    t = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/{branch}?recursive=1",
        headers=HEADERS, timeout=30,
    )
    t.raise_for_status()
    return branch, [x for x in t.json()["tree"] if x["type"] == "blob"]


def select_files(files):
    code, configs = [], []
    for f in files:
        parts = f["path"].split("/")
        name = parts[-1]
        ext = os.path.splitext(name)[1].lower()
        if any(p in SKIP_DIRS for p in parts[:-1]):
            continue                                   # inside node_modules, build, etc.
        limit = MAX_NOTEBOOK_BYTES if ext == ".ipynb" else MAX_FILE_BYTES
        if f.get("size", 0) > limit or name.endswith(".min.js"):
            continue
        if ext in CODE_EXT:
            code.append(f)
        elif name in CONFIG_FILES and len(parts) <= 2:  # only root-level configs
            configs.append(f)
    # sort key: non-tests first, then fewer folders deep, then larger files first
    code.sort(key=lambda f: ("test" in f["path"].lower(), f["path"].count("/"), -f.get("size", 0)))
    return code[:MAX_FILES], configs[:MAX_CONFIGS]


def fetch_file(owner, repo, branch, path):
    try:
        r = requests.get(f"{RAW_URL}/{owner}/{repo}/{branch}/{path}", headers=HEADERS, timeout=20)
        return r.text if r.status_code == 200 else None
    except requests.RequestException:
        return None


# ---- Jupyter notebooks (.ipynb) ---------------------------------------------
# A notebook is a JSON file, so Tree-sitter can't read it directly. We turn it into a plain
# script in the common "# %%" cell format: markdown cells become comments, code cells stay
# code, and a short piece of each cell's printed output is kept as a comment (so the
# documentation can say what a cell produced). Images and HTML are dropped.
def _notebook_outputs(outputs, limit=400):
    parts = []
    for o in outputs:
        kind = o.get("output_type")
        if kind == "stream":                                   # print(...) output
            text = o.get("text", "")
        elif kind in ("execute_result", "display_data"):       # last expression / displayed value
            text = o.get("data", {}).get("text/plain", "")
        elif kind == "error":
            text = f"{o.get('ename', 'Error')}: {o.get('evalue', '')}"
        else:
            continue
        parts.append("".join(text) if isinstance(text, list) else str(text))
    text = "\n".join(parts).strip()
    return text[:limit] + (" ...[truncated]" if len(text) > limit else "")


# JSON text -> notebook dict, or None if it isn't a valid nbformat-4 notebook.
def _load_notebook(raw: str):
    try:
        nb = json.loads(raw)
        return nb if isinstance(nb["cells"], list) else None
    except (ValueError, KeyError, TypeError):
        return None


def _cell_source(cell) -> str:
    source = cell.get("source", "")
    return "".join(source) if isinstance(source, list) else str(source)


def notebook_to_text(nb: dict, level: int = 0) -> str:
   
    cells = nb["cells"]
    # level 0 = the full text. Higher levels are used for LONG notebooks: each code cell is cut
    # to fewer lines and each output to fewer characters (see NOTEBOOK_LEVELS), so the WHOLE
    # notebook still fits in the LLM prompt instead of its ending being chopped off.
    max_lines, out_limit = NOTEBOOK_LEVELS[level]
    lines = [
        "# Jupyter notebook converted to plain text for analysis.",
        "# Cells are separated by '# %%' lines. Markdown cells are written as comments.",
        "# Lines starting with '# [output]' are the saved results of the cell above them.",
        "",
    ]
    for i, cell in enumerate(cells, 1):
        source = _cell_source(cell)
        kind = cell.get("cell_type")
        if kind == "markdown":
            lines.append(f"# %% [markdown] cell {i}")
            lines += ["# " + ln for ln in source.splitlines()]
        elif kind == "code":
            lines.append(f"# %% [code] cell {i}")
            code_lines = source.splitlines()
            for ln in code_lines[:max_lines]:
                # IPython magics (%matplotlib inline, !pip install ...) are not valid Python,
                # so comment them out to keep the Tree-sitter parse clean.
                lines.append("# [magic] " + ln if ln.lstrip().startswith(("%", "!")) else ln)
            if len(code_lines) > max_lines:
                lines.append(f"# ... ({len(code_lines) - max_lines} more lines in this cell)")
            out = _notebook_outputs(cell.get("outputs", []), out_limit)
            if out:
                lines += ["# [output] " + ln for ln in out.splitlines() if ln.strip()]
        else:
            continue                                           # raw cells etc.
        lines.append("")
    return "\n".join(lines)


# ---- notebook ANALYSIS (v1.3): facts the LLM can't reliably count by itself --------
NOTEBOOK_CHAR_BUDGET = 10_000   # keep in step with MAX_SRC_CHARS in doc_generator.py
# (max lines kept per code cell, max characters kept per output), from full text to most shortened
NOTEBOOK_LEVELS = [(10_000, 400), (15, 200), (6, 100)]

# data a notebook reads / writes, found with simple patterns, e.g.  pd.read_csv("train.csv")
_READS = re.compile(r"""\b(?:read_csv|read_excel|read_parquet|read_json|read_table|read_sql|load_dataset|loadtxt|imread|open|load)\(\s*f?['"]([^'"]+)['"]""")
_WRITES = re.compile(r"""\b(?:to_csv|to_excel|to_parquet|to_pickle|savefig|save|dump|save_model)\(\s*f?['"]([^'"]+)['"]""")
_SEED = re.compile(r"random_state|\.seed\(|manual_seed|set_seed")
_INSTALL = re.compile(r"^\s*[!%]\s*(?:pip|conda)\s+install", re.M)


def notebook_stats(nb: dict) -> dict:
    """Cell counts, execution health, data files, ... computed from the notebook JSON."""
    cells = nb["cells"]
    code = [c for c in cells if c.get("cell_type") == "code"]
    counts = [c["execution_count"] for c in code if c.get("execution_count") is not None]
    errors, images = [], 0
    for c in code:
        for o in c.get("outputs", []):
            if o.get("output_type") == "error":
                errors.append(f"{o.get('ename', 'Error')}: {str(o.get('evalue', ''))[:80]}")
            data = o.get("data", {}) if o.get("output_type") in ("execute_result", "display_data") else {}
            if any(k.startswith("image/") for k in data):        # a plot / picture was saved here
                images += 1
    code_text = "\n".join(_cell_source(c) for c in code)
    meta = nb.get("metadata") or {}
    language = (meta.get("language_info") or {}).get("name") or (meta.get("kernelspec") or {}).get("language") or "python"
    return {
        "cells": len(cells),
        "code_cells": len(code),
        "markdown_cells": sum(1 for c in cells if c.get("cell_type") == "markdown"),
        "language": str(language),
        "executed_code_cells": len(counts),
        "unexecuted_code_cells": sum(1 for c in code if c.get("execution_count") is None and _cell_source(c).strip()),
        "out_of_order": counts != sorted(counts),               # executed in a different order than written
        "error_outputs": errors[:5],
        "image_outputs": images,
        "data_files": list(dict.fromkeys(_READS.findall(code_text)))[:10],
        "saved_files": list(dict.fromkeys(_WRITES.findall(code_text)))[:10],
        "sets_random_seed": bool(_SEED.search(code_text)),
        "installs_packages": bool(_INSTALL.search(code_text)),
    }


def describe_notebook(s: dict) -> str:
    """Notebook statistics as compact text for the LLM (like describe() does for code)."""
    yes_no = lambda b: "yes" if b else "no"
    return "\n".join([
        f"Cells: {s['cells']} ({s['code_cells']} code, {s['markdown_cells']} markdown). Language: {s['language']}.",
        f"Execution: {s['executed_code_cells']} code cells have a saved run number, "
        f"{s['unexecuted_code_cells']} non-empty code cells were never run; cells run out of order: {yes_no(s['out_of_order'])}.",
        f"Saved outputs: {s['image_outputs']} plot/image outputs (the images themselves are not shown); "
        f"error outputs: {'; '.join(s['error_outputs']) or 'none'}.",
        f"Data files read: {', '.join(s['data_files']) or 'none found'}.",
        f"Files written: {', '.join(s['saved_files']) or 'none found'}.",
        f"Random seed set: {yes_no(s['sets_random_seed'])}. Installs packages inside the notebook: {yes_no(s['installs_packages'])}.",
    ])


def analyze_notebook(raw: str):
    """
    Returns None for an invalid notebook, otherwise a dict with
      text      - what the LLM reads (the compact version if the notebook is long)
      full_text - the complete converted script (Tree-sitter analyses THIS one, so no function is cut)
      stats     - notebook facts from notebook_stats()
    """
    nb = _load_notebook(raw)
    if nb is None:
        return None
    full = notebook_to_text(nb)
    text = full
    for level in range(1, len(NOTEBOOK_LEVELS)):           # still too long? shorten step by step
        if len(text) <= NOTEBOOK_CHAR_BUDGET:
            break
        text = notebook_to_text(nb, level)
    return {"text": text, "full_text": full, "stats": notebook_stats(nb)}


#tree sitter analysis of a single file
def _text(node, src: bytes) -> str:
    return src[node.start_byte:node.end_byte].decode("utf8", "ignore")


def _name_of(node, src):
    """Function/class name. Arrow functions get their name from `const x = () => ...`."""
    n = node.child_by_field_name("name")
    if n is None and node.parent is not None and node.parent.type == "variable_declarator":
        n = node.parent.child_by_field_name("name")
    return _text(n, src) if n is not None else "<anonymous>"


def _summarize_function(fn, src):
    """Walk everything inside ONE function and collect its control/data-flow facts."""
    branches = loops = returns = 0
    calls, assigns = [], []
    stack = [fn]                      
    while stack:
        n = stack.pop()
        t = n.type
        if t in BRANCH:
            branches += 1
        elif t in LOOP:
            loops += 1
        elif t in RETURN:
            returns += 1
        elif t in CALL:             
            callee = n.child_by_field_name("function") or n.child_by_field_name("name")
            if callee is not None:
                calls.append(_text(callee, src)[:60])
        elif t in ASSIGN:            
            left = n.child_by_field_name("left") or n.child_by_field_name("name")
            if left is not None:
                assigns.append(_text(left, src)[:40])
        stack.extend(n.children)
    params = fn.child_by_field_name("parameters")
    return {
        "name": _name_of(fn, src),
        "params": _text(params, src)[:120] if params is not None else "()",
        "line": fn.start_point[0] + 1,
        "end_line": fn.end_point[0] + 1,
        "branches": branches, "loops": loops, "returns": returns,
        "calls": list(dict.fromkeys(calls))[:20],      # dedupe, keep order, cap size
        "assigns": list(dict.fromkeys(assigns))[:15],
    }


def analyze_code(source: str, lang: str) -> dict:
    try:
        parser = get_parser(lang)
        src = source.encode("utf8")
        tree = parser.parse(src)      # <- this is the CST
    except Exception as e:
        print(f"[tree-sitter] could not parse ({lang}): {e}")
        return {"parsed": False}

    imports, classes, functions = [], [], []
    stack = [tree.root_node]
    while stack:
        n = stack.pop()
        if n.type in IMPORT:
            imports.append(_text(n, src).splitlines()[0][:120])
        elif n.type in CLASS:
            classes.append({"name": _name_of(n, src), "line": n.start_point[0] + 1})
        elif n.type in FUNC:
            functions.append(_summarize_function(n, src))
        stack.extend(reversed(n.children)) 
    return {"parsed": True, "imports": imports, "classes": classes, "functions": functions}


def describe(a: dict) -> str:
    if not a.get("parsed"):
        return "(No structural analysis available for this file.)"
    lines = []
    if a["imports"]:
        lines.append("Imports: " + "; ".join(a["imports"][:25]))
    if a["classes"]:
        lines.append("Classes: " + ", ".join(f"{c['name']} (line {c['line']})" for c in a["classes"]))
    for f in a["functions"]:
        lines.append(
            f"- {f['name']}{f['params']} lines {f['line']}-{f['end_line']} | "
            f"control flow: {f['branches']} branches, {f['loops']} loops, {f['returns']} returns | "
            f"calls: {', '.join(f['calls']) or 'none'} | "
            f"variables assigned: {', '.join(f['assigns']) or 'none'}"
        )
    return "\n".join(lines) or "(no functions or classes found)"


def analyze_repo(repo_url: str, progress) -> dict:
    owner, name = parse_repo_url(repo_url)
    progress(2, f"Contacting GitHub for {owner}/{name}")
    branch, all_files = list_repo_files(owner, name)
    code, configs = select_files(all_files)
    if not code:
        raise ValueError("No supported source files found (Python, Jupyter notebooks, JS/TS, Java, Go, Rust, C/C++, Ruby).")

    files = []
    total = len(code) + len(configs)
    for i, f in enumerate(code):
        progress(5 + int(90 * i / total), f"Reading and parsing {f['path']}")
        src = fetch_file(owner, name, branch, f["path"])
        if src is None:
            continue                                   # skip files that failed to download
        ext = os.path.splitext(f["path"])[1].lower()
        lang = CODE_EXT[ext]
        if ext == ".ipynb":
            nb = analyze_notebook(src)                 # JSON -> script text + notebook statistics
            if nb is None:
                continue                               # not a valid notebook: skip it
            files.append({
                "path": f["path"], "lang": nb["stats"]["language"].lower(), "source": nb["text"],
                "analysis": analyze_code(nb["full_text"], nb["stats"]["language"].lower()),
                "notebook": nb["stats"],                # its presence tells doc_generator.py to write a notebook analysis
            })
            continue
        files.append({"path": f["path"], "lang": lang, "source": src,
                      "analysis": analyze_code(src, lang)})

    config_files = []
    for j, f in enumerate(configs):
        progress(5 + int(90 * (len(code) + j) / total), f"Reading {f['path']}")
        src = fetch_file(owner, name, branch, f["path"])
        if src:
            config_files.append({"path": f["path"], "source": src})

    progress(100, "Repository parsed")
    return {
        "owner": owner, "name": name, "branch": branch,
        "tree": [f["path"] for f in all_files if not any(p in SKIP_DIRS for p in f["path"].split("/"))],
        "files": files, "configs": config_files,
    }
