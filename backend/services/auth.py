import datetime
from functools import wraps

import jwt
from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash

import config
from database import get_connection

bp = Blueprint("auth", __name__)


def create_token(username):
    payload = {
        "username": username,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(days=30),
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def verify_token(token):
    return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])


def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "missing or invalid Authorization header"}), 401
        token = auth_header.split(" ", 1)[1]
        try:
            verify_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "invalid token"}), 401
        return f(*args, **kwargs)

    return wrapper


@bp.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(force=True) or {}
    username = data.get("username", "")
    password = data.get("password", "")

    conn = get_connection(config.DB_PATH)
    row = conn.execute(
        "SELECT username, password_hash FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()

    if row is None or not check_password_hash(row["password_hash"], password):
        return jsonify({"error": "invalid username or password"}), 401

    token = create_token(row["username"])
    return jsonify({"token": token})
