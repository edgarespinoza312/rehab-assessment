import os
import secrets
from collections.abc import Mapping

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def resolve_security_settings(environ: Mapping[str, str]) -> tuple[str, bool]:
    """Resolve the Flask session secret and cookie transport policy.

    Local development can use an ephemeral secret and plain HTTP. Production
    must provide a persistent secret and cannot explicitly disable secure cookies.
    """
    deployment_environment = environ.get("REVALIV_ENV", "development").strip().lower()
    is_production = deployment_environment in {"prod", "production"}

    configured_secret = environ.get("REVALIV_SECRET_KEY", "").strip()
    if is_production and not configured_secret:
        raise RuntimeError(
            "REVALIV_SECRET_KEY must be set to a persistent secret in production."
        )

    secure_cookie_setting = environ.get("REVALIV_SECURE_COOKIES")
    if is_production and secure_cookie_setting is not None:
        if secure_cookie_setting.strip() != "1":
            raise RuntimeError(
                "REVALIV_SECURE_COOKIES must be set to '1' in production."
            )
        secure_cookies = True
    elif is_production:
        secure_cookies = True
    else:
        secure_cookies = secure_cookie_setting == "1"

    return configured_secret or secrets.token_hex(32), secure_cookies


_SECRET_KEY, _SESSION_COOKIE_SECURE = resolve_security_settings(os.environ)


class Config:
    # Bound request bodies to reduce memory pressure from oversized submissions.
    MAX_CONTENT_LENGTH = 1_048_576

    SECRET_KEY = _SECRET_KEY
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _SESSION_COOKIE_SECURE

    REVALIV_ENV = os.environ.get("REVALIV_ENV", "development").strip().lower()
    REVALIV_PUBLIC_BASE_URL = os.environ.get(
        "REVALIV_PUBLIC_BASE_URL", ""
    ).strip().rstrip("/")
    REVALIV_SMTP_HOST = os.environ.get("REVALIV_SMTP_HOST", "").strip()
    REVALIV_SMTP_PORT = int(os.environ.get("REVALIV_SMTP_PORT", "587"))
    REVALIV_SMTP_USERNAME = os.environ.get("REVALIV_SMTP_USERNAME", "")
    REVALIV_SMTP_PASSWORD = os.environ.get("REVALIV_SMTP_PASSWORD", "")
    REVALIV_SMTP_FROM = os.environ.get("REVALIV_SMTP_FROM", "").strip()
    REVALIV_SMTP_STARTTLS = os.environ.get(
        "REVALIV_SMTP_STARTTLS", "1"
    ).strip().lower() in {"1", "true", "yes"}
    REVALIV_SMTP_USE_SSL = os.environ.get(
        "REVALIV_SMTP_USE_SSL", "0"
    ).strip().lower() in {"1", "true", "yes"}
    PASSWORD_RESET_TOKEN_MAX_AGE = 60 * 60

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "REVALIV_DATABASE_URI",
        f"sqlite:///{os.path.join(BASE_DIR, 'neuromotion.db')}",
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False
