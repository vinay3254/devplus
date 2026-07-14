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
    conn.execute("DELETE FROM snaps")
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
