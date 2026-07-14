from flask import Flask, jsonify
from flask_cors import CORS

import config
from database import init_db


def create_app():
    app = Flask(__name__)
    # Wildcard CORS: local-only single-user tool, extension origin
    # (chrome-extension://<id>) varies per install so can't be pinned in advance.
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    init_db(config.DB_PATH)

    from services.auth import bp as auth_bp
    from services.capture_service import bp as capture_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(capture_bp)

    @app.route("/api/health")
    def health():
        return jsonify({"status": "ok"})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(port=config.PORT, debug=True)
