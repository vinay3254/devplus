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
