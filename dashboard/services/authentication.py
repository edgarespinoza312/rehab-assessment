"""Application authentication and server-owned session identity."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from functools import wraps

from flask import (
    abort,
    current_app,
    g,
    jsonify,
    redirect,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from dashboard.database import db
from dashboard.models import Patient, User
from dashboard.services.identity import (
    AuthorizationService,
    Capability,
    IdentityContext,
    anonymous_identity,
    identity_from_user,
)

SESSION_USER_KEY = "revaliv_user_id"
CSRF_SESSION_KEY = "revaliv_csrf_token"
RUNTIME_SESSION_KEY = "revaliv_runtime_id"
SESSION_AUTH_FINGERPRINT_KEY = "revaliv_auth_fingerprint"
MAX_PASSWORD_LENGTH = 1024


def hash_password(password: str) -> str:
    if not isinstance(password, str) or len(password) < 8:
        raise ValueError("password must contain at least 8 characters")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(
            f"password must be at most {MAX_PASSWORD_LENGTH} characters"
        )
    return generate_password_hash(password)


def verify_password(user: User, password: str) -> bool:
    return bool(
        user.password_hash
        and isinstance(password, str)
        and len(password) <= MAX_PASSWORD_LENGTH
        and check_password_hash(user.password_hash, password)
    )


def _session_auth_fingerprint(password_hash: str) -> str:
    """Bind a browser session to the account's current password hash.

    The keyed fingerprint stays opaque in Flask's signed client-side session.
    Changing the password makes all previously issued session cookies stale.
    """
    secret = current_app.config["SECRET_KEY"]
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    return hmac.new(
        secret,
        password_hash.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def load_identity() -> IdentityContext:
    user_id = session.get(SESSION_USER_KEY)
    if isinstance(user_id, bool) or not isinstance(user_id, int):
        return anonymous_identity()
    user = db.session.get(User, user_id)
    if (
        user is None
        or user.status != "ACTIVE"
        or not isinstance(user.password_hash, str)
        or not user.password_hash
    ):
        session.pop(SESSION_USER_KEY, None)
        session.pop(SESSION_AUTH_FINGERPRINT_KEY, None)
        return anonymous_identity()

    stored_fingerprint = session.get(SESSION_AUTH_FINGERPRINT_KEY)
    expected_fingerprint = _session_auth_fingerprint(user.password_hash)
    if (
        not isinstance(stored_fingerprint, str)
        or not secrets.compare_digest(stored_fingerprint, expected_fingerprint)
    ):
        # Missing fingerprints also revoke sessions issued before this guard
        # existed. A valid login must establish the current fingerprint.
        session.pop(SESSION_USER_KEY, None)
        session.pop(SESSION_AUTH_FINGERPRINT_KEY, None)
        return anonymous_identity()

    return identity_from_user(user)


def current_identity() -> IdentityContext:
    identity = getattr(g, "identity_context", None)
    if identity is None:
        identity = load_identity()
        g.identity_context = identity
    return identity


def login_user(user: User) -> None:
    session.clear()
    session[SESSION_USER_KEY] = user.user_id
    session[SESSION_AUTH_FINGERPRINT_KEY] = _session_auth_fingerprint(user.password_hash)
    session[CSRF_SESSION_KEY] = secrets.token_urlsafe(32)
    session.permanent = True
    g.identity_context = identity_from_user(user)


def logout_user() -> None:
    session.clear()
    g.identity_context = anonymous_identity()


def csrf_token() -> str:
    token = session.get(CSRF_SESSION_KEY)
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        session[CSRF_SESSION_KEY] = token
    return token


def valid_csrf_token() -> bool:
    supplied = request.form.get("csrf_token") or request.headers.get(
        "X-CSRF-Token"
    )
    expected = session.get(CSRF_SESSION_KEY)
    return (
        isinstance(supplied, str)
        and bool(supplied)
        and isinstance(expected, str)
        and bool(expected)
        and secrets.compare_digest(supplied, expected)
    )


def require_csrf() -> None:
    if not valid_csrf_token():
        abort(400, description="invalid CSRF token")


def _unauthorized_response():
    if request.path.startswith("/api/") or request.is_json:
        return jsonify({"error": "authentication required"}), 401
    return redirect(url_for("login", next=request.full_path))


def require_auth(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_identity().is_authenticated:
            return _unauthorized_response()
        return view(*args, **kwargs)

    return wrapped


def require_authenticated_identity():
    return require_auth


def require_capability(capability: Capability, *, patient_arg="patient_id"):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            identity = current_identity()
            if not identity.is_authenticated:
                return _unauthorized_response()
            patient_id = kwargs.get(patient_arg)
            # Preserve the API's 404 contract for nonexistent patient IDs,
            # while still returning 403 for existing patients outside the
            # caller's authorization scope.
            if patient_id is not None and db.session.get(Patient, patient_id) is None:
                if request.path.startswith("/api/"):
                    return jsonify({"error": f"patient {patient_id} does not exist"}), 404
                abort(404)
            if not AuthorizationService.can(
                identity,
                capability,
                patient_id=patient_id,
            ):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "forbidden"}), 403
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorate


def authorize_patient_access(
    identity: IdentityContext,
    capability: Capability,
    patient_id: int | None,
) -> bool:
    return AuthorizationService.can(
        identity,
        capability,
        patient_id=patient_id,
    )


def role_landing(identity: IdentityContext) -> str:
    roles = identity.roles
    if "ADMIN" in {role.value for role in roles}:
        return url_for("admin_accounts")
    if "CLINICIAN" in {role.value for role in roles}:
        return url_for("clinician_portal")
    if "PATIENT" in {role.value for role in roles}:
        return url_for("patient_home")
    return url_for("access_unavailable")


def init_auth(app):
    @app.before_request
    def refresh_request_identity():
        g.identity_context = load_identity()
        identity = g.identity_context
        patient_id = request.view_args.get("patient_id") if request.view_args else None
        if (
            identity.is_authenticated
            and patient_id is not None
            and any(role.value == "PATIENT" for role in identity.roles)
            and not any(
                role.value == "CLINICIAN" for role in identity.roles
            )
            and identity.patient_id != patient_id
        ):
            return jsonify({"error": "forbidden"}), 403

    app.context_processor(lambda: {
        "current_identity": current_identity(),
        "csrf_token": csrf_token,
    })
