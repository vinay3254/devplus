from flask import Flask, jsonify
from flask_cors import CORS

import config
from database import init_db, get_connection


def create_app():
    app = Flask(__name__)
    # Wildcard CORS: local-only single-user tool, extension origin
    # (chrome-extension://<id>) varies per install so can't be pinned in advance.
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    init_db(config.DB_PATH)

    from services.auth import bp as auth_bp
    from services.capture_service import bp as capture_bp
    from services.search_service import bp as snaps_bp
    from services.review_service import bp as review_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(capture_bp)
    app.register_blueprint(snaps_bp)
    app.register_blueprint(review_bp)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app


app = create_app()


def _startup_consistency_check():
    """Rebuild the FAISS index from SQLite if vector count drifts from row count.
    Only runs when launching the real server (python app.py) — not on import,
    so tests never trigger a live Ollama call."""
    from services import search_index
    from services.ollama_client import embed, OllamaError

    conn = get_connection(config.DB_PATH)
    summarized = conn.execute(
        "SELECT id, raw_text FROM snaps WHERE summary IS NOT NULL"
    ).fetchall()
    conn.close()

    if search_index.count() == len(summarized):
        return

    rows = []
    for row in summarized:
        try:
            vector = embed(row["raw_text"], config.OLLAMA_API_URL, config.OLLAMA_EMBED_MODEL)
            rows.append((row["id"], vector))
        except OllamaError:
            print(f"WARNING: could not re-embed snap {row['id']} during startup rebuild")
    search_index.rebuild_from_rows(rows)


if __name__ == "__main__":
    _startup_consistency_check()
    app.run(port=config.PORT, debug=True)
