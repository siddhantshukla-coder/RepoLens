"""
auth.py  -  JWT authentication for RepoLens

How it works:
  1. A user registers / logs in with a username + password.
  2. Passwords are NEVER stored as plain text - only a bcrypt hash goes into SQLite.
  3. On success the server returns a JWT: a signed token saying
     "this is <username>, valid until <time>".
  4. The browser sends it on every request as the header:
         Authorization: Bearer <token>
  5. `current_user` (bottom of this file) verifies the signature + expiry on
     every protected route. Nobody can forge a token without JWT_SECRET.
"""
import os
import sqlite3
import time
from contextlib import contextmanager

import bcrypt
import jwt  
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

load_dotenv()  

SECRET = os.getenv("JWT_SECRET")
if not SECRET:
    raise RuntimeError("Set JWT_SECRET in backend/.env (any long random string).")

ALGORITHM = "HS256"                    
TOKEN_LIFETIME_SECONDS = 8 * 60 * 60   
DB_PATH = os.path.join(os.path.dirname(__file__), "users.db")


@contextmanager
def db():
    con = sqlite3.connect(DB_PATH, timeout=30)   
    con.row_factory = sqlite3.Row # with this you can access values with column names instead 0 based indexing
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit() # permanently saves values after execution
    except Exception:
        con.rollback() # reverses all uncommitted changes in the current transaction.
        raise
    finally:
        con.close() 


def init_db():
    with db() as con:
        con.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "username TEXT PRIMARY KEY, "
            "pw_hash BLOB NOT NULL, "  
            "email TEXT, "
            "full_name TEXT NOT NULL DEFAULT '', "
            "created_at INTEGER)"
        )
        
        have = {row["name"] for row in con.execute("PRAGMA table_info(users)")}
        if "email" not in have:
            con.execute("ALTER TABLE users ADD COLUMN email TEXT")
        if "full_name" not in have:
            con.execute("ALTER TABLE users ADD COLUMN full_name TEXT NOT NULL DEFAULT ''")
        if "created_at" not in have:
            con.execute("ALTER TABLE users ADD COLUMN created_at INTEGER")
        con.execute("UPDATE users SET created_at=? WHERE created_at IS NULL", (int(time.time()),))
        con.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email)")


def _prep(password: str) -> bytes: # user sets the password
    # bcrypt only looks at the first 72 bytes of a password, so we cut there
    # explicitly (newer bcrypt versions raise an error otherwise).
    return password.encode("utf-8")[:72]


def create_user(username: str, password: str, email: str = "", full_name: str = "") -> bool:
    """Returns False if the username (or email) is already taken."""
    hashed = bcrypt.hashpw(_prep(password), bcrypt.gensalt())  # bcrypt.gensalt generates a random data and adds it to the password to prevent formation of similar hashing for the same password
    try:
        with db() as con:
            con.execute(
                "INSERT INTO users (username, pw_hash, email, full_name, created_at) VALUES (?, ?, ?, ?, ?)",
                (username, hashed, email or None, full_name, int(time.time())),
            )
        return True
    except sqlite3.IntegrityError:  # PRIMARY KEY / UNIQUE clash -> user exists
        return False


def check_user(username: str, password: str) -> bool:
    """True only if the username exists AND the password matches the stored hash."""
    with db() as con:
        row = con.execute(
            "SELECT pw_hash FROM users WHERE username = ?", (username,)
        ).fetchone() # fetches one row with the same username, and then returns true if that username exists and password matches
    return bool(row) and bcrypt.checkpw(_prep(password), row[0])


def user_exists(username: str) -> bool:
    with db() as con:
        return con.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone() is not None


def email_taken(email: str) -> bool:
    with db() as con:
        return con.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone() is not None


def get_profile(username: str):
    with db() as con:
        row = con.execute(
            "SELECT username, email, full_name, created_at FROM users WHERE username = ?", (username,)
        ).fetchone()
    return dict(row) if row else None


def update_profile(username: str, new_username: str, email: str, full_name: str) -> str:
    with db() as con:
        if new_username != username and con.execute(
            "SELECT 1 FROM users WHERE username = ?", (new_username,)
        ).fetchone():
            raise ValueError("That username is taken")
        if email and con.execute(
            "SELECT 1 FROM users WHERE email = ? AND username <> ?", (email, username)
        ).fetchone():
            raise ValueError("That email is already registered")
        con.execute(
            "UPDATE users SET username = ?, email = ?, full_name = ? WHERE username = ?",
            (new_username, email or None, full_name, username),
        )
    return new_username


def set_password(username: str, new_password: str):
    hashed = bcrypt.hashpw(_prep(new_password), bcrypt.gensalt())
    with db() as con:
        con.execute("UPDATE users SET pw_hash = ? WHERE username = ?", (hashed, username))


def delete_user(username: str):
    with db() as con:
        con.execute("DELETE FROM users WHERE username = ?", (username,))


# ----------------------------------------------------------------------------
# JWT creation + verification
# ----------------------------------------------------------------------------
def create_token(username: str) -> str:
    now = int(time.time())
    payload = {
        "sub": username,                       # "subject" = who this token is for
        "iat": now,                            # issued at
        "exp": now + TOKEN_LIFETIME_SECONDS,   # expiry (PyJWT enforces it for us)
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


# auto_error=False lets us return a clean 401 ourselves when the header is missing
_bearer = HTTPBearer(auto_error=False) # auto error prevents 403 HTTP error when it does not find the bearer jwt token


def current_user(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> str: # creds has the datatype of HTTPAuthCrendentials and it depends on the _bearer. 
    if creds is None:
        raise HTTPException(401, "Not logged in")
    try:
        data = jwt.decode(creds.credentials, SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Session expired, please log in again")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")
    # v1.1: a perfectly valid token can still belong to an account that was deleted
    # or renamed since it was issued, so make sure the user is really there.
    if not user_exists(data["sub"]):
        raise HTTPException(401, "Account not found, please log in again")
    return data["sub"] # returns the username whose session is currently ongoing
