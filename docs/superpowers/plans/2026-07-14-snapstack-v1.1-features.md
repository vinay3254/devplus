# SnapStack v1.1 Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tag/category filtering, keyboard-shortcut capture, review streak/stats, and snap edit/delete to SnapStack, and drop Firefox support in favor of Chrome-only.

**Architecture:** Backend gains a `review_log` table (for streak history) and `PATCH`/`DELETE /api/snaps/<id>` endpoints (new `snap_management.py` service, mirroring the existing blueprint-per-concern pattern). Dashboard changes are additive to existing pages/components. Extension changes are additive to the existing `manifest.json`/`background.js`.

**Tech Stack:** Same as v1 — Flask/SQLite/FAISS backend, Vite/React dashboard, Manifest V3 extension (Chrome only as of this plan).

## Global Constraints

- **Do NOT run `git commit` at any point in this plan** — per explicit user instruction, leave all changes staged/unstaged for the user to review and commit themselves.
- Backend tests: standalone `test_*.py` scripts, plain `assert`, run via `./.venv/Scripts/python.exe test_x.py` (the backend venv, not global Python) — not pytest-discovered.
- Dashboard: no test runner — verified via dev server + manual exercise.
- Extension: no automated tests — manual checklist verification, Chrome only (Firefox dropped).
- `review_log.graded_at` and `snaps.due_date` both use date-only ISO strings (`datetime.date.today().isoformat()`), never full timestamps — this consistency is load-bearing (see the v1 `due_date` bug fixed during v1 implementation).

---

## File Structure

```
devplus/
  backend/
    database.py                       # MODIFY: add review_log table to SCHEMA
    services/
      review_service.py               # MODIFY: log grades, add GET /api/review/stats
      search_index.py                 # MODIFY: add remove(snap_id)
      snap_management.py              # CREATE: PATCH/DELETE /api/snaps/<id>
    app.py                             # MODIFY: register snap_management blueprint
    test_review_service.py             # MODIFY: streak/stats test cases
    test_snap_management.py            # CREATE: PATCH/DELETE test cases
  dashboard/
    src/
      api.js                          # MODIFY: updateSnap, deleteSnap, getReviewStats
      components/
        SnapCard.jsx                  # MODIFY: edit/delete UI, clickable tag/category chips
      pages/
        Snaps.jsx                     # MODIFY: filter state + clear-filter UI
        Stats.jsx                     # CREATE: streak/stats view
      App.jsx                         # MODIFY: add Stats nav tab
  extension/
    manifest.json                     # MODIFY: drop browser_specific_settings, add commands + permissions
    background.js                     # MODIFY: add chrome.commands.onCommand listener
  README.md                            # MODIFY: Chrome-only extension steps, mention shortcut
```

---

### Task 1: Review log + streak/stats endpoint

**Files:**
- Modify: `backend/database.py`
- Modify: `backend/services/review_service.py`
- Test: `backend/test_review_service.py`

**Interfaces:**
- Consumes: `services.auth.require_auth`; existing `config.DB_PATH`, `database.get_connection`.
- Produces: `GET /api/review/stats` → `{"current_streak": int, "longest_streak": int, "total_reviewed": int, "reviewed_today": int}`. `POST /api/review/<id>/grade` now also inserts a `review_log` row (response shape unchanged).

- [ ] **Step 1: Write the failing tests**

Add to the end of `backend/test_review_service.py` (before the `if __name__ == "__main__":` block):

