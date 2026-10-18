"""Expiring, single-use password reset tokens and email delivery."""

from __future__ import annotations

import hashlib
import hmac
import smtplib
import ssl
from email.message import EmailMessage
from urllib.parse import urljoin, urlsplit

from flask import current_app, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer

from dashboard.database import db
from dashboard.models import User


_TOKEN_SALT = "revaliv-password-reset-v1"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        current_app.config["SECRET_KEY"],
        salt=_TOKEN_SALT,
    )


def _password_fingerprint(password_hash: str) -> str:
    secret = current_app.config["SECRET_KEY"]
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    return hmac.new(
        secret,
        password_hash.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def generate_password_reset_token(user: User) -> str:
    """Create a signed token tied to the account's current password hash."""
    if (
        not isinstance(user.user_id, int)
        or user.status != "ACTIVE"
        or not user.password_hash
    ):
        raise ValueError("user cannot receive a password reset token")
    return _serializer().dumps({
        "user_id": user.user_id,
        "password_fingerprint": _password_fingerprint(user.password_hash),
    })


def verify_password_reset_token(token: str) -> User | None:
    """Return the active account only while its token is valid and unused."""
    if not isinstance(token, str) or not token:
        return None
    try:
        payload = _serializer().loads(
            token,
            max_age=current_app.config["PASSWORD_RESET_TOKEN_MAX_AGE"],
        )
    except (BadSignature, TypeError, ValueError):
        return None

    if not isinstance(payload, dict):
        return None
    user_id = payload.get("user_id")
    fingerprint = payload.get("password_fingerprint")
    if (
        isinstance(user_id, bool)
        or not isinstance(user_id, int)
        or user_id <= 0
        or not isinstance(fingerprint, str)
    ):
        return None

    user = db.session.get(User, user_id)
    if (
        user is None
        or user.status != "ACTIVE"
        or not user.email
        or not user.password_hash
    ):
        return None
    expected = _password_fingerprint(user.password_hash)
    if not hmac.compare_digest(fingerprint, expected):
        return None
    return user


def build_password_reset_url(token: str) -> str:
    """Build a reset link from the configured public origin in production."""
    path = url_for("reset_password", token=token)
    base_url = current_app.config.get("REVALIV_PUBLIC_BASE_URL", "").strip()
    production = current_app.config.get("REVALIV_ENV") in {"prod", "production"}

    if not base_url:
        if production:
            raise RuntimeError(
                "REVALIV_PUBLIC_BASE_URL must be set in production."
            )
        return url_for("reset_password", token=token, _external=True)

    parsed = urlsplit(base_url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError("REVALIV_PUBLIC_BASE_URL must be a valid URL origin.")
    if production and parsed.scheme != "https":
        raise RuntimeError("REVALIV_PUBLIC_BASE_URL must use HTTPS in production.")

    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def send_password_reset_email(recipient: str, reset_url: str) -> None:
    """Send a reset email through SMTP, or log the link in local development."""
    host = current_app.config.get("REVALIV_SMTP_HOST", "").strip()
    sender = current_app.config.get("REVALIV_SMTP_FROM", "").strip()
    username = current_app.config.get("REVALIV_SMTP_USERNAME", "")
    password = current_app.config.get("REVALIV_SMTP_PASSWORD", "")
    production = current_app.config.get("REVALIV_ENV") in {"prod", "production"}

    if not host or not sender:
        if production:
            raise RuntimeError(
                "REVALIV_SMTP_HOST and REVALIV_SMTP_FROM must be configured."
            )
        current_app.logger.warning(
            "SMTP is not configured; development-only password reset link: %s",
            reset_url,
        )
        return

    message = EmailMessage()
    message["Subject"] = "Reset your Revaliv password"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        "A password reset was requested for your Revaliv account.\n\n"
        f"Use this link within one hour to choose a new password:\n{reset_url}\n\n"
        "If you did not request this, you can ignore this message."
    )

    timeout = 15
    use_ssl = current_app.config.get("REVALIV_SMTP_USE_SSL", False)
    use_starttls = current_app.config.get("REVALIV_SMTP_STARTTLS", True)
    context = ssl.create_default_context()
    smtp_class = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
    options = {"timeout": timeout}
    if use_ssl:
        options["context"] = context

    with smtp_class(host, current_app.config["REVALIV_SMTP_PORT"], **options) as server:
        server.ehlo()
        if use_starttls and not use_ssl:
            server.starttls(context=context)
            server.ehlo()
        if username:
            server.login(username, password)
        server.send_message(message)
