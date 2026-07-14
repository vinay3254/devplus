from flask import Blueprint, request, jsonify

import config
from database import get_connection
from services.auth import require_auth
from services.ollama_client import embed, OllamaError
from services import search_index

bp = Blueprint("snaps", __name__)

# L2 distance threshold below which a FAISS hit counts as a semantic match.
SIMILARITY_THRESHOLD = 0.8


def _row_to_dict(row):
    return {
        "id": row["id"],
        "url": row["url"],
        "title": row["title"],
        "raw_text": row["raw_text"],
        "summary": row["summary"],
        "category": row["category"],
        "tags": row["tags"].split(",") if row["tags"] else [],
        "created_at": row["created_at"],
        "due_date": row["due_date"],
    }


@bp.route("/api/snaps", methods=["GET"])
@require_auth
def list_snaps():
    conn = get_connection(config.DB_PATH)
    rows = conn.execute("SELECT * FROM snaps ORDER BY created_at DESC").fetchall()
    conn.close()
    return jsonify([_row_to_dict(r) for r in rows])


@bp.route("/api/snaps/<int:snap_id>", methods=["GET"])
@require_auth
def get_snap(snap_id):
    conn = get_connection(config.DB_PATH)
    row = conn.execute("SELECT * FROM snaps WHERE id = ?", (snap_id,)).fetchone()
    conn.close()
    if row is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(_row_to_dict(row))


@bp.route("/api/snaps/search", methods=["GET"])
@require_auth
def search_snaps():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify([])

    conn = get_connection(config.DB_PATH)

    try:
        vector = embed(query, config.OLLAMA_API_URL, config.OLLAMA_EMBED_MODEL)
        hits = search_index.search(vector, k=20)
        matches = [snap_id for snap_id, distance in hits if distance <= SIMILARITY_THRESHOLD]
    except OllamaError:
        matches = []

    if matches:
        placeholders = ",".join("?" * len(matches))
        rows = conn.execute(
            f"SELECT * FROM snaps WHERE id IN ({placeholders})", matches
        ).fetchall()
        rows_by_id = {r["id"]: r for r in rows}
        ordered = [rows_by_id[i] for i in matches if i in rows_by_id]
    else:
        like = f"%{query}%"
        ordered = conn.execute(
            "SELECT * FROM snaps WHERE title LIKE ? OR tags LIKE ? OR category LIKE ? "
            "ORDER BY created_at DESC",
            (like, like, like),
        ).fetchall()

    conn.close()
    return jsonify([_row_to_dict(r) for r in ordered])