```python
def test_grade_endpoint_logs_review():
    seed_due_snap()
    app = create_app()
    client = app.test_client()
    client.post("/api/review/1/grade", json={"grade": "good"}, headers=auth_headers())

    conn = get_connection(config.DB_PATH)
    rows = conn.execute("SELECT * FROM review_log WHERE snap_id = 1").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0]["grade"] == "good"
    assert rows[0]["graded_at"] == datetime.date.today().isoformat()
    print("PASS: grading inserts a review_log row")


def seed_review_log(dates):
    init_db(config.DB_PATH)
    conn = get_connection(config.DB_PATH)
    conn.execute("DELETE FROM review_log")
    for d in dates:
        conn.execute(
            "INSERT INTO review_log (snap_id, graded_at, grade) VALUES (1, ?, 'good')",
            (d.isoformat(),),
        )
    conn.commit()
    conn.close()


def test_stats_streak_and_totals():
    today = datetime.date.today()
    seed_review_log([today, today - datetime.timedelta(days=1), today - datetime.timedelta(days=2)])
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/review/stats", headers=auth_headers())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["current_streak"] == 3
    assert body["longest_streak"] == 3
    assert body["total_reviewed"] == 3
    assert body["reviewed_today"] == 1
    print("PASS: stats computes streak/totals from consecutive days")


def test_stats_streak_breaks_on_gap():
    today = datetime.date.today()
    seed_review_log([today, today - datetime.timedelta(days=1), today - datetime.timedelta(days=5)])
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/review/stats", headers=auth_headers())
    body = resp.get_json()
    assert body["current_streak"] == 2
    assert body["longest_streak"] == 2
    assert body["total_reviewed"] == 3
    print("PASS: streak breaks on a gap, longest_streak still reflects the best run")


def test_stats_empty_history_returns_zeros():
    seed_review_log([])
    app = create_app()
    client = app.test_client()
    resp = client.get("/api/review/stats", headers=auth_headers())
    body = resp.get_json()
    assert body == {
        "current_streak": 0,
        "longest_streak": 0,
        "total_reviewed": 0,
        "reviewed_today": 0,
    }
    print("PASS: empty review history returns all zeros")
```

Also add `conn.execute("DELETE FROM review_log")` to `seed_due_snap()` (right after the existing `conn.execute("DELETE FROM snaps")` line) — without it, a prior test's grade action leaks a `review_log` row into this test's count, since `seed_due_snap()` only clears `snaps`.

Also update the `if __name__ == "__main__":` block at the bottom of the file to call all four new functions:

```python
if __name__ == "__main__":
    test_sm2_good_grades_increase_interval_progressively()
    test_sm2_again_resets_repetitions_and_interval()
    test_due_endpoint_returns_overdue_snaps()
    test_grade_endpoint_updates_due_date_forward()
    test_grade_endpoint_logs_review()
    test_stats_streak_and_totals()
    test_stats_streak_breaks_on_gap()
    test_stats_empty_history_returns_zeros()
    print("All review_service tests passed.")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/Scripts/python.exe test_review_service.py`
Expected: fails on `test_grade_endpoint_logs_review` with `sqlite3.OperationalError: no such table: review_log`

- [ ] **Step 3: Add the `review_log` table to `backend/database.py`**

In `SCHEMA`, after the `snaps` table definition, add:

```python
CREATE TABLE IF NOT EXISTS review_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snap_id INTEGER NOT NULL,
    graded_at TEXT NOT NULL,
    grade TEXT NOT NULL
);
```

(So `SCHEMA` becomes the `users` table, then `snaps`, then this new `review_log` table, all inside the same triple-quoted string.)

- [ ] **Step 4: Modify `backend/services/review_service.py`** to log every grade and add the stats endpoint

Replace the `grade_snap` function's body from the `conn.execute("UPDATE snaps ...")` line onward, and add the new stats function + route at the end of the file:

