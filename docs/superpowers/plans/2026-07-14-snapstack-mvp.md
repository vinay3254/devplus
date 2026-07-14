# SnapStack MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working SnapStack v1 — a browser extension that captures highlighted text into a Flask/Ollama/FAISS backend, plus a Vite/React dashboard for semantic search and SM-2 spaced-repetition review.

**Architecture:** Flask backend (SQLite + FAISS + Ollama, blueprint-per-concern) exposes a JWT-protected REST API. A Vite+React dashboard and a Manifest V3 browser extension both consume that API. Backend, dashboard, and extension are built and independently testable in that order — each layer is runnable/verifiable before the next depends on it.

**Tech Stack:** Python 3 / Flask / SQLite / FAISS (faiss-cpu) / PyJWT / Ollama (local) for the backend; Vite + React for the dashboard; vanilla JS Manifest V3 for the extension.

## Global Constraints

- LLM/embeddings: Ollama only for v1 — no cloud provider fallback (spec: "Ollama Only for v1").
- Auth: single-user JWT, no public register endpoint — the one user account is created via a one-time local script, not an API route.
- Deployment: local-only — backend binds to localhost, not exposed to LAN/internet in v1.
- Backend tests: standalone `test_*.py` scripts at `backend/` root, plain `assert` statements, run individually via `python test_x.py` — **not** pytest-discovered, matching this project's own convention.
- Backend dependencies install into an isolated `backend/.venv` (created via `python -m venv .venv`), never into the global Python environment. All `python`/`pip` commands in this plan assume that venv is activated, or use its interpreter directly (e.g. `.venv/Scripts/python.exe` on Windows).
- Dashboard: Vite + React, no test runner — verified via dev server + manual exercise, matching `chatbot-ui-vite/` convention.
- Extension: Manifest V3, Chrome + Firefox — no automated tests, manual checklist verification only.
- No offline queueing or automatic retry anywhere in v1 (extension capture failures and Ollama summarization failures both surface an error/manual-retry path instead).

---

## File Structure

```
devplus/
  backend/
    app.py                        # Flask app factory, blueprint registration, startup check
    config.py                     # env-driven settings
    database.py                   # SQLite connection + schema
    requirements.txt
    .env.example
    .gitignore                    # data/, .env, __pycache__
    services/
      __init__.py
      auth.py                     # JWT issuance, require_auth decorator, /api/auth/login
      ollama_client.py            # summarize_and_tag(), embed() — Ollama HTTP wrappers
      search_index.py             # FAISS IndexIDMap wrapper: add/search/rebuild
      capture_service.py          # save_snap(), /api/snaps POST, retry-summary
      search_service.py           # /api/snaps GET/search, /api/snaps/<id> GET
      review_service.py           # sm2(), /api/review/due, /api/review/<id>/grade
    scripts/
      create_user.py              # one-time local user setup
    data/                         # gitignored: snapstack.db, snapstack.faiss
    test_ollama_client.py
    test_auth.py
    test_capture_service.py
    test_search_service.py
    test_review_service.py
  extension/
    manifest.json
    background.js                 # context menu + capture POST + notifications
    icon128.png
    popup/
      popup.html
      popup.js
      popup.css
  dashboard/                       # Vite + React app (scaffolded)
    .env
    src/
      main.jsx
      App.jsx
      api.js
      pages/
        Login.jsx
        Snaps.jsx
        Review.jsx
      components/
        SnapCard.jsx
  docs/superpowers/specs/2026-07-14-snapstack-design.md   # (already written)
  docs/superpowers/plans/2026-07-14-snapstack-mvp.md      # this file
```

---

