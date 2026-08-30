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
    conn.execute("DELETE FROM review_log")
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