```python
    conn.execute(
        "UPDATE snaps SET repetitions = ?, easiness_factor = ?, interval = ?, due_date = ? WHERE id = ?",
        (repetitions, easiness_factor, interval, due_date, snap_id),
    )
    conn.execute(
        "INSERT INTO review_log (snap_id, graded_at, grade) VALUES (?, ?, ?)",
        (snap_id, datetime.date.today().isoformat(), grade),
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


def _compute_stats(conn):
    rows = conn.execute("SELECT DISTINCT graded_at FROM review_log").fetchall()
    dates = {datetime.date.fromisoformat(r["graded_at"]) for r in rows}

    total_reviewed = conn.execute("SELECT COUNT(*) AS c FROM review_log").fetchone()["c"]
    today = datetime.date.today()
    reviewed_today = conn.execute(
        "SELECT COUNT(*) AS c FROM review_log WHERE graded_at = ?", (today.isoformat(),)
    ).fetchone()["c"]

    current_streak = 0
    cursor_date = today if today in dates else today - datetime.timedelta(days=1)
    while cursor_date in dates:
        current_streak += 1
        cursor_date -= datetime.timedelta(days=1)

    longest_streak = 0
    run = 0
    prev = None
    for d in sorted(dates):
        run = run + 1 if prev is not None and (d - prev).days == 1 else 1
        longest_streak = max(longest_streak, run)
        prev = d

    return {
        "current_streak": current_streak,
        "longest_streak": longest_streak,
        "total_reviewed": total_reviewed,
        "reviewed_today": reviewed_today,
    }


@bp.route("/api/review/stats", methods=["GET"])
@require_auth
def review_stats():
    conn = get_connection(config.DB_PATH)
    stats = _compute_stats(conn)
    conn.close()
    return jsonify(stats)
```

Note the existing `grade_snap` function currently ends with `conn.close()` immediately after the `UPDATE`, then builds the response — the replacement above moves `conn.close()` to after the new `INSERT`, and keeps the same final `jsonify(...)` response.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe test_review_service.py`
Expected: `All review_service tests passed.`

---

### Task 2: Snap edit/delete endpoints

**Files:**
- Modify: `backend/services/search_index.py`
- Create: `backend/services/snap_management.py`
- Modify: `backend/app.py`
- Test: `backend/test_snap_management.py`

**Interfaces:**
- Consumes: `services.auth.require_auth`; `database.get_connection`; `services.search_index` (existing module).
- Produces: `search_index.remove(snap_id: int) -> None`; `snap_management.bp` exposing `PATCH /api/snaps/<id>` (body: subset of `{title, category, tags}`) and `DELETE /api/snaps/<id>`.

- [ ] **Step 1: Write the failing tests**

Create `backend/test_snap_management.py`:

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
from app import create_app


def seed_snap():
    init_db(config.DB_PATH)
    conn = get_connection(config.DB_PATH)
    conn.execute("DELETE FROM snaps")
    conn.execute(
        "INSERT INTO snaps (id, url, title, raw_text, summary, category, tags, created_at, due_date) "
        "VALUES (1, 'http://a.com', 'Old Title', 'text', 'sum', 'old-cat', 'old,tags', '2026-01-01', '2026-01-01')"
    )
    conn.commit()
    conn.close()


def auth_headers():
    return {"Authorization": f"Bearer {create_token('testuser')}"}


def test_patch_updates_only_provided_fields():
    seed_snap()
    app = create_app()
    client = app.test_client()
    resp = client.patch("/api/snaps/1", json={"title": "New Title"}, headers=auth_headers())
    assert resp.status_code == 200

    conn = get_connection(config.DB_PATH)
    row = conn.execute("SELECT * FROM snaps WHERE id = 1").fetchone()
    conn.close()
    assert row["title"] == "New Title"
    assert row["category"] == "old-cat"
    assert row["tags"] == "old,tags"
    print("PASS: PATCH updates only the provided fields")


def test_patch_missing_snap_returns_404():
    seed_snap()
    app = create_app()
    client = app.test_client()
    resp = client.patch("/api/snaps/999", json={"title": "x"}, headers=auth_headers())
    assert resp.status_code == 404
    print("PASS: PATCH on missing snap returns 404")


def test_delete_removes_row_and_calls_search_index_remove():
    seed_snap()
    app = create_app()
    client = app.test_client()

    with patch("services.snap_management.search_index") as mock_index:
        resp = client.delete("/api/snaps/1", headers=auth_headers())

    assert resp.status_code == 200
    mock_index.remove.assert_called_once_with(1)

    conn = get_connection(config.DB_PATH)
    row = conn.execute("SELECT * FROM snaps WHERE id = 1").fetchone()
    conn.close()
    assert row is None
    print("PASS: DELETE removes the row and calls search_index.remove")


def test_delete_missing_snap_returns_404():
    seed_snap()
    app = create_app()
    client = app.test_client()
    resp = client.delete("/api/snaps/999", headers=auth_headers())
    assert resp.status_code == 404
    print("PASS: DELETE on missing snap returns 404")


if __name__ == "__main__":
    test_patch_updates_only_provided_fields()
    test_patch_missing_snap_returns_404()
    test_delete_removes_row_and_calls_search_index_remove()
    test_delete_missing_snap_returns_404()
    print("All snap_management tests passed.")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && ./.venv/Scripts/python.exe test_snap_management.py`
