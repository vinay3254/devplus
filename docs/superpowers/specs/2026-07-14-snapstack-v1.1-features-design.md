# SnapStack v1.1 — Additional Features Design

Date: 2026-07-14
Status: Approved

## Summary

Four additions to the SnapStack v1 MVP, plus a scope reduction to Chrome-only:

1. Tag/category filter on the dashboard.
2. Keyboard-shortcut capture (no right-click required).
3. Review streak/stats.
4. Edit/delete a snap.
5. Drop Firefox support — Chrome only.

## Scope

In scope: the five items above.

Out of scope (explicitly deferred):
- Editing `raw_text`/`summary` by hand (use the existing "Retry summarization" flow instead).
- Soft-delete/archive/undo — delete is permanent.
- In-app shortcut configuration UI — Chrome's own `chrome://extensions/shortcuts` page covers remapping.
- Streak "freeze"/grace-day mechanics, or excluding "Again" grades from the streak.
- Charts/graphs for stats — four plain numbers only.
- Firefox manifest/testing — dropped entirely per the Chrome-only decision.

## Backend changes

### `review_log` table (new)

```sql
CREATE TABLE IF NOT EXISTS review_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    snap_id INTEGER NOT NULL,
    graded_at TEXT NOT NULL,
    grade TEXT NOT NULL
);
```

`graded_at` is date-only (`datetime.date.today().isoformat()`), matching `snaps.due_date`'s existing date-only convention. `POST /api/review/<id>/grade` inserts one row here, in addition to its existing SM-2 update — this is purely additive, no change to the existing grading response shape.

### `GET /api/review/stats` (new)

Returns:
```json
{"current_streak": 3, "longest_streak": 7, "total_reviewed": 42, "reviewed_today": 2}
```

Computed by reading all distinct `graded_at` dates from `review_log` (ordered descending), then:
- `total_reviewed` = count of all rows in `review_log` (not distinct dates — every grade action counts).
- `reviewed_today` = count of rows where `graded_at` = today.
- `current_streak` = walk backward day-by-day from today (or yesterday, if today has no reviews yet) counting consecutive days present in the distinct-dates set, stopping at the first gap.
- `longest_streak` = scan the full sorted distinct-dates list once, tracking the longest run of consecutive calendar days.
- Zero review history returns all-zero, not an error.

### `PATCH /api/snaps/<id>` (new)

Body: any subset of `{"title": str, "category": str, "tags": [str]}`. Updates only the provided fields. `tags` is stored the same way capture already stores it (comma-joined string). 404 if the snap doesn't exist. Does not touch `raw_text`/`summary`/FAISS indexing — editing metadata doesn't change what the embedding was computed from.

### `DELETE /api/snaps/<id>` (new)

Deletes the row from `snaps` and calls the new `search_index.remove(snap_id)`. 404 if the snap doesn't exist.

### `search_index.remove(snap_id)` (new)

```python
def remove(snap_id):
    with _lock:
        index = _load()
        index.remove_ids(np.array([snap_id], dtype="int64"))
        os.makedirs(os.path.dirname(config.FAISS_INDEX_PATH), exist_ok=True)
        faiss.write_index(index, config.FAISS_INDEX_PATH)
```

Mirrors `add()`'s locking/persist pattern. Removing an id that was never indexed (e.g. a snap whose summarization failed) is a no-op — FAISS's `remove_ids` silently ignores ids not present.

## Dashboard changes

### Tag/category filter (`Snaps.jsx`, `SnapCard.jsx`)

`Snaps.jsx` gets `const [filter, setFilter] = useState(null)` where `filter` is `{type: "tag"|"category", value: string} | null`. Tag chips and the category (rendered as a chip too, styled distinctly) become clickable buttons calling `setFilter({type, value})`. The rendered list is `snaps.filter(...)` applied client-side on top of whatever `snaps` currently holds (full list or search results) — no new fetch. A "Clear filter ×" button appears next to the search bar when `filter` is non-null.

### Edit/delete (`SnapCard.jsx`)

`SnapCard` gets local state `editing: bool` and, while editing, renders inputs for title/category/tags (tags as a single comma-separated text input, split/joined on save) instead of the static text. "Save" calls the new `api.updateSnap(id, {title, category, tags})` (`PATCH`) then the parent's `onChanged` callback to refetch. "Delete" calls `window.confirm("Delete this snap?")`; on confirm, calls `api.deleteSnap(id)` (`DELETE`) then `onChanged`.

### Stats view (`Stats.jsx`, new)

New page, added as a third `nav` button in `App.jsx` ("Stats") alongside Snaps/Review. On mount, calls `api.getReviewStats()` and renders the four numbers as plain labeled values (`Current streak`, `Longest streak`, `Total reviewed`, `Reviewed today`) — no chart library, no historical graph.

## Extension changes

### Chrome-only

`manifest.json` drops the `browser_specific_settings` block entirely. README's extension setup section drops the Firefox (`about:debugging`) step, keeping only Chrome's `chrome://extensions` flow.

### Keyboard shortcut capture

`manifest.json` gets:
```json
"commands": {
  "capture-selection": {
    "suggested_key": { "default": "Ctrl+Shift+S", "mac": "Command+Shift+S" },
    "description": "Save the current text selection to SnapStack"
  }
},
"permissions": ["contextMenus", "storage", "notifications", "activeTab", "scripting"]
```

`background.js` adds:
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

Reuses the existing `captureSelection()` function unchanged — same auth/error/notification handling as the right-click path. An empty selection silently no-ops, matching the existing `!info.selectionText` guard on the context-menu path.

## Error handling (new surfaces only)

- `PATCH`/`DELETE /api/snaps/<id>` on a missing id → `404 {"error": "not found"}`, matching the existing pattern in `search_service.py`/`capture_service.py`.
- Hotkey with no active selection → no-op, no error surfaced (consistent with the existing right-click behavior).
- `GET /api/review/stats` with an empty `review_log` → `{"current_streak": 0, "longest_streak": 0, "total_reviewed": 0, "reviewed_today": 0}`, not an error.
- Delete/edit network failures on the dashboard surface the same inline `role="alert"` error pattern already used by `Snaps.jsx`/`Review.jsx`.

## Testing

Following the existing convention (standalone `test_*.py`, plain `assert`, run via `python test_x.py`):

- `test_review_service.py` gets new cases for `GET /api/review/stats` (streak math: consecutive days, a gap, longest vs current) and the `review_log` insert on grade.
- `test_search_service.py` (or a new `test_snap_management.py`) gets cases for `PATCH`/`DELETE` — including the FAISS-removal behavior via a mocked `search_index`.
- Dashboard: no test runner, manual verification per existing convention — filter chips, edit/save, delete-with-confirm, stats numbers.
- Extension: no automated tests — manual checklist addition: trigger the hotkey with text selected, confirm the same "Saved." notification as right-click.
