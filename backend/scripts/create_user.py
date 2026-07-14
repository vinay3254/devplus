import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from database import get_connection, init_db
from werkzeug.security import generate_password_hash


def main():
    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")

    init_db(config.DB_PATH)
    conn = get_connection(config.DB_PATH)
    conn.execute(
        "INSERT OR REPLACE INTO users (username, password_hash) VALUES (?, ?)",
        (username, generate_password_hash(password)),
    )
    conn.commit()
    conn.close()
    print(f"User '{username}' created.")


if __name__ == "__main__":
    main()