Expected: `ModuleNotFoundError: No module named 'app'` fails first on the PATCH call with a 404/405 since no such route exists yet — specifically `AssertionError` on `resp.status_code == 200` (route doesn't exist, Flask returns 404 for unmatched PATCH).

- [ ] **Step 3: Add `remove` to `backend/services/search_index.py`**

Add this function (after `add`, before `search`):

```python
def remove(snap_id):
    with _lock:
        index = _load()
        index.remove_ids(np.array([snap_id], dtype="int64"))
        os.makedirs(os.path.dirname(config.FAISS_INDEX_PATH), exist_ok=True)
        faiss.write_index(index, config.FAISS_INDEX_PATH)
```

- [ ] **Step 4: Create `backend/services/snap_management.py`**

```python
from flask import Blueprint, request, jsonify

import config
from database import get_connection
from services.auth import require_auth
from services import search_index

bp = Blueprint("snap_management", __name__)


@bp.route("/api/snaps/<int:snap_id>", methods=["PATCH"])
@require_auth
def update_snap(snap_id):
    data = request.get_json(force=True) or {}
    conn = get_connection(config.DB_PATH)
    row = conn.execute("SELECT id FROM snaps WHERE id = ?", (snap_id,)).fetchone()
    if row is None:
        conn.close()
        return jsonify({"error": "not found"}), 404

    fields = []
    values = []
    if "title" in data:
        fields.append("title = ?")
        values.append(data["title"])
    if "category" in data:
        fields.append("category = ?")
        values.append(data["category"])
    if "tags" in data:
        fields.append("tags = ?")
        values.append(",".join(data["tags"]))

    if fields:
        values.append(snap_id)
        conn.execute(f"UPDATE snaps SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()

    conn.close()
    return jsonify({"status": "updated"})


@bp.route("/api/snaps/<int:snap_id>", methods=["DELETE"])
@require_auth
def delete_snap(snap_id):
    conn = get_connection(config.DB_PATH)
    row = conn.execute("SELECT id FROM snaps WHERE id = ?", (snap_id,)).fetchone()
    if row is None:
        conn.close()
        return jsonify({"error": "not found"}), 404

    conn.execute("DELETE FROM snaps WHERE id = ?", (snap_id,))
    conn.commit()
    conn.close()
    search_index.remove(snap_id)
    return jsonify({"status": "deleted"})
```

- [ ] **Step 5: Modify `backend/app.py`** to register the new blueprint

In `create_app`, add the import and registration:

```python
    from services.auth import bp as auth_bp
    from services.capture_service import bp as capture_bp
    from services.search_service import bp as snaps_bp
    from services.review_service import bp as review_bp
    from services.snap_management import bp as snap_management_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(capture_bp)
    app.register_blueprint(snaps_bp)
    app.register_blueprint(review_bp)
    app.register_blueprint(snap_management_bp)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd backend && ./.venv/Scripts/python.exe test_snap_management.py`
Expected: `All snap_management tests passed.`

- [ ] **Step 7: Run the full backend suite**

```bash
cd backend
./.venv/Scripts/python.exe test_ollama_client.py
./.venv/Scripts/python.exe test_auth.py
./.venv/Scripts/python.exe test_capture_service.py
./.venv/Scripts/python.exe test_search_service.py
./.venv/Scripts/python.exe test_review_service.py
./.venv/Scripts/python.exe test_snap_management.py
```

Expected: all six print their "All ... tests passed." line.

---

### Task 3: Dashboard edit/delete

**Files:**
- Modify: `dashboard/src/api.js`
- Modify: `dashboard/src/components/SnapCard.jsx`
- Modify: `dashboard/src/pages/Snaps.jsx`

**Interfaces:**
- Consumes: backend `PATCH`/`DELETE /api/snaps/<id>` (Task 2); existing `authedFetch` helper in `api.js`.
- Produces: `api.updateSnap(snapId, fields) -> Promise`; `api.deleteSnap(snapId) -> Promise`; `SnapCard` gains an `onChanged` prop (callback invoked after a successful edit or delete).

- [ ] **Step 1: Add to `dashboard/src/api.js`** (after `gradeSnap`)

```javascript
export async function updateSnap(snapId, fields) {
  const resp = await authedFetch(`${API_URL}/api/snaps/${snapId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields),
  });
  if (!resp.ok) throw new Error("Update failed");
  return resp.json();
}