### Task 1: Backend scaffold — config, schema, app skeleton

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/config.py`
- Create: `backend/database.py`
- Create: `backend/app.py`
- Create: `backend/.env.example`
- Create: `backend/.gitignore`

**Interfaces:**
- Produces: `config.OLLAMA_API_URL, config.OLLAMA_MODEL, config.OLLAMA_EMBED_MODEL, config.JWT_SECRET, config.DB_PATH, config.FAISS_INDEX_PATH, config.EMBEDDING_DIM, config.PORT`; `database.get_connection(db_path) -> sqlite3.Connection`, `database.init_db(db_path) -> None`; `app.create_app() -> Flask`.

- [ ] **Step 1: Create `backend/requirements.txt`**

```
Flask==3.0.3
flask-cors==4.0.1
PyJWT==2.8.0
requests==2.32.3
faiss-cpu==1.14.3
numpy==2.4.6
python-dotenv==1.0.1
```

(`faiss-cpu`/`numpy` versions pinned to whatever has a prebuilt wheel for your Python version — bump if `pip install` reports no matching distribution.)

- [ ] **Step 2: Create `backend/config.py`**

```python
import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3:8b")
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-secret-change-me")
DB_PATH = os.getenv(
    "DB_PATH", os.path.join(os.path.dirname(__file__), "data", "snapstack.db")
)
FAISS_INDEX_PATH = os.getenv(
    "FAISS_INDEX_PATH", os.path.join(os.path.dirname(__file__), "data", "snapstack.faiss")
)
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))
PORT = int(os.getenv("PORT", "5100"))
```

- [ ] **Step 3: Create `backend/database.py`**

```python
import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS snaps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT NOT NULL,
    title TEXT,
    raw_text TEXT NOT NULL,
    summary TEXT,
    category TEXT,
    tags TEXT,
    created_at TEXT NOT NULL,
    interval INTEGER NOT NULL DEFAULT 0,
    repetitions INTEGER NOT NULL DEFAULT 0,
    easiness_factor REAL NOT NULL DEFAULT 2.5,
    due_date TEXT NOT NULL
);
"""


def get_connection(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path):
    conn = get_connection(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
```

- [ ] **Step 4: Create `backend/app.py`**

```python
from flask import Flask, jsonify
from flask_cors import CORS

import config
from database import init_db


def create_app():
    app = Flask(__name__)
    # Wildcard CORS: local-only single-user tool, extension origin
    # (chrome-extension://<id>) varies per install so can't be pinned in advance.
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    init_db(config.DB_PATH)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(port=config.PORT, debug=True)
```

- [ ] **Step 5: Create `backend/.env.example`**

```
OLLAMA_API_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:8b
OLLAMA_EMBED_MODEL=nomic-embed-text
JWT_SECRET=change-me-to-a-random-string
PORT=5100
```

- [ ] **Step 6: Create `backend/.gitignore`**

```
data/
.env
__pycache__/
*.pyc
.venv/
```

- [ ] **Step 7: Verify the app boots**

```bash
cd backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install --upgrade pip
./.venv/Scripts/python.exe -m pip install -r requirements.txt
cp .env.example .env
./.venv/Scripts/python.exe app.py
```

In another terminal:

```bash
curl http://localhost:5100/api/health
```

Expected: `{"status":"ok"}`. Stop the server (Ctrl+C).

- [ ] **Step 8: Commit**

```bash
cd backend
git add requirements.txt config.py database.py app.py .env.example .gitignore
git commit -m "feat: scaffold backend with config, SQLite schema, Flask skeleton"
```

---

### Task 2: Ollama client helper

**Files:**
- Create: `backend/services/__init__.py`
- Create: `backend/services/ollama_client.py`
- Test: `backend/test_ollama_client.py`

**Interfaces:**
- Consumes: `config.OLLAMA_API_URL`, `config.OLLAMA_MODEL`, `config.OLLAMA_EMBED_MODEL`.
- Produces: `ollama_client.OllamaError(Exception)`; `ollama_client.summarize_and_tag(text, api_url, model) -> (summary: str|None, category: str|None, tags: list[str])`; `ollama_client.embed(text, api_url, model) -> list[float]`.

- [ ] **Step 1: Write the failing test**

Create `backend/services/__init__.py` (empty file).

Create `backend/test_ollama_client.py`:

```python
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from services.ollama_client import _parse_summary_response


def test_parse_summary_response_extracts_all_fields():
    raw = "SUMMARY: A short summary.\nCATEGORY: dsa\nTAGS: arrays, sorting, search"
    summary, category, tags = _parse_summary_response(raw)
    assert summary == "A short summary."
    assert category == "dsa"
    assert tags == ["arrays", "sorting", "search"]
    print("PASS: parses summary/category/tags from well-formed response")


def test_parse_summary_response_handles_missing_fields():
    raw = "SUMMARY: Only a summary, nothing else."
    summary, category, tags = _parse_summary_response(raw)
    assert summary == "Only a summary, nothing else."
    assert category is None
    assert tags == []
    print("PASS: missing CATEGORY/TAGS lines default to None/[]")


if __name__ == "__main__":
    test_parse_summary_response_extracts_all_fields()
    test_parse_summary_response_handles_missing_fields()
    print("All ollama_client tests passed.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python test_ollama_client.py`
Expected: `ModuleNotFoundError: No module named 'services.ollama_client'`

- [ ] **Step 3: Implement `backend/services/ollama_client.py`**

```python
import requests


class OllamaError(Exception):
    pass


def summarize_and_tag(text, api_url, model):
    prompt = (
        "Summarize the following text in 1-2 sentences, then suggest one "
        "category (a single word) and up to 3 tags (comma-separated, lowercase). "
        "Respond in exactly this format:\n"
        "SUMMARY: <summary>\n"
        "CATEGORY: <category>\n"
        "TAGS: <tag1, tag2, tag3>\n\n"
        f"TEXT:\n{text}"
    )
    try:
        resp = requests.post(
            f"{api_url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise OllamaError(str(e))

    raw = resp.json().get("response", "")
    return _parse_summary_response(raw)


def _parse_summary_response(raw):
    summary, category, tags = None, None, []
    for line in raw.splitlines():
        line = line.strip()
        if line.upper().startswith("SUMMARY:"):
            summary = line.split(":", 1)[1].strip()
        elif line.upper().startswith("CATEGORY:"):
            category = line.split(":", 1)[1].strip()
        elif line.upper().startswith("TAGS:"):
            tags = [t.strip() for t in line.split(":", 1)[1].split(",") if t.strip()]
    return summary, category, tags


def embed(text, api_url, model):
    try:
        resp = requests.post(
            f"{api_url}/api/embeddings",
            json={"model": model, "prompt": text},
            timeout=30,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise OllamaError(str(e))
    return resp.json()["embedding"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python test_ollama_client.py`
Expected: `All ollama_client tests passed.`

- [ ] **Step 5: Commit**

```bash
cd backend
git add services/__init__.py services/ollama_client.py test_ollama_client.py
git commit -m "feat: add Ollama client for summarization/tagging and embeddings"
```

---

### Task 3: Auth service

**Files:**
- Create: `backend/services/auth.py`
- Create: `backend/scripts/create_user.py`
- Modify: `backend/app.py` (register auth blueprint)
- Test: `backend/test_auth.py`

**Interfaces:**
- Consumes: `config.JWT_SECRET`, `config.DB_PATH`, `database.get_connection`.
- Produces: `auth.create_token(username) -> str`; `auth.verify_token(token) -> dict`; `auth.require_auth` (decorator, returns 401 JSON on missing/expired/invalid token); `auth.bp` (Flask Blueprint exposing `POST /api/auth/login`).

- [ ] **Step 1: Write the failing test**

Create `backend/test_auth.py`:

```python
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

import config
config.DB_PATH = tempfile.mktemp(suffix=".db")

from flask import Flask, jsonify
from database import init_db, get_connection
from werkzeug.security import generate_password_hash
from services.auth import require_auth, create_token
from app import create_app


def make_protected_test_app():
    app = Flask(__name__)

    @app.route("/protected")
    @require_auth
    def protected():
        return jsonify({"ok": True})

    return app


def seed_user():
    init_db(config.DB_PATH)
    conn = get_connection(config.DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO users (username, password_hash) VALUES (?, ?)",
        ("testuser", generate_password_hash("testpass")),
    )
    conn.commit()
    conn.close()


def test_protected_route_rejects_missing_token():
    app = make_protected_test_app()
    client = app.test_client()
    resp = client.get("/protected")
    assert resp.status_code == 401
    print("PASS: missing token rejected")


def test_protected_route_accepts_valid_token():
    app = make_protected_test_app()
    client = app.test_client()
    token = create_token("testuser")
    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    print("PASS: valid token accepted")


def test_login_returns_token_for_valid_credentials():
    seed_user()
    app = create_app()
    client = app.test_client()
    resp = client.post(
        "/api/auth/login", json={"username": "testuser", "password": "testpass"}
    )
    assert resp.status_code == 200
    assert "token" in resp.get_json()
    print("PASS: valid login returns token")


def test_login_rejects_invalid_password():
    seed_user()
    app = create_app()
    client = app.test_client()
    resp = client.post(
        "/api/auth/login", json={"username": "testuser", "password": "wrong"}
    )
    assert resp.status_code == 401
    print("PASS: invalid password rejected")


if __name__ == "__main__":
    test_protected_route_rejects_missing_token()
    test_protected_route_accepts_valid_token()
    test_login_returns_token_for_valid_credentials()
    test_login_rejects_invalid_password()
    print("All auth tests passed.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python test_auth.py`
Expected: `ModuleNotFoundError: No module named 'services.auth'`

- [ ] **Step 3: Implement `backend/services/auth.py`**

```python
import datetime
from functools import wraps

import jwt
from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash

import config
from database import get_connection

bp = Blueprint("auth", __name__)


def create_token(username):
    payload = {
        "username": username,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=30),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def verify_token(token):
    return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])


def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "missing or invalid Authorization header"}), 401
        token = auth_header.split(" ", 1)[1]
        try:
            verify_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "invalid token"}), 401
        return f(*args, **kwargs)

    return wrapper


@bp.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(force=True) or {}
    username = data.get("username", "")
    password = data.get("password", "")

    conn = get_connection(config.DB_PATH)
    row = conn.execute(
        "SELECT username, password_hash FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()

    if row is None or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "invalid username or password"}), 401

    token = create_token(row["username"])
    return jsonify({"token": token})
```

- [ ] **Step 4: Create `backend/scripts/create_user.py`**

```python
import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from database import get_connection, init_db
from werkzeug.security import generate_password_hash


def main():
    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")

    init_db(config.DB_PATH)
    conn = get_connection(config.DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO users (username, password_hash) VALUES (?, ?)",
        (username, generate_password_hash(password)),
    )
    conn.commit()
    conn.close()
    print(f"User '{username}' created.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Modify `backend/app.py`** to register the auth blueprint

Replace the `create_app` function with:

```python
def create_app():
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    init_db(config.DB_PATH)

    from services.auth import bp as auth_bp
    app.register_blueprint(auth_bp)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && python test_auth.py`
Expected: `All auth tests passed.`

- [ ] **Step 7: Commit**

```bash
cd backend
git add services/auth.py scripts/create_user.py app.py test_auth.py
git commit -m "feat: add JWT auth, login endpoint, and user setup script"
```

---

### Task 4: Capture service + FAISS write path

**Files:**
- Create: `backend/services/search_index.py`
- Create: `backend/services/capture_service.py`
- Modify: `backend/app.py` (register capture blueprint)
- Test: `backend/test_capture_service.py`

**Interfaces:**
- Consumes: `services.auth.require_auth`; `services.ollama_client.summarize_and_tag`, `embed`, `OllamaError`; `config.EMBEDDING_DIM, FAISS_INDEX_PATH`.
- Produces: `search_index.add(snap_id: int, vector: list[float]) -> None`; `search_index.search(vector, k=10) -> list[(id, distance)]`; `search_index.rebuild_from_rows(rows: list[(id, vector)]) -> None`; `search_index.count() -> int`; `capture_service.save_snap(url, title, raw_text) -> snap_id: int`; `capture_service.bp` exposing `POST /api/snaps` and `POST /api/snaps/<id>/retry-summary`.

- [ ] **Step 1: Write the failing test**

Create `backend/test_capture_service.py`:

```python
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

import config
config.DB_PATH = tempfile.mktemp(suffix=".db")
config.FAISS_INDEX_PATH = tempfile.mktemp(suffix=".faiss")

from database import init_db, get_connection
from services.ollama_client import OllamaError
import services.capture_service as capture_service


def setup():
    init_db(config.DB_PATH)


def test_save_snap_stores_summary_when_ollama_succeeds():
    setup()
    with patch(
        "services.capture_service.summarize_and_tag",
        return_value=("a summary", "tech", ["ai", "notes"]),
    ), patch(
        "services.capture_service.embed", return_value=[0.1] * config.EMBEDDING_DIM
    ), patch(
        "services.capture_service.search_index"
    ) as mock_search_index:
        snap_id = capture_service.save_snap("http://x.com", "Title", "some raw text")

    conn = get_connection(config.DB_PATH)
    row = conn.execute("SELECT * FROM snaps WHERE id = ?", (snap_id,)).fetchone()
    conn.close()

    assert row["summary"] == "a summary"
    assert row["category"] == "tech"
    assert row["tags"] == "ai,notes"
    mock_search_index.add.assert_called_once()
    print("PASS: successful summarization stores summary/category/tags and indexes")


def test_save_snap_falls_back_to_raw_text_when_ollama_fails():
    setup()
    with patch(
        "services.capture_service.summarize_and_tag",
        side_effect=OllamaError("unreachable"),
    ), patch("services.capture_service.search_index") as mock_search_index:
        snap_id = capture_service.save_snap("http://x.com", "Title", "some raw text")

    conn = get_connection(config.DB_PATH)
    row = conn.execute("SELECT * FROM snaps WHERE id = ?", (snap_id,)).fetchone()
    conn.close()

    assert row["raw_text"] == "some raw text"
    assert row["summary"] is None
    assert row["category"] is None
    mock_search_index.add.assert_not_called()
    print("PASS: Ollama failure still saves raw text without summary, skips indexing")


if __name__ == "__main__":
    test_save_snap_stores_summary_when_ollama_succeeds()
    test_save_snap_falls_back_to_raw_text_when_ollama_fails()
    print("All capture_service tests passed.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python test_capture_service.py`
Expected: `ModuleNotFoundError: No module named 'services.capture_service'`

- [ ] **Step 3: Implement `backend/services/search_index.py`**

```python
import os
import threading

import faiss
import numpy as np

import config

_lock = threading.Lock()
_index = None


def _load():
    global _index
    if _index is not None:
        return _index
    if os.path.exists(config.FAISS_INDEX_PATH):
        _index = faiss.read_index(config.FAISS_INDEX_PATH)
    else:
        _index = faiss.IndexIDMap(faiss.IndexFlatL2(config.EMBEDDING_DIM))
    return _index


def add(snap_id, vector):
    with _lock:
        index = _load()
        vec = np.array([vector], dtype="float32")
        ids = np.array([snap_id], dtype="int64")
        index.remove_ids(ids)
        index.add_with_ids(vec, ids)
        os.makedirs(os.path.dirname(config.FAISS_INDEX_PATH), exist_ok=True)
        faiss.write_index(index, config.FAISS_INDEX_PATH)


def search(vector, k=10):
    with _lock:
        index = _load()
        if index.ntotal == 0:
            return []
        vec = np.array([vector], dtype="float32")
        distances, ids = index.search(vec, min(k, index.ntotal))
        return [(int(i), float(d)) for i, d in zip(ids[0], distances[0]) if i != -1]


def rebuild_from_rows(rows):
    """rows: list of (snap_id, vector). Used for startup consistency check."""
    global _index
    with _lock:
        new_index = faiss.IndexIDMap(faiss.IndexFlatL2(config.EMBEDDING_DIM))
        if rows:
            ids = np.array([r[0] for r in rows], dtype="int64")
            vecs = np.array([r[1] for r in rows], dtype="float32")
            new_index.add_with_ids(vecs, ids)
        _index = new_index
        os.makedirs(os.path.dirname(config.FAISS_INDEX_PATH), exist_ok=True)
        faiss.write_index(_index, config.FAISS_INDEX_PATH)


def count():
    with _lock:
        return _load().ntotal
```

- [ ] **Step 4: Implement `backend/services/capture_service.py`**

```python
import datetime

from flask import Blueprint, request, jsonify

import config
from database import get_connection
from services.auth import require_auth
from services.ollama_client import summarize_and_tag, embed, OllamaError
from services import search_index

bp = Blueprint("capture", __name__)


def _now_iso():
    return datetime.datetime.utcnow().isoformat()


def save_snap(url, title, raw_text):
    summary, category, tags = None, None, []
    try:
        summary, category, tags = summarize_and_tag(
            raw_text, config.OLLAMA_API_URL, config.OLLAMA_MODEL
        )
    except OllamaError:
        pass

    now = _now_iso()
    conn = get_connection(config.DB_PATH)
    cursor = conn.execute(
        """
        INSERT INTO snaps (url, title, raw_text, summary, category, tags, created_at, due_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (url, title, raw_text, summary, category, ",".join(tags), now, now),
    )
    snap_id = cursor.lastrowid
    conn.commit()
    conn.close()

    if summary is not None:
        _index_snap(snap_id, raw_text)

    return snap_id


