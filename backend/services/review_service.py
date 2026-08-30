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
