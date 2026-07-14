import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

import config
config.DB_PATH = tempfile.mktemp(suffix=".db")

from flask import Flask, jsonify
from database import init_db, get_connection
from werkzeug.security import generate_password_hash
from services.auth import require_auth, create_token
from app import create_app


def make_protected_test_app():
    app = Flask(__name__)

    @app.route("/protected")
    @require_auth
    def protected():
        return jsonify({"ok": True})

    return app


def seed_user():
    init_db(config.DB_PATH)
    conn = get_connection(config.DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO users (username, password_hash) VALUES (?, ?)",
        ("testuser", generate_password_hash("testpass")),
    )
    conn.commit()
    conn.close()


def test_protected_route_rejects_missing_token():
    app = make_protected_test_app()
    client = app.test_client()
    resp = client.get("/protected")
    assert resp.status_code == 401
    print("PASS: missing token rejected")


def test_protected_route_accepts_valid_token():
    app = make_protected_test_app()
    client = app.test_client()
    token = create_token("testuser")
    resp = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    print("PASS: valid token accepted")


def test_login_returns_token_for_valid_credentials():
    seed_user()
    app = create_app()
    client = app.test_client()
    resp = client.post(
        "/api/auth/login", json={"username": "testuser", "password": "testpass"}
    )
    assert resp.status_code == 200
    assert "token" in resp.get_json()
    print("PASS: valid login returns token")


def test_login_rejects_invalid_password():
    seed_user()
    app = create_app()
    client = app.test_client()
    resp = client.post(
        "/api/auth/login", json={"username": "testuser", "password": "wrong"}
    )
    assert resp.status_code == 401
    print("PASS: invalid password rejected")


if __name__ == "__main__":
    test_protected_route_rejects_missing_token()
    test_protected_route_accepts_valid_token()
    test_login_returns_token_for_valid_credentials()
    test_login_rejects_invalid_password()
    print("All auth tests passed.")