def _index_snap(snap_id, raw_text):
    try:
        vector = embed(raw_text, config.OLLAMA_API_URL, config.OLLAMA_EMBED_MODEL)
        search_index.add(snap_id, vector)
    except OllamaError:
        pass


@bp.route("/api/snaps", methods=["POST"])
@require_auth
def create_snap():
    data = request.get_json(force=True) or {}
    url = data.get("url", "")
    title = data.get("title", "")
    raw_text = data.get("text", "")
    if not raw_text.strip():
        return jsonify({"error": "text is required"}), 400

    snap_id = save_snap(url, title, raw_text)
    return jsonify({"id": snap_id}), 201


@bp.route("/api/snaps/<int:snap_id>/retry-summary", methods=["POST"])
@require_auth
def retry_summary(snap_id):
    conn = get_connection(config.DB_PATH)
    row = conn.execute("SELECT raw_text FROM snaps WHERE id = ?", (snap_id,)).fetchone()
    if row is None:
        conn.close()
        return jsonify({"error": "not found"}), 404

    try:
        summary, category, tags = summarize_and_tag(
            row["raw_text"], config.OLLAMA_API_URL, config.OLLAMA_MODEL
        )
    except OllamaError:
        conn.close()
        return jsonify({"error": "summarization still failing"}), 502

    conn.execute(
        "UPDATE snaps SET summary = ?, category = ?, tags = ? WHERE id = ?",
        (summary, category, ",".join(tags), snap_id),
    )
    conn.commit()
    conn.close()
    _index_snap(snap_id, row["raw_text"])
    return jsonify({"status": "updated"})
