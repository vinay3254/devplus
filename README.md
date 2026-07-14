# SnapStack

Highlight text on any webpage, right-click, and save it. SnapStack summarizes and
auto-tags the capture with a local LLM, indexes it for semantic search, and files
it for spaced-repetition review.

## Why

A personal study/interview-prep tool: capture concepts while reading, review them
later as flashcards, and search past captures semantically instead of by exact
keyword.

## Architecture

- **`backend/`** — Flask + SQLite + FAISS + Ollama. JWT-authenticated REST API:
  capture, semantic/keyword search, SM-2 spaced-repetition scheduling.
- **`dashboard/`** — Vite + React. Login, snap list/search, flashcard review mode.
- **`extension/`** — Manifest V3 browser extension (Chrome + Firefox). Context-menu
  capture (`Add to SnapStack`) and a login popup.

See [`docs/superpowers/specs/2026-07-14-snapstack-design.md`](docs/superpowers/specs/2026-07-14-snapstack-design.md)
for the full design and [`docs/superpowers/plans/2026-07-14-snapstack-mvp.md`](docs/superpowers/plans/2026-07-14-snapstack-mvp.md)
for the implementation plan.

## Setup

### Backend

```bash
cd backend
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt   # .venv/bin/python on macOS/Linux
cp .env.example .env
./.venv/Scripts/python.exe scripts/create_user.py               # create your login
./.venv/Scripts/python.exe app.py                                # serves on :5100
```

Requires a local [Ollama](https://ollama.com) instance running with a chat model
(default `qwen3:8b`) and an embedding model (default `nomic-embed-text`) pulled.

Run the backend test suite (standalone scripts, not pytest):

```bash
cd backend
./.venv/Scripts/python.exe test_ollama_client.py
./.venv/Scripts/python.exe test_auth.py
./.venv/Scripts/python.exe test_capture_service.py
./.venv/Scripts/python.exe test_search_service.py
./.venv/Scripts/python.exe test_review_service.py
```

### Dashboard

```bash
cd dashboard
npm install
cp .env.example .env
npm run dev   # serves on :5173
```

### Extension

1. `chrome://extensions` (or `about:debugging` in Firefox) → enable Developer mode.
2. "Load unpacked" → select the `extension/` directory.
3. Click the SnapStack toolbar icon and log in with the user you created above.
4. Highlight text on any page → right-click → "Add to SnapStack".

## Status

v1 (MVP) implemented per the plan above. Not deployed anywhere — local-only,
single-user by design.