export async function deleteSnap(snapId) {
  const resp = await authedFetch(`${API_URL}/api/snaps/${snapId}`, {
    method: "DELETE",
  });
  if (!resp.ok) throw new Error("Delete failed");
  return resp.json();
}
```

- [ ] **Step 2: Replace `dashboard/src/components/SnapCard.jsx`**

```jsx
import { useState } from "react";
import { updateSnap, deleteSnap } from "../api";

export default function SnapCard({ snap, onRetry, onChanged }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(snap.title);
  const [category, setCategory] = useState(snap.category || "");
  const [tagsText, setTagsText] = useState(snap.tags.join(", "));
  const [error, setError] = useState("");

  async function handleSave() {
    setError("");
    try {
      const tags = tagsText.split(",").map((t) => t.trim()).filter(Boolean);
      await updateSnap(snap.id, { title, category, tags });
      setEditing(false);
      onChanged();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDelete() {
    if (!window.confirm("Delete this snap?")) return;
    setError("");
    try {
      await deleteSnap(snap.id);
      onChanged();
    } catch (err) {
      setError(err.message);
    }
  }

  if (editing) {
    return (
      <div className="snap-card">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" />
        <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Category" />
        <input value={tagsText} onChange={(e) => setTagsText(e.target.value)} placeholder="tag1, tag2" />
        {error && <p role="alert">{error}</p>}
        <button onClick={handleSave}>Save</button>
        <button onClick={() => setEditing(false)}>Cancel</button>
      </div>
    );
  }

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
      {error && <p role="alert">{error}</p>}
      <a href={snap.url} target="_blank" rel="noreferrer">
        Source
      </a>
      <button onClick={() => setEditing(true)}>Edit</button>
      <button onClick={handleDelete}>Delete</button>
    </div>
  );
}
```

- [ ] **Step 3: Modify `dashboard/src/pages/Snaps.jsx`** to pass `onChanged`

Find the `<SnapCard ... />` usage and add the `onChanged` prop:

```jsx
        {snaps.map((snap) => (
          <SnapCard
            key={snap.id}
            snap={snap}
            onRetry={() => handleRetry(snap.id)}
            onChanged={loadAll}
          />
        ))}
```

- [ ] **Step 4: Manually verify**

With the backend running and a snap captured:

```bash
cd dashboard
npm run dev
```

Confirm: clicking "Edit" shows title/category/tags inputs pre-filled with current values; "Save" persists changes and the card updates; "Cancel" discards changes; "Delete" prompts a confirm dialog and, on confirm, removes the card from the list.

---

### Task 4: Tag/category filter

**Files:**
- Modify: `dashboard/src/components/SnapCard.jsx`
- Modify: `dashboard/src/pages/Snaps.jsx`

**Interfaces:**
- Consumes: Task 3's `SnapCard`/`Snaps.jsx`.
- Produces: `SnapCard` gains `onFilterTag(tag: string)` and `onFilterCategory(category: string)` props; `Snaps.jsx` gains filter state `{type: "tag"|"category", value: string} | null`.

- [ ] **Step 1: Modify `dashboard/src/components/SnapCard.jsx`** — make tags/category clickable

Replace the function signature and the tag-rendering `<div>` block:

```jsx
export default function SnapCard({ snap, onRetry, onChanged, onFilterTag, onFilterCategory }) {
```

```jsx
      <div>
        {snap.category && (
          <button className="chip category" onClick={() => onFilterCategory(snap.category)}>
            {snap.category}
          </button>
        )}
        {snap.tags.map((tag) => (
          <button key={tag} className="chip tag" onClick={() => onFilterTag(tag)}>
            {tag}
          </button>
        ))}
      </div>
```

(This replaces the `<div>{snap.tags.map(...)}</div>` block from Task 3 — same position in the non-editing render, right after the retry button.)

- [ ] **Step 2: Modify `dashboard/src/pages/Snaps.jsx`** — add filter state and wiring

Add `filter` state (with the other `useState` calls):

```jsx
  const [filter, setFilter] = useState(null);
```

Add the filtered-list computation (after `handleRetry`, before the `return`):

```jsx
  const visibleSnaps = filter
    ? snaps.filter((snap) =>
        filter.type === "tag" ? snap.tags.includes(filter.value) : snap.category === filter.value
      )
    : snaps;
```

Replace the `return (...)` block:

```jsx
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
      {filter && (
        <p>
          Filtered by {filter.type}: <strong>{filter.value}</strong>{" "}
          <button onClick={() => setFilter(null)}>Clear filter ×</button>
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      <div>
        {visibleSnaps.map((snap) => (
          <SnapCard
            key={snap.id}
            snap={snap}
            onRetry={() => handleRetry(snap.id)}
            onChanged={loadAll}
            onFilterTag={(tag) => setFilter({ type: "tag", value: tag })}
            onFilterCategory={(category) => setFilter({ type: "category", value: category })}
          />
        ))}
      </div>
    </div>
  );
```

- [ ] **Step 3: Manually verify**

With multiple snaps captured (varying tags/categories):

```bash
cd dashboard
npm run dev
```

Confirm: clicking a tag or category chip filters the list to matching snaps and shows the "Filtered by ..." banner; "Clear filter ×" returns to the full list; filtering combines correctly with a prior search (filter applies on top of whatever `snaps` currently holds).

---

### Task 5: Review streak/stats view

**Files:**
- Modify: `dashboard/src/api.js`
- Create: `dashboard/src/pages/Stats.jsx`
- Modify: `dashboard/src/App.jsx`

**Interfaces:**
- Consumes: backend `GET /api/review/stats` (Task 1).
- Produces: `api.getReviewStats() -> Promise<{current_streak, longest_streak, total_reviewed, reviewed_today}>`; `<Stats />` component.

- [ ] **Step 1: Add to `dashboard/src/api.js`** (after `deleteSnap`)

```javascript
export async function getReviewStats() {
  const resp = await authedFetch(`${API_URL}/api/review/stats`);
  if (!resp.ok) throw new Error("Failed to load stats");
  return resp.json();
}
```

- [ ] **Step 2: Create `dashboard/src/pages/Stats.jsx`**

```jsx
import { useEffect, useState } from "react";
import { getReviewStats } from "../api";

export default function Stats() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getReviewStats()
      .then(setStats)
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <p role="alert">{error}</p>;
  if (!stats) return <p>Loading...</p>;

  return (
    <div className="stats">
      <p>
        Current streak: {stats.current_streak} day{stats.current_streak === 1 ? "" : "s"}
      </p>
      <p>
        Longest streak: {stats.longest_streak} day{stats.longest_streak === 1 ? "" : "s"}
      </p>
      <p>Total reviewed: {stats.total_reviewed}</p>
      <p>Reviewed today: {stats.reviewed_today}</p>
    </div>
  );
}
```

- [ ] **Step 3: Modify `dashboard/src/App.jsx`**

```jsx
import { useState } from "react";
import Login from "./pages/Login";
import Snaps from "./pages/Snaps";
import Review from "./pages/Review";
import Stats from "./pages/Stats";
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
          <button onClick={() => setView("stats")}>Stats</button>
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
      {view === "stats" && <Stats />}
    </div>
  );
}

