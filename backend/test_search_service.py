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
    conn.execute("DELETE FROM snaps")
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
