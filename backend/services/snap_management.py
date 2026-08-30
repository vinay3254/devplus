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