```

- [ ] **Step 5: Modify `backend/app.py`** to register the capture blueprint

Replace the `create_app` function with:

```python
def create_app():
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    init_db(config.DB_PATH)

    from services.auth import bp as auth_bp
    from services.capture_service import bp as capture_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(capture_bp)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app
```

- [ ] **Step 6: Run test to verify it passes**

Run: `cd backend && python test_capture_service.py`
Expected: `All capture_service tests passed.`

- [ ] **Step 7: Commit**

```bash
cd backend
git add services/search_index.py services/capture_service.py app.py test_capture_service.py
git commit -m "feat: add capture service with FAISS indexing and summarization fallback"
```

---

### Task 5: List & search endpoints + startup consistency check

**Files:**
- Create: `backend/services/search_service.py`
- Modify: `backend/app.py` (register snaps blueprint, add startup consistency check)
- Test: `backend/test_search_service.py`

**Interfaces:**
- Consumes: `services.auth.require_auth`; `services.ollama_client.embed, OllamaError`; `services.search_index.search, count, rebuild_from_rows`.
- Produces: `search_service.bp` exposing `GET /api/snaps`, `GET /api/snaps/<id>`, `GET /api/snaps/search?q=`.

- [ ] **Step 1: Write the failing test**

Create `backend/test_search_service.py`:

```python
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(__file__))

import config
config.DB_PATH = tempfile.mktemp(suffix=".db")
config.FAISS_INDEX_PATH = tempfile.mktemp(suffix=".faiss")

from database import init_db, get_connection
from services.auth import create_token
from services.ollama_client import OllamaError
from app import create_app


def seed_snaps():
    init_db(config.DB_PATH)
    conn = get_connection(config.DB_PATH)
    conn.execute(
        "INSERT INTO snaps (id, url, title, raw_text, summary, category, tags, created_at, due_date) "
        "VALUES (1, 'http://a.com', 'Binary Search', 'binary search algorithm notes', "
        "'summary', 'dsa', 'algorithms,search', '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO snaps (id, url, title, raw_text, summary, category, tags, created_at, due_date) "
        "VALUES (2, 'http://b.com', 'React Hooks', 'react hooks explanation', "
        "'summary', 'frontend', 'react,hooks', '2026-01-02', '2026-01-02')"
    )
    conn.commit()
    conn.close()


def auth_headers():
    return {"Authorization": f"Bearer {create_token('testuser')}"}


def test_list_snaps_returns_all_rows():
    seed_snaps()
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/snaps", headers=auth_headers())
    assert resp.status_code == 200
    assert len(resp.get_json()) == 2
    print("PASS: list endpoint returns all snaps")


def test_semantic_search_ranks_and_filters_by_threshold():
    seed_snaps()
    app = create_app()
    client = app.test_client()

    with patch(
        "services.search_service.embed", return_value=[0.0] * config.EMBEDDING_DIM
    ), patch("services.search_service.search_index") as mock_index:
        mock_index.search.return_value = [(1, 0.1), (2, 0.9)]
        resp = client.get("/api/snaps/search?q=binary+search", headers=auth_headers())

    assert resp.status_code == 200
    results = resp.get_json()
    assert [r["id"] for r in results] == [1]
    print("PASS: semantic search ranks by FAISS order and filters by similarity threshold")


def test_search_falls_back_to_keyword_when_ollama_fails():
    seed_snaps()
    app = create_app()
    client = app.test_client()

    with patch("services.search_service.embed", side_effect=OllamaError("down")):
        resp = client.get("/api/snaps/search?q=React", headers=auth_headers())

    assert resp.status_code == 200
    results = resp.get_json()
    assert any(r["id"] == 2 for r in results)
    print("PASS: keyword fallback triggers when embedding fails")


