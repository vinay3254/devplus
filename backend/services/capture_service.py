import datetime

from flask import Blueprint, request, jsonify

import config
from database import get_connection
from services.auth import require_auth
from services.ollama_client import summarize_and_tag, embed, OllamaError
from services import search_index

bp = Blueprint("capture", __name__)


def _now_iso():
    return datetime.datetime.utcnow().isoformat()


def save_snap(url, title, raw_text):
    summary, category, tags = None, None, []
    try:
        summary, category, tags = summarize_and_tag(
            raw_text, config.OLLAMA_API_URL, config.OLLAMA_MODEL
        )
    except OllamaError:
        pass

    now = _now_iso()
    conn = get_connection(config.DB_PATH)
    cursor = conn.execute(
        """
        INSERT INTO snaps (url, title, raw_text, summary, category, tags, created_at, due_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (url, title, raw_text, summary, category, ",".join(tags), now, now),
    )
    snap_id = cursor.lastrowid
    conn.commit()
    conn.close()

    if summary is not None:
        _index_snap(snap_id, raw_text)

    return snap_id


def _index_snap(snap_id, raw_text):
    try:
        vector = embed(raw_text, config.OLLAMA_API_URL, config.OLLAMA_EMBED_MODEL)
        search_index.add(snap_id, vector)
    except OllamaError:
        pass


@bp.route("/api/snaps", methods=["POST"])
@require_auth
def create_snap():
    data = request.get_json(force=True) or {}
    url = data.get("url", "")
    title = data.get("title", "")
    raw_text = data.get("text", "")
    if not raw_text.strip():
        return jsonify({"error": "text is required"}), 400

    snap_id = save_snap(url, title, raw_text)
    return jsonify({"id": snap_id}), 201


@bp.route("/api/snaps/<int:snap_id>/retry-summary", methods=["POST"])
@require_auth
def retry_summary(snap_id):
    conn = get_connection(config.DB_PATH)
    row = conn.execute("SELECT raw_text FROM snaps WHERE id = ?", (snap_id,)).fetchone()
    if row is None:
        conn.close()
        return jsonify({"error": "not found"}), 404

    try:
        summary, category, tags = summarize_and_tag(
            row["raw_text"], config.OLLAMA_API_URL, config.OLLAMA_MODEL
        )
    except OllamaError:
        conn.close()
        return jsonify({"error": "summarization still failing"}), 502

    conn.execute(
        "UPDATE snaps SET summary = ?, category = ?, tags = ? WHERE id = ?",
        (summary, category, ",".join(tags), snap_id),
    )
    conn.commit()
    conn.close()
    _index_snap(snap_id, row["raw_text"])
    return jsonify({"status": "updated"})
