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
