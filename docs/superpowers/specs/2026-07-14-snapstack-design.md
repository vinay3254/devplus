# SnapStack — Design Spec

Date: 2026-07-14
Status: Approved (pending final spec review)

## Summary

SnapStack is a browser extension + local web app for turning highlighted text on any webpage into a structured, reviewable note. Highlight text → right-click → "Add to SnapStack" → the backend summarizes and auto-tags it via a local LLM, embeds it for semantic search, and files it for spaced-repetition review on a dashboard.

Primary use case: personal study/interview-prep tool — capture concepts while reading, review them later via flashcards, and search past captures semantically instead of by exact keyword.

## Scope (v1)

In scope:
- Chrome + Firefox extension (Manifest V3) for capture
- Flask backend: capture, summarization/tagging via local Ollama, SQLite storage, FAISS semantic search, SM-2 spaced-repetition scheduling
- Vite + React dashboard: login, list/search view, review (flashcard) mode
- Basic single-user auth (JWT)
- Local-only deployment (backend runs on your machine; not exposed to other devices)

Out of scope (deferred, not part of this design):
- Offline queueing/local buffering in the extension when the backend is unreachable
- Automatic retry of failed summarizations (manual retry button only)
- Multi-user support
- Remote/hosted deployment, mobile access
- Cloud LLM provider support (Ollama only for v1)

## Architecture & Components

**1. Browser extension** (Chrome + Firefox, Manifest V3, vanilla JS)
- Content script + context-menu entry ("Add to SnapStack") captures highlighted text, page URL, and title on right-click.
- Background service worker POSTs the capture to the backend and shows a toast (success/error).
- Popup shows login status and a link to open the dashboard.

**2. Backend** (Flask, mirrors Pragna's `app.py` + `services/` layout)
- `services/auth.py` — username/password + JWT, modeled on Pragna's `require_auth` decorator. Single user account, created via a one-time local setup script (no public register endpoint).
- `services/capture_service.py` — receives a raw snippet, calls Ollama for summary + auto-tag/category, computes an embedding, writes to SQLite + FAISS.
- `services/review_service.py` — SM-2 spaced-repetition scheduling: due-card queries, grade-and-reschedule.
- `services/search_service.py` — embedding + FAISS similarity search, with keyword fallback.
- SQLite table `snaps`: `id, url, title, raw_text, summary, category, tags, created_at`, plus SM-2 fields (`interval, repetitions, easiness_factor, due_date`).
- FAISS index persisted to disk, following the pattern in Pragna's `services/rag_service.py`.

**3. Dashboard** (Vite + React, same tooling as Pragna's `chatbot-ui-vite/`)
- Login screen (JWT stored in localStorage).
- List/search view — semantic search bar, tag/category filters.
- Review mode — flashcard flow (show snippet → reveal summary → grade recall: again/hard/good/easy) driving the SM-2 scheduler.

## Data Flow

**Capture:**
1. Highlight text on any page → right-click → "Add to SnapStack."
2. Background script `POST /api/snaps` with `{text, url, title}` (JWT attached).
3. Backend calls Ollama to generate a summary + auto-assigned category/tags.
4. Backend computes an embedding, stores the row in SQLite, adds the vector to the FAISS index.
5. Extension shows a confirmation toast.

**Review (spaced repetition):**
1. Dashboard requests `GET /api/review/due` — snaps whose `due_date` has passed.
2. User sees the raw snippet, tries to recall, reveals the summary, grades themselves (again/hard/good/easy).
3. `POST /api/review/:id/grade` updates the SM-2 fields (interval, repetitions, easiness factor, next `due_date`).

**Search:**
1. Dashboard search bar sends the query to `GET /api/snaps/search?q=...`.
2. Backend embeds the query, runs FAISS similarity search, falls back to keyword match on title/tags if FAISS returns nothing above a similarity threshold.
3. Results returned ranked, rendered as a list.

## Error Handling

- **Ollama unreachable/fails during capture**: the snippet is still saved with `summary=null`, `category=null`; failure is logged. Dashboard shows "no summary yet" with a manual "Retry summarization" button. No auto-retry or offline queue in v1.
- **Extension can't reach backend**: background script shows an error toast ("SnapStack backend unreachable — is it running?"). No local queuing/buffering in v1.
- **JWT expired/invalid**: dashboard redirects to login; extension popup shows "log in required" and rejects captures with a clear error toast.
- **FAISS index/SQLite drift** (writes aren't transactional across both): on backend startup, a consistency check rebuilds the FAISS index from SQLite if the vector count doesn't match the row count.

## Testing

Following Pragna's convention — standalone `test_*.py` scripts at the backend root, plain `assert` statements, run individually with `python test_x.py` (not pytest-discovered):

- `test_capture_service.py` — snippet save with mocked Ollama response; verifies fallback behavior when the Ollama call fails (raw text still saved).
- `test_review_service.py` — SM-2 scheduling math: grading sequences produce expected interval/due_date progressions.
- `test_search_service.py` — embedding + FAISS search returns expected ranking; keyword fallback triggers correctly below the similarity threshold.
- `test_auth.py` — login issues a valid JWT; protected routes reject missing/expired tokens.

**Extension**: no automated tests — manual checklist: capture on a real page, confirm toast, confirm it lands in the dashboard.

**Dashboard**: no test runner (matches `chatbot-ui-vite/` convention) — verified via dev server + manual exercise of capture → list → search → review flow.

## Repository Layout

```
devplus/
  backend/
    app.py
    services/
      auth.py
      capture_service.py
      review_service.py
      search_service.py
    data/            # SQLite db, FAISS index
    test_*.py
  extension/
    manifest.json
    background.js
    content.js
    popup/
  dashboard/          # Vite + React app
  docs/superpowers/specs/
```