if __name__ == "__main__":
    test_list_snaps_returns_all_rows()
    test_semantic_search_ranks_and_filters_by_threshold()
    test_search_falls_back_to_keyword_when_ollama_fails()
    print("All search_service tests passed.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python test_search_service.py`
Expected: `ModuleNotFoundError: No module named 'services.search_service'`

- [ ] **Step 3: Implement `backend/services/search_service.py`**

```python
from flask import Blueprint, request, jsonify

import config
from database import get_connection
from services.auth import require_auth
from services.ollama_client import embed, OllamaError
from services import search_index

bp = Blueprint("snaps", __name__)

# L2 distance threshold below which a FAISS hit counts as a semantic match.
SIMILARITY_THRESHOLD = 0.8


def _row_to_dict(row):
    return {
        "id": row["id"],
        "url": row["url"],
        "title": row["title"],
        "raw_text": row["raw_text"],
        "summary": row["summary"],
        "category": row["category"],
        "tags": row["tags"].split(",") if row["tags"] else [],
        "created_at": row["created_at"],
        "due_date": row["due_date"],
    }


@bp.route("/api/snaps", methods=["GET"])
@require_auth
def list_snaps():
    conn = get_connection(config.DB_PATH)
    rows = conn.execute("SELECT * FROM snaps ORDER BY created_at DESC").fetchall()
    conn.close()
    return jsonify([_row_to_dict(r) for r in rows])


@bp.route("/api/snaps/<int:snap_id>", methods=["GET"])
@require_auth
def get_snap(snap_id):
    conn = get_connection(config.DB_PATH)
    row = conn.execute("SELECT * FROM snaps WHERE id = ?", (snap_id,)).fetchone()
    conn.close()
    if row is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(_row_to_dict(row))


@bp.route("/api/snaps/search", methods=["GET"])
@require_auth
def search_snaps():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])

    conn = get_connection(config.DB_PATH)

    try:
        vector = embed(query, config.OLLAMA_API_URL, config.OLLAMA_EMBED_MODEL)
        hits = search_index.search(vector, k=20)
        matches = [snap_id for snap_id, distance in hits if distance <= SIMILARITY_THRESHOLD]
    except OllamaError:
        matches = []

    if matches:
        placeholders = ",".join("?" * len(matches))
        rows = conn.execute(
            f"SELECT * FROM snaps WHERE id IN ({placeholders})", matches
        ).fetchall()
        rows_by_id = {r["id"]: r for r in rows}
        ordered = [rows_by_id[i] for i in matches if i in rows_by_id]
    else:
        like = f"%{query}%"
        ordered = conn.execute(
            "SELECT * FROM snaps WHERE title LIKE ? OR tags LIKE ? OR category LIKE ? "
            "ORDER BY created_at DESC",
            (like, like, like),
        ).fetchall()

    conn.close()
    return jsonify([_row_to_dict(r) for r in ordered])
```

- [ ] **Step 4: Modify `backend/app.py`** to register the snaps blueprint and add the startup consistency check

Replace the full file with:

```python
from flask import Flask, jsonify
from flask_cors import CORS

import config
from database import init_db, get_connection


def create_app():
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    init_db(config.DB_PATH)

    from services.auth import bp as auth_bp
    from services.capture_service import bp as capture_bp
    from services.search_service import bp as snaps_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(capture_bp)
    app.register_blueprint(snaps_bp)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app


app = create_app()


def _startup_consistency_check():
    """Rebuild the FAISS index from SQLite if vector count drifts from row count.
    Only runs when launching the real server (python app.py) — not on import,
    so tests never trigger a live Ollama call."""
    from services import search_index
    from services.ollama_client import embed, OllamaError

    conn = get_connection(config.DB_PATH)
    summarized = conn.execute(
        "SELECT id, raw_text FROM snaps WHERE summary IS NOT NULL"
    ).fetchall()
    conn.close()

    if search_index.count() == len(summarized):
        return

    rows = []
    for row in summarized:
        try:
            vector = embed(row["raw_text"], config.OLLAMA_API_URL, config.OLLAMA_EMBED_MODEL)
            rows.append((row["id"], vector))
        except OllamaError:
            print(f"WARNING: could not re-embed snap {row['id']} during startup rebuild")
    search_index.rebuild_from_rows(rows)


if __name__ == "__main__":
    _startup_consistency_check()
    app.run(port=config.PORT, debug=True)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python test_search_service.py`
Expected: `All search_service tests passed.`

- [ ] **Step 6: Commit**

```bash
cd backend
git add services/search_service.py app.py test_search_service.py
git commit -m "feat: add list/search endpoints and FAISS startup consistency check"
```

---

### Task 6: Review service (SM-2 spaced repetition)

**Files:**
- Create: `backend/services/review_service.py`
- Modify: `backend/app.py` (register review blueprint)
- Test: `backend/test_review_service.py`

**Interfaces:**
- Consumes: `services.auth.require_auth`.
- Produces: `review_service.sm2(quality, repetitions, easiness_factor, interval) -> (repetitions, easiness_factor, interval)`; `review_service.bp` exposing `GET /api/review/due`, `POST /api/review/<id>/grade`.

- [ ] **Step 1: Write the failing test**

Create `backend/test_review_service.py`:

```python
import datetime
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

import config
config.DB_PATH = tempfile.mktemp(suffix=".db")
config.FAISS_INDEX_PATH = tempfile.mktemp(suffix=".faiss")

from database import init_db, get_connection
from services.auth import create_token
from services.review_service import sm2
from app import create_app


def test_sm2_good_grades_increase_interval_progressively():
    repetitions, ef, interval = 0, 2.5, 0
    repetitions, ef, interval = sm2(4, repetitions, ef, interval)  # "good"
    assert (repetitions, interval, ef) == (1, 1, 2.5)
    repetitions, ef, interval = sm2(4, repetitions, ef, interval)
    assert (repetitions, interval, ef) == (2, 6, 2.5)
    repetitions, ef, interval = sm2(4, repetitions, ef, interval)
    assert (repetitions, interval, ef) == (3, 15, 2.5)
    print("PASS: SM-2 good grades increase interval 1 -> 6 -> 15 days")


def test_sm2_again_resets_repetitions_and_interval():
    repetitions, ef, interval = sm2(0, 3, 2.5, 15)  # "again"
    assert repetitions == 0
    assert interval == 1
    print("PASS: SM-2 'again' grade resets repetitions and interval")


def seed_due_snap():
    init_db(config.DB_PATH)
    conn = get_connection(config.DB_PATH)
    yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    conn.execute(
        "INSERT INTO snaps (id, url, title, raw_text, summary, category, tags, "
        "created_at, due_date, interval, repetitions, easiness_factor) "
        "VALUES (1, 'http://a.com', 'T', 'text', 'sum', 'cat', 'tag', ?, ?, 0, 0, 2.5)",
        (yesterday, yesterday),
    )
    conn.commit()
    conn.close()


def auth_headers():
    return {"Authorization": f"Bearer {create_token('testuser')}"}


def test_due_endpoint_returns_overdue_snaps():
    seed_due_snap()
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/review/due", headers=auth_headers())
    assert resp.status_code == 200
    ids = [s["id"] for s in resp.get_json()]
    assert 1 in ids
    print("PASS: due endpoint returns overdue snaps")


def test_grade_endpoint_updates_due_date_forward():
    seed_due_snap()
    app = create_app()
    client = app.test_client()
    resp = client.post("/api/review/1/grade", json={"grade": "good"}, headers=auth_headers())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["repetitions"] == 1
    assert body["due_date"] > datetime.date.today().isoformat()
    print("PASS: grading updates due_date forward")


if __name__ == "__main__":
    test_sm2_good_grades_increase_interval_progressively()
    test_sm2_again_resets_repetitions_and_interval()
    test_due_endpoint_returns_overdue_snaps()
    test_grade_endpoint_updates_due_date_forward()
    print("All review_service tests passed.")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python test_review_service.py`
Expected: `ModuleNotFoundError: No module named 'services.review_service'`

- [ ] **Step 3: Implement `backend/services/review_service.py`**

```python
import datetime

from flask import Blueprint, request, jsonify

import config
from database import get_connection
from services.auth import require_auth

bp = Blueprint("review", __name__)

GRADE_TO_QUALITY = {"again": 0, "hard": 3, "good": 4, "easy": 5}


def sm2(quality, repetitions, easiness_factor, interval):
    if quality < 3:
        repetitions = 0
        interval = 1
    else:
        if repetitions == 0:
            interval = 1
        elif repetitions == 1:
            interval = 6
        else:
            interval = round(interval * easiness_factor)
        repetitions += 1

    easiness_factor = easiness_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    if easiness_factor < 1.3:
        easiness_factor = 1.3

    return repetitions, easiness_factor, interval


def _row_to_dict(row):
    return {
        "id": row["id"],
        "url": row["url"],
        "title": row["title"],
        "raw_text": row["raw_text"],
        "summary": row["summary"],
        "due_date": row["due_date"],
    }


@bp.route("/api/review/due", methods=["GET"])
@require_auth
def due_snaps():
    today = datetime.date.today().isoformat()
    conn = get_connection(config.DB_PATH)
    rows = conn.execute(
        "SELECT * FROM snaps WHERE due_date <= ? ORDER BY due_date ASC", (today,)
    ).fetchall()
    conn.close()
    return jsonify([_row_to_dict(r) for r in rows])


@bp.route("/api/review/<int:snap_id>/grade", methods=["POST"])
@require_auth
def grade_snap(snap_id):
    data = request.get_json(force=True) or {}
    grade = data.get("grade", "")
    if grade not in GRADE_TO_QUALITY:
        return jsonify({"error": "grade must be one of: again, hard, good, easy"}), 400

    conn = get_connection(config.DB_PATH)
    row = conn.execute("SELECT * FROM snaps WHERE id = ?", (snap_id,)).fetchone()
    if row is None:
        conn.close()
        return jsonify({"error": "not found"}), 404

    quality = GRADE_TO_QUALITY[grade]
    repetitions, easiness_factor, interval = sm2(
        quality, row["repetitions"], row["easiness_factor"], row["interval"]
    )
    due_date = (datetime.date.today() + datetime.timedelta(days=interval)).isoformat()

    conn.execute(
        "UPDATE snaps SET repetitions = ?, easiness_factor = ?, interval = ?, due_date = ? WHERE id = ?",
        (repetitions, easiness_factor, interval, due_date, snap_id),
    )
    conn.commit()
    conn.close()

    return jsonify(
        {
            "repetitions": repetitions,
            "easiness_factor": easiness_factor,
            "interval": interval,
            "due_date": due_date,
        }
    )
```

- [ ] **Step 4: Modify `backend/app.py`** to register the review blueprint

In `create_app`, add the import and registration:

```python
    from services.auth import bp as auth_bp
    from services.capture_service import bp as capture_bp
    from services.search_service import bp as snaps_bp
    from services.review_service import bp as review_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(capture_bp)
    app.register_blueprint(snaps_bp)
    app.register_blueprint(review_bp)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && python test_review_service.py`
Expected: `All review_service tests passed.`

- [ ] **Step 6: Run the full backend test suite**

```bash
cd backend
python test_ollama_client.py
python test_auth.py
python test_capture_service.py
python test_search_service.py
python test_review_service.py
```

Expected: all five print their "All ... tests passed." line with no assertion errors.

- [ ] **Step 7: Commit**

```bash
cd backend
git add services/review_service.py app.py test_review_service.py
git commit -m "feat: add SM-2 spaced-repetition review service"
```

---

### Task 7: Dashboard scaffold + login page

**Files:**
- Create: `dashboard/` (scaffolded via Vite)
- Create: `dashboard/.env`
- Create: `dashboard/src/api.js`
- Create: `dashboard/src/pages/Login.jsx`
- Modify: `dashboard/src/App.jsx`

**Interfaces:**
- Consumes: backend `POST /api/auth/login` (Task 3).
- Produces: `api.login(username, password) -> Promise<token>`; `api.logout()`; `api.isLoggedIn() -> bool`; localStorage key `snapstack_token`.

- [ ] **Step 1: Scaffold the Vite React app**

```bash
cd C:/Users/Admin/Desktop/devplus
npm create vite@latest dashboard -- --template react
cd dashboard
npm install
```

- [ ] **Step 2: Create `dashboard/.env`**

```
VITE_API_URL=http://localhost:5100
```

- [ ] **Step 3: Create `dashboard/src/api.js`**

```javascript
const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5100";

function authHeaders() {
  const token = localStorage.getItem("snapstack_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// Wraps fetch for authenticated calls: on a 401 (expired/invalid JWT), clears
// the stored token and reloads so App.jsx's isLoggedIn() check sends the user
// back to the login screen, per the spec's "JWT expired -> redirect to login".
async function authedFetch(url, options = {}) {
  const resp = await fetch(url, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  if (resp.status === 401) {
    localStorage.removeItem("snapstack_token");
    window.location.reload();
    throw new Error("Session expired");
  }
  return resp;
}

export async function login(username, password) {
  const resp = await fetch(`${API_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!resp.ok) {
    throw new Error("Invalid username or password");
  }
  const data = await resp.json();
  localStorage.setItem("snapstack_token", data.token);
  return data.token;
}

