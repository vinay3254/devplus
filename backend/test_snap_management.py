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