export default App;
```

- [ ] **Step 4: Manually verify**

With the backend running and at least one graded review from earlier testing:

```bash
cd dashboard
npm run dev
```

Click the "Stats" tab. Confirm the four numbers render and are non-zero if you've graded at least one card today; grade another card in the Review tab and confirm "Reviewed today" / "Total reviewed" increment on revisiting Stats.

---

### Task 6: Extension — Chrome-only + keyboard shortcut capture

**Files:**
- Modify: `extension/manifest.json`
- Modify: `extension/background.js`
- Modify: `README.md`

**Interfaces:**
- Consumes: existing `captureSelection(text, url, title)` function in `background.js` (Task 10 of the v1 plan).
- Produces: a `capture-selection` Chrome command bound to `Ctrl+Shift+S` / `Cmd+Shift+S`.

- [ ] **Step 1: Replace `extension/manifest.json`**

```json
{
  "manifest_version": 3,
  "name": "SnapStack",
  "version": "1.0.0",
  "description": "Capture highlighted text into SnapStack for later review.",
  "icons": { "128": "icon128.png" },
  "permissions": ["contextMenus", "storage", "notifications", "activeTab", "scripting"],
  "host_permissions": ["http://localhost:5100/*"],
  "background": {
    "service_worker": "background.js"
  },
  "action": {
    "default_popup": "popup/popup.html",
    "default_title": "SnapStack"
  },
  "commands": {
    "capture-selection": {
      "suggested_key": { "default": "Ctrl+Shift+S", "mac": "Command+Shift+S" },
      "description": "Save the current text selection to SnapStack"
    }
  }
}
```

(Drops the `browser_specific_settings` block entirely — Chrome only. Adds `activeTab` and `scripting` permissions, and the `commands` block.)

- [ ] **Step 2: Modify `extension/background.js`** — add the command listener

Add this block after the existing `chrome.contextMenus.onClicked.addListener(...)` block, before the `captureSelection` function definition:

```javascript
chrome.commands.onCommand.addListener(async (command) => {
  if (command !== "capture-selection") return;
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;
  const [{ result: selectionText }] = await chrome.scripting.executeScript({
    target: { tabId: tab.id },
    func: () => window.getSelection().toString(),
  });
  if (!selectionText) return;
  await captureSelection(selectionText, tab.url, tab.title);
});
```

- [ ] **Step 3: Modify `README.md`** — Chrome-only extension section

Replace the `### Extension` section:

```markdown
### Extension (Chrome only)

1. `chrome://extensions` → enable Developer mode.
2. "Load unpacked" → select the `extension/` directory.
3. Click the SnapStack toolbar icon and log in with the user you created above.
4. Highlight text on any page → right-click → "Add to SnapStack", or press `Ctrl+Shift+S`
   (`Cmd+Shift+S` on Mac) to capture without the menu. Remap the shortcut anytime at
   `chrome://extensions/shortcuts`.
```

- [ ] **Step 4: Manually verify**

In `chrome://extensions`, click the reload icon on the SnapStack extension to pick up the manifest/background changes. Highlight text on any page and press `Ctrl+Shift+S`. Confirm the same "Saved." notification appears as the right-click path, and that the capture shows up in the dashboard's Snaps view. Also confirm `chrome://extensions/shortcuts` lists "Save the current text selection to SnapStack" bound to the shortcut.