export function logout() {
  localStorage.removeItem("snapstack_token");
}

export function isLoggedIn() {
  return Boolean(localStorage.getItem("snapstack_token"));
}

export async function listSnaps() {
  const resp = await authedFetch(`${API_URL}/api/snaps`);
  if (!resp.ok) throw new Error("Failed to load snaps");
  return resp.json();
}

export async function searchSnaps(query) {
  const resp = await authedFetch(
    `${API_URL}/api/snaps/search?q=${encodeURIComponent(query)}`
  );
  if (!resp.ok) throw new Error("Search failed");
  return resp.json();
}

export async function retrySummary(snapId) {
  const resp = await authedFetch(`${API_URL}/api/snaps/${snapId}/retry-summary`, {
    method: "POST",
  });
  if (!resp.ok) throw new Error("Retry failed");
  return resp.json();
}

export async function getDueSnaps() {
  const resp = await authedFetch(`${API_URL}/api/review/due`);
  if (!resp.ok) throw new Error("Failed to load due snaps");
  return resp.json();
}

export async function gradeSnap(snapId, grade) {
  const resp = await authedFetch(`${API_URL}/api/review/${snapId}/grade`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ grade }),
  });
  if (!resp.ok) throw new Error("Grading failed");
  return resp.json();
}
```

- [ ] **Step 4: Create `dashboard/src/pages/Login.jsx`**

```jsx
import { useState } from "react";
import { login } from "../api";

