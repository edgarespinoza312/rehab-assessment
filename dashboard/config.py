import os
import secrets

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get(
        "REVALIV_SECRET_KEY",
        secrets.token_hex(32),
    )
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("REVALIV_SECURE_COOKIES", "0") == "1"

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "REVALIV_DATABASE_URI",
        f"sqlite:///{os.path.join(BASE_DIR, 'neuromotion.db')}",
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False