export default function Login({ onLoggedIn }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function handleSubmit(e) {
    e.preventDefault();
    setError("");
    try {
      await login(username, password);
      onLoggedIn();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <h1>SnapStack Login</h1>
      <input
        type="text"
        placeholder="Username"
        value={username}
        onChange={(e) => setUsername(e.target.value)}
      />
      <input
        type="password"
        placeholder="Password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <button type="submit">Log in</button>
      {error && <p role="alert">{error}</p>}
    </form>
  );
}
```

- [ ] **Step 5: Modify `dashboard/src/App.jsx`**

```jsx
import { useState } from "react";
import Login from "./pages/Login";
import { isLoggedIn, logout } from "./api";

function App() {
  const [loggedIn, setLoggedIn] = useState(isLoggedIn());

  if (!loggedIn) {
    return <Login onLoggedIn={() => setLoggedIn(true)} />;
  }

  return (
    <div>
      <header>
        <h1>SnapStack</h1>
        <button
          onClick={() => {
            logout();
            setLoggedIn(false);
          }}
        >
          Log out
        </button>
      </header>
      <p>Logged in.</p>
    </div>
  );
}

export default App;
```

- [ ] **Step 6: Manually verify**

With the backend running (`python app.py` in `backend/`, and a user created via `python scripts/create_user.py`):

```bash
cd dashboard
npm run dev
```

Open `http://localhost:5173`. Confirm: login form renders; wrong credentials show an error message; correct credentials show "Logged in." and a Log out button.

- [ ] **Step 7: Commit**

```bash
cd dashboard
git add .
git commit -m "feat: scaffold dashboard with login page"
```

---

### Task 8: Dashboard list/search view

**Files:**
- Create: `dashboard/src/pages/Snaps.jsx`
- Create: `dashboard/src/components/SnapCard.jsx`
- Modify: `dashboard/src/App.jsx` (nav + render Snaps)

**Interfaces:**
- Consumes: `api.listSnaps, searchSnaps, retrySummary` (Task 7).
- Produces: `<Snaps />` component, `<SnapCard snap onRetry />` component.

- [ ] **Step 1: Create `dashboard/src/components/SnapCard.jsx`**

```jsx
export default function SnapCard({ snap, onRetry }) {
  return (
    <div className="snap-card">
      <h3>{snap.title || snap.url}</h3>
      <p>{snap.summary || "No summary yet."}</p>
      {!snap.summary && <button onClick={onRetry}>Retry summarization</button>}
      <div>
        {snap.tags.map((tag) => (
          <span key={tag} className="tag">
            {tag}
          </span>
        ))}
      </div>
      <a href={snap.url} target="_blank" rel="noreferrer">
        Source
      </a>
    </div>
  );
}
```

- [ ] **Step 2: Create `dashboard/src/pages/Snaps.jsx`**

```jsx
import { useEffect, useState } from "react";
import { listSnaps, searchSnaps, retrySummary } from "../api";
import SnapCard from "../components/SnapCard";

export default function Snaps() {
  const [snaps, setSnaps] = useState([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    loadAll();
  }, []);

  async function loadAll() {
    try {
      setSnaps(await listSnaps());
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleSearch(e) {
    e.preventDefault();
    setError("");
    try {
      if (query.trim() === "") {
        await loadAll();
      } else {
        setSnaps(await searchSnaps(query));
      }
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleRetry(snapId) {
    try {
      await retrySummary(snapId);
      await loadAll();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div>
      <form onSubmit={handleSearch}>
        <input
          type="text"
          placeholder="Search snaps..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button type="submit">Search</button>
      </form>
      {error && <p role="alert">{error}</p>}
      <div>
        {snaps.map((snap) => (
          <SnapCard key={snap.id} snap={snap} onRetry={() => handleRetry(snap.id)} />
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Modify `dashboard/src/App.jsx`**

```jsx
import { useState } from "react";
import Login from "./pages/Login";
import Snaps from "./pages/Snaps";
import { isLoggedIn, logout } from "./api";

function App() {
  const [loggedIn, setLoggedIn] = useState(isLoggedIn());
  const [view, setView] = useState("snaps");

  if (!loggedIn) {
    return <Login onLoggedIn={() => setLoggedIn(true)} />;
  }

  return (
    <div>
      <header>
        <h1>SnapStack</h1>
        <nav>
          <button onClick={() => setView("snaps")}>Snaps</button>
          <button onClick={() => setView("review")}>Review</button>
        </nav>
        <button
          onClick={() => {
            logout();
            setLoggedIn(false);
          }}
        >
          Log out
        </button>
      </header>
      {view === "snaps" && <Snaps />}
      {view === "review" && <p>Review mode coming soon.</p>}
    </div>
  );
}

export default App;
```

- [ ] **Step 4: Manually verify**

With the backend running and at least one snap saved (via `curl -X POST http://localhost:5100/api/snaps -H "Authorization: Bearer <token>" -H "Content-Type: application/json" -d '{"url":"http://test.com","title":"Test","text":"some captured text"}'`):

```bash
cd dashboard
npm run dev
```

Confirm the Snaps view lists the saved snap, the search box filters results, and (if summarization failed) the "Retry summarization" button appears and works.

- [ ] **Step 5: Commit**

```bash
cd dashboard
git add src/pages/Snaps.jsx src/components/SnapCard.jsx src/App.jsx
git commit -m "feat: add snap list/search dashboard view"
```

---

### Task 9: Dashboard review mode (flashcards)

**Files:**
- Create: `dashboard/src/pages/Review.jsx`
- Modify: `dashboard/src/App.jsx` (render Review instead of placeholder)

**Interfaces:**
- Consumes: `api.getDueSnaps, gradeSnap` (Task 7).
- Produces: `<Review />` component.

- [ ] **Step 1: Create `dashboard/src/pages/Review.jsx`**

```jsx
import { useEffect, useState } from "react";
import { getDueSnaps, gradeSnap } from "../api";

export default function Review() {
  const [queue, setQueue] = useState([]);
  const [revealed, setRevealed] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    loadDue();
  }, []);

  async function loadDue() {
    try {
      setQueue(await getDueSnaps());
      setRevealed(false);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleGrade(grade) {
    const current = queue[0];
    try {
      await gradeSnap(current.id, grade);
      setQueue((q) => q.slice(1));
      setRevealed(false);
    } catch (err) {
      setError(err.message);
    }
  }

  if (error) return <p role="alert">{error}</p>;
  if (queue.length === 0) return <p>Nothing due for review. Nice.</p>;

  const current = queue[0];

  return (
    <div className="flashcard">
      <p className="remaining">{queue.length} due</p>
      <h3>{current.title || current.url}</h3>
      <p>{current.raw_text}</p>
      {!revealed && <button onClick={() => setRevealed(true)}>Reveal summary</button>}
      {revealed && (
        <>
          <p className="summary">{current.summary || "No summary available."}</p>
          <div className="grade-buttons">
            <button onClick={() => handleGrade("again")}>Again</button>
            <button onClick={() => handleGrade("hard")}>Hard</button>
            <button onClick={() => handleGrade("good")}>Good</button>
            <button onClick={() => handleGrade("easy")}>Easy</button>
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Modify `dashboard/src/App.jsx`**

Replace the placeholder line with a real import and render:

```jsx
import { useState } from "react";
import Login from "./pages/Login";
import Snaps from "./pages/Snaps";
import Review from "./pages/Review";
import { isLoggedIn, logout } from "./api";

function App() {
  const [loggedIn, setLoggedIn] = useState(isLoggedIn());
  const [view, setView] = useState("snaps");

  if (!loggedIn) {
    return <Login onLoggedIn={() => setLoggedIn(true)} />;
  }

  return (
    <div>
      <header>
        <h1>SnapStack</h1>
        <nav>
          <button onClick={() => setView("snaps")}>Snaps</button>
          <button onClick={() => setView("review")}>Review</button>
        </nav>
        <button
          onClick={() => {
            logout();
            setLoggedIn(false);
          }}
        >
          Log out
        </button>
      </header>
      {view === "snaps" && <Snaps />}
      {view === "review" && <Review />}
    </div>
  );
}

export default App;
```

- [ ] **Step 3: Manually verify**

With the backend running and at least one due snap saved:

```bash
cd dashboard
npm run dev
```

Switch to the Review tab. Confirm: raw text shows first, "Reveal summary" shows the summary and grade buttons, grading removes the card from the queue and advances to the next one, and an empty queue shows "Nothing due for review."

- [ ] **Step 4: Commit**

```bash
cd dashboard
git add src/pages/Review.jsx src/App.jsx
git commit -m "feat: add spaced-repetition review mode to dashboard"
```

---

### Task 10: Extension scaffold — capture via context menu

**Files:**
- Create: `extension/manifest.json`
- Create: `extension/background.js`
- Create: `extension/icon128.png`

**Interfaces:**
- Consumes: backend `POST /api/snaps` (Task 4); `chrome.storage.local` key `snapstack_token` (set by Task 11's popup).
- Produces: context menu item "Add to SnapStack" active whenever text is selected on a page.

Note: no content script is needed — `chrome.contextMenus`'s `info.selectionText` already provides the highlighted text, URL, and title directly to the background script, satisfying the spec's capture requirement without extra moving parts.

- [ ] **Step 1: Generate a placeholder icon**

```bash
pip install Pillow
python -c "
from PIL import Image
img = Image.new('RGB', (128, 128), color=(79, 70, 229))
img.save('C:/Users/Admin/Desktop/devplus/extension/icon128.png')
"
```

- [ ] **Step 2: Create `extension/manifest.json`**

```json
{
  "manifest_version": 3,
  "name": "SnapStack",
  "version": "1.0.0",
  "description": "Capture highlighted text into SnapStack for later review.",
  "icons": { "128": "icon128.png" },
  "permissions": ["contextMenus", "storage", "notifications"],
  "host_permissions": ["http://localhost:5100/*"],
  "background": {
    "service_worker": "background.js"
  },
  "action": {
    "default_popup": "popup/popup.html",
    "default_title": "SnapStack"
  },
  "browser_specific_settings": {
    "gecko": {
      "id": "snapstack@devplus.local",
      "strict_min_version": "109.0"
    }
  }
}
```

- [ ] **Step 3: Create `extension/background.js`**

```javascript
const API_URL = "http://localhost:5100";
const MENU_ID = "snapstack-add";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: MENU_ID,
    title: "Add to SnapStack",
    contexts: ["selection"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== MENU_ID || !info.selectionText) {
    return;
  }
  await captureSelection(info.selectionText, tab.url, tab.title);
});

async function captureSelection(text, url, title) {
  const { snapstack_token: token } = await chrome.storage.local.get("snapstack_token");

  if (!token) {
    notify("SnapStack", "Log in required — open the SnapStack popup.");
    return;
  }

  try {
    const resp = await fetch(`${API_URL}/api/snaps`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ text, url, title }),
    });

    if (resp.status === 401) {
      notify("SnapStack", "Log in required — open the SnapStack popup.");
      return;
    }
    if (!resp.ok) {
      notify("SnapStack", "Save failed — check the backend is running.");
      return;
    }
    notify("SnapStack", "Saved.");
  } catch (err) {
    notify("SnapStack", "SnapStack backend unreachable — is it running?");
  }
}

function notify(title, message) {
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icon128.png",
    title,
    message,
  });
}
```

- [ ] **Step 4: Manually verify (requires Task 11's popup for login first — do the login check after Task 11; for now just confirm the menu appears)**

In Chrome: `chrome://extensions` → enable Developer mode → "Load unpacked" → select `devplus/extension`. Visit any webpage, highlight text, right-click. Confirm "Add to SnapStack" appears in the context menu (clicking it now will show the "Log in required" notification, since no popup/login exists yet).

- [ ] **Step 5: Commit**

```bash
cd extension
git add manifest.json background.js icon128.png
git commit -m "feat: add extension scaffold with context-menu capture"
```

---

### Task 11: Extension popup (login)

**Files:**
- Create: `extension/popup/popup.html`
- Create: `extension/popup/popup.js`
- Create: `extension/popup/popup.css`

**Interfaces:**
- Consumes: backend `POST /api/auth/login` (Task 3); `chrome.storage.local`.
- Produces: `chrome.storage.local` key `snapstack_token`, consumed by `background.js` (Task 10).

- [ ] **Step 1: Create `extension/popup/popup.html`**

```html
<!DOCTYPE html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>SnapStack</title>
    <link rel="stylesheet" href="popup.css" />
  </head>
  <body>
    <div id="root">
      <h1>SnapStack</h1>
      <div id="logged-out">
        <input type="text" id="username" placeholder="Username" />
        <input type="password" id="password" placeholder="Password" />
        <button id="login-btn">Log in</button>
        <p id="error"></p>
      </div>
      <div id="logged-in" hidden>
        <p>Logged in.</p>
        <button id="logout-btn">Log out</button>
        <a href="http://localhost:5173" target="_blank">Open dashboard</a>
      </div>
    </div>
    <script src="popup.js"></script>
  </body>
</html>
```

- [ ] **Step 2: Create `extension/popup/popup.css`**

```css
body {
  width: 220px;
  font-family: sans-serif;
  padding: 12px;
}
input,
button {
  display: block;
  width: 100%;
  margin-bottom: 8px;
}
#error {
  color: #c0392b;
  font-size: 12px;
}
```

- [ ] **Step 3: Create `extension/popup/popup.js`**

```javascript
const API_URL = "http://localhost:5100";

const loggedOutEl = document.getElementById("logged-out");
const loggedInEl = document.getElementById("logged-in");
const errorEl = document.getElementById("error");

async function refreshView() {
  const { snapstack_token: token } = await chrome.storage.local.get("snapstack_token");
  loggedOutEl.hidden = Boolean(token);
  loggedInEl.hidden = !token;
}

document.getElementById("login-btn").addEventListener("click", async () => {
  errorEl.textContent = "";
  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;

  try {
    const resp = await fetch(`${API_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!resp.ok) {
      errorEl.textContent = "Invalid username or password.";
      return;
    }
    const { token } = await resp.json();
    await chrome.storage.local.set({ snapstack_token: token });
    refreshView();
  } catch (err) {
    errorEl.textContent = "SnapStack backend unreachable.";
  }
});

document.getElementById("logout-btn").addEventListener("click", async () => {
  await chrome.storage.local.remove("snapstack_token");
  refreshView();
});

refreshView();
```

- [ ] **Step 4: Manually verify the full capture flow end to end**

With the backend running and a user created:

1. `chrome://extensions` → reload the SnapStack extension (to pick up the new popup files).
2. Click the SnapStack toolbar icon, log in with the created user's credentials. Confirm the popup switches to "Logged in." with a working "Open dashboard" link.
3. Visit any webpage, highlight a sentence, right-click → "Add to SnapStack". Confirm a "Saved." notification appears.
4. Open the dashboard (`http://localhost:5173`), go to the Snaps tab, confirm the captured text appears (with a summary if Ollama is running, or a "Retry summarization" button if not).

- [ ] **Step 5: Commit**

```bash
cd extension
git add popup/
git commit -m "feat: add extension popup with login"
```

---

## Post-plan checklist (not a task — verify once all tasks are done)

- [ ] All five backend `test_*.py` scripts pass individually.
- [ ] Full capture → summarize → list → search → review loop works end to end with a real local Ollama running.
- [ ] Extension loads in both Chrome and Firefox (`about:debugging` → "This Firefox" → "Load Temporary Add-on" → select `extension/manifest.json`).
