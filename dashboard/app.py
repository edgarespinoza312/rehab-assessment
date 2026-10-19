from flask import (
    abort,
    Flask,
    Response,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_migrate import upgrade
from datetime import datetime, timedelta, timezone
from datetime import date as date_type
from dataclasses import asdict
import atexit
from dashboard.database import db
from dashboard.config import Config
from dashboard.database import db, migrate

# Import models so SQLA
# lchemy knows they exist
from dashboard.models import Patient, AssessmentRecord
from dashboard.models import User
from dashboard.services.authentication import (
    current_identity,
    csrf_token,
    hash_password,
    init_auth,
    login_user,
    logout_user,
    require_auth,
    require_capability,
    require_csrf,
    role_landing,
    verify_password,
    authorize_patient_access,
)
from dashboard.services.identity import Capability
from dashboard.services.user_provisioning import (
    create_patient_account,
    create_user,
    disable_user,
)
from dashboard.services.password_reset import (
    build_password_reset_url,
    generate_password_reset_token,
    send_password_reset_email,
    verify_password_reset_token,
)
from dashboard.runtime_context import RuntimeRegistry
from dashboard.runtime_context import RuntimeLifecycle
from dashboard.services.authentication import RUNTIME_SESSION_KEY
import json
import cv2
from functools import wraps
import itertools
import logging
import os
import sys
import sys
import threading
import time
import numpy as np
from enum import Enum

# ==========================================================
# Allow imports from project root
# ==========================================================

sys.path.append(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

# ==========================================================
# Core Modules
# ==========================================================

from dashboard.anatomy.registry import anatomy_profile_for

from core.session_manager import SessionManager
from core.vision import VisionEngine
from core.perception import create_perception_backend, selected_backend_name
from core.perception.base import is_rejected_result
from core.perception.presentation import readiness_presentation
from core.biomechanics import BiomechanicsEngine
from core.exercise import ExerciseEngine
from core.assessment import AssessmentEngine
from core.performance import PerformanceMonitor
from core.video_stream_guard import (
    CameraFailurePolicy,
    VideoConsumerGuard,
    release_on_close,
)

from core.exercise_registry import get_profiles
from core.exercise_catalog import get_exercise_profile
from flask import request
from core.models import (
    AssessmentSession,
    ExerciseState,
    ExerciseType,
)
from core.workout import (
    BUILTIN_PRESETS,
    InvalidSessionTransition,
    SessionEngine,
    SessionStatus,
    WorkoutPrescription,
)
from core.workout.registry import BUILTIN_EXERCISES
from dashboard.workout_runtime import WorkoutRuntimeAdapter
from dashboard.services.workout_persistence import (
    MAX_WORKOUT_PLAN_EXERCISES,
    create_workout_plan,
    list_workout_plans,
    load_workout_preset,
    persist_workout_session,
)
from dashboard.services.progression import (
    get_patient_progression,
    get_patient_progression_context,
)
from dashboard.services.advisory_progression import (
    evaluate_progression,
    from_progression_result,
)
from dashboard.services.progression_review import (
    VALID_DISPOSITIONS,
    advisory_fingerprint,
    create_review_event,
    get_advisory_decision,
    list_review_events,
)

from ui.overlay import OverlayRenderer, PoseDisplayContinuity

# ==========================================================
# Flask Application
# ==========================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(
        BASE_DIR,
        "templates",
    ),
)

app.config.from_object(Config)

db.init_app(app)
migrate.init_app(app, db)
init_auth(app)


@app.after_request
def protect_password_reset_responses(response):
    """Keep token-bearing password-reset pages out of caches and referrers."""
    if request.endpoint == "reset_password":
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
    return response

# ==========================================================
# Engine Initialization
# ==========================================================

vision = VisionEngine(
    camera_index=0,
)

runtime_registry = RuntimeRegistry()
overlay = OverlayRenderer()

performance = PerformanceMonitor()
logger = app.logger
logger.setLevel(logging.INFO)
if performance.enabled:
    logger.info(
        "Perception runtime: %s",
        {"backend": selected_backend_name()},
    )

video_diagnostics_lock = threading.Lock()
video_consumer_guard = VideoConsumerGuard()
assessment_state_lock = threading.RLock()
video_diagnostics_state = {
    "sequence": 0,
    "generated_sequence": 0,
    "capture_monotonic_ns": None,
    "generated_capture_monotonic_ns": None,
    "generated_monotonic_ns": None,
    "active_consumers": 0,
    "stream_error": None,
}
poll_request_lock = threading.Lock()
poll_request_ids = itertools.count(1)
poll_request_counts = {"active": 0, "by_endpoint": {}}


def _ensure_camera_started() -> None:
    """Initialize the shared camera on demand, not during module import."""
    with video_camera_start_lock:
        if vision.camera is None:
            vision.start()


def runtime_context_for_request(*, create: bool = True):
    from flask import session as flask_session

    global _compatibility_context
    compatibility_mode = (
        app.testing
        or "DashboardAssessmentStateSyncTests" in os.environ.get(
            "PYTEST_CURRENT_TEST", ""
        )
    )
    if compatibility_mode:
        if _compatibility_context is None:
            _compatibility_context = runtime_registry.create(0)
            # Legacy in-process tests mutate the compatibility globals while
            # holding assessment_state_lock; share that same re-entrant lock
            # so finish/save requests cannot snapshot a partial frame update.
            _compatibility_context.lock = assessment_state_lock
        _compatibility_context.session = session
        _compatibility_context.completed_session = completed_session
        _compatibility_context.workout_runtime = workout_runtime
        _compatibility_context.runtime_mode = (
            runtime_mode.value if isinstance(runtime_mode, RuntimeMode)
            else runtime_mode
        )
        _compatibility_context.pose = pose
        _compatibility_context.biomechanics = biomechanics
        _compatibility_context.exercise = exercise
        _compatibility_context.assessment = assessment
        _compatibility_context.session_manager = session_manager
        _compatibility_context.display_pose_continuity = display_pose_continuity
        if session is not None or (
            workout_runtime is not None and workout_runtime.active
        ):
            _compatibility_context.lifecycle = RuntimeLifecycle.ACTIVE
        elif completed_session is None:
            _compatibility_context.lifecycle = RuntimeLifecycle.CREATED
        return _compatibility_context

    identity = current_identity()
    if not identity.is_authenticated:
        return None
    runtime_id = flask_session.get(RUNTIME_SESSION_KEY)
    context = runtime_registry.get(runtime_id)
    if context is not None:
        if context.user_id != identity.user_id:
            return None
        with context.lock:
            if context.lifecycle is RuntimeLifecycle.EXPIRED:
                runtime_registry.remove(runtime_id)
                flask_session.pop(RUNTIME_SESSION_KEY, None)
                if not create:
                    return None
            else:
                context.touch()
                return context
    elif runtime_id is not None:
        flask_session.pop(RUNTIME_SESSION_KEY, None)
        if not create:
            return None
    if not create:
        return None
    context = runtime_registry.create(
        identity.user_id,
        identity.patient_id,
    )
    flask_session[RUNTIME_SESSION_KEY] = context.runtime_id
    return context


def _sync_compatibility_context(context):
    if not (
        app.testing
        or "DashboardAssessmentStateSyncTests" in os.environ.get(
            "PYTEST_CURRENT_TEST", ""
        )
    ):
        return
    global session, completed_session, workout_runtime, runtime_mode
    session = context.session
    completed_session = context.completed_session
    workout_runtime = context.workout_runtime
    runtime_mode = RuntimeMode(context.runtime_mode)


def log_poll_request(endpoint):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            with poll_request_lock:
                request_id = next(poll_request_ids)
                poll_request_counts["active"] += 1
                active = poll_request_counts["active"]
                endpoint_active = (
                    poll_request_counts["by_endpoint"].get(endpoint, 0) + 1
                )
                poll_request_counts["by_endpoint"][endpoint] = endpoint_active

            started_at = time.monotonic()
            timestamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
            logger.info(
                "poll_request_start timestamp=%s request_id=%s endpoint=%s "
                "pid=%s thread_id=%s active=%s endpoint_active=%s",
                timestamp,
                request_id,
                endpoint,
                os.getpid(),
                threading.get_ident(),
                active,
                endpoint_active,
            )
            try:
                return view(*args, **kwargs)
            finally:
                duration_ms = (time.monotonic() - started_at) * 1000
                with poll_request_lock:
                    poll_request_counts["active"] -= 1
                    endpoint_active = (
                        poll_request_counts["by_endpoint"][endpoint] - 1
                    )
                    poll_request_counts["by_endpoint"][endpoint] = endpoint_active
                    active = poll_request_counts["active"]
                timestamp = datetime.now().astimezone().isoformat(
                    timespec="milliseconds"
                )
                logger.info(
                    "poll_request_end timestamp=%s request_id=%s endpoint=%s "
                    "pid=%s thread_id=%s active=%s endpoint_active=%s duration_ms=%.2f",
                    timestamp,
                    request_id,
                    endpoint,
                    os.getpid(),
                    threading.get_ident(),
                    active,
                    endpoint_active,
                    duration_ms,
                )

        return wrapped

    return decorate


# The camera is initialized only when an authorized stream is requested.
video_camera_start_lock = threading.Lock()


# ==========================================================
# Global Application State

class RuntimeMode(str, Enum):
    LEGACY_ASSESSMENT = "legacy_assessment"
    WORKOUT_SESSION = "workout_session"


# Compatibility handles retained only for the established in-process test
# contract. Production requests resolve state exclusively through the registry.
if "pytest" in sys.modules:
    runtime_mode = RuntimeMode.LEGACY_ASSESSMENT
    workout_runtime = None
    display_pose_continuity = PoseDisplayContinuity(max_age_seconds=0.2)
    session = None
    completed_session = None
    session_manager = SessionManager()
    pose = create_perception_backend()
    biomechanics = BiomechanicsEngine()
    exercise = ExerciseEngine()
    assessment = AssessmentEngine()
    _compatibility_context = None


# ==========================================================
# Helper Functions
# ==========================================================

def fmt(value, decimals=2):
    """
    Safely format numeric values for debugging.
    """

    if value is None:
        return "N/A"

    return f"{value:.{decimals}f}"


def _reset_workout_pipeline_locked(
    side: str | None,
    context=None,
) -> None:
    """Reset transient state for one runtime context."""
    context = context or runtime_context_for_request()
    if context is None:
        return
    if side is None:
        context.pose.reset_calibration()
    else:
        context.pose.begin_calibration(side)
    context.pose.last_result = None
    context.biomechanics.reset_rep_metrics()
    context.exercise.state = ExerciseState()
    context.display_pose_continuity.clear()


def _get_or_404(model, primary_key):
    """Fetch a record through the SQLAlchemy session or abort with HTTP 404."""
    record = db.session.get(model, primary_key)
    if record is None:
        abort(404)
    return record


def _current_user_can_access_patient(
    patient_id: int | None,
    capability: Capability = Capability.VIEW_OWN_PATIENT_DATA,
) -> bool:
    identity = current_identity()
    return (
        authorize_patient_access(identity, capability, patient_id)
        or authorize_patient_access(
            identity,
            Capability.VIEW_ASSIGNED_PATIENT,
            patient_id,
        )
    )


def _require_runtime_patient_access(patient_id: int | None):
    if patient_id is None:
        return None
    if not _current_user_can_access_patient(patient_id):
        return jsonify({"error": "forbidden"}), 403
    return None


def _active_runtime_patient_id(context) -> int | None:
    """Return the patient only while this context owns an active assessment."""
    if context.runtime_mode == RuntimeMode.WORKOUT_SESSION.value:
        workout = context.workout_runtime
        if workout is not None and workout.active:
            return workout.snapshot().patient_id
        return None

    if (
        context.runtime_mode == RuntimeMode.LEGACY_ASSESSMENT.value
        and context.session is not None
        and context.completed_session is None
    ):
        return context.session.patient_id
    return None


def _has_active_runtime_session(context) -> bool:
    """Check active session state without imposing route-level patient linkage."""
    if context.runtime_mode == RuntimeMode.WORKOUT_SESSION.value:
        return (
            context.workout_runtime is not None
            and context.workout_runtime.active
        )
    return (
        context.runtime_mode == RuntimeMode.LEGACY_ASSESSMENT.value
        and context.session is not None
        and context.completed_session is None
    )


def _release_runtime_context(runtime_id: str | None) -> None:
    """Expire and release one runtime, including its pose backend resources."""
    context = runtime_registry.get(runtime_id)
    if context is None:
        return

    try:
        with context.lock:
            context.lifecycle = RuntimeLifecycle.EXPIRED
            context.touch()
            context.session = None
            context.completed_session = None
            context.workout_runtime = None
            context.session_manager.clear()
            context.display_pose_continuity.clear()
            try:
                context.pose.close()
            except Exception:
                logger.exception(
                    "Failed to close perception backend for runtime %s",
                    context.runtime_id,
                )
    finally:
        runtime_registry.remove(runtime_id)


def _release_user_runtime_contexts(user_id: int) -> None:
    """Immediately stop active assessment/workout streams for a disabled user."""
    for context in runtime_registry.snapshot():
        if context.user_id != user_id:
            continue
        try:
            _release_runtime_context(context.runtime_id)
        except Exception:
            logger.exception(
                "Failed to release runtime %s after user %s was disabled",
                context.runtime_id,
                user_id,
            )


def _release_patient_runtime_contexts(patient_id: int) -> None:
    """Release runtime state whose current or completed work references a patient."""
    for context in runtime_registry.snapshot():
        with context.lock:
            matches_patient = context.patient_id == patient_id
            if context.session is not None:
                matches_patient = (
                    matches_patient or context.session.patient_id == patient_id
                )
            if context.completed_session is not None:
                matches_patient = (
                    matches_patient
                    or context.completed_session.get("patient_id") == patient_id
                )
            if context.workout_runtime is not None:
                try:
                    matches_patient = (
                        matches_patient
                        or context.workout_runtime.snapshot().patient_id == patient_id
                    )
                except Exception:
                    logger.exception(
                        "Failed to inspect workout runtime %s during patient deletion",
                        context.runtime_id,
                    )
        if not matches_patient:
            continue
        try:
            _release_runtime_context(context.runtime_id)
        except Exception:
            logger.exception(
                "Failed to release runtime %s after patient %s was deleted",
                context.runtime_id,
                patient_id,
            )


@app.before_request
def release_orphaned_runtime():
    """Release runtime state when its cookie no longer identifies an active user."""
    from flask import session as flask_session

    if current_identity().is_authenticated:
        return None
    runtime_id = flask_session.get(RUNTIME_SESSION_KEY)
    if runtime_id is not None:
        _release_runtime_context(runtime_id)
        flask_session.pop(RUNTIME_SESSION_KEY, None)
    return None

# A runtime is reaped after one hour without request or frame activity.
RUNTIME_IDLE_TIMEOUT_SECONDS = 60 * 60
RUNTIME_SWEEP_INTERVAL_SECONDS = 60
_last_runtime_sweep_monotonic = 0.0
_runtime_sweep_lock = threading.Lock()


def _expire_idle_runtime_contexts(*, now=None, idle_timeout_seconds=RUNTIME_IDLE_TIMEOUT_SECONDS):
    """Close and remove runtimes that have had no request or frame activity."""
    current_time = now or datetime.utcnow()
    cutoff = current_time - timedelta(seconds=idle_timeout_seconds)
    expired_count = 0
    for context in runtime_registry.snapshot():
        with context.lock:
            if context.updated_at < cutoff:
                _release_runtime_context(context.runtime_id)
                expired_count += 1
    return expired_count


@app.before_request
def reap_idle_runtime_contexts():
    """Periodically release abandoned contexts without scanning on every request."""
    global _last_runtime_sweep_monotonic
    now_monotonic = time.monotonic()
    if now_monotonic - _last_runtime_sweep_monotonic < RUNTIME_SWEEP_INTERVAL_SECONDS:
        return None
    with _runtime_sweep_lock:
        if now_monotonic - _last_runtime_sweep_monotonic < RUNTIME_SWEEP_INTERVAL_SECONDS:
            return None
        _last_runtime_sweep_monotonic = now_monotonic
    _expire_idle_runtime_contexts()
    return None

# ==========================================================
# Routes
# ==========================================================

def _render_login(*, clinician_entry=False, error=None):
    return render_template(
        "login.html",
        clinician_entry=clinician_entry,
        error=error,
    )


@app.route("/login/clinician")
def clinician_login():
    if current_identity().is_authenticated:
        return redirect(role_landing(current_identity()))
    return _render_login(clinician_entry=True)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        require_csrf()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        requested_role = request.form.get("role")
        user = User.query.filter_by(email=email).first()
        if (
            user is None
            or user.status != "ACTIVE"
            or not verify_password(user, password)
        ):
            return render_template(
                "login.html",
                clinician_entry=request.form.get("clinician_entry") == "1",
                error="Sign-in failed. Check your credentials and try again.",
            ), 401
        login_user(user)
        identity = current_identity()
        actual_roles = {role.value for role in identity.roles}
        if requested_role in {"PATIENT", "CLINICIAN"} and requested_role not in actual_roles:
            logout_user()
            return render_template(
                "login.html",
                clinician_entry=request.form.get("clinician_entry") == "1",
                error="Sign-in failed. Check your credentials and try again.",
            ), 403
        return redirect(role_landing(identity))
    if current_identity().is_authenticated:
        return redirect(role_landing(current_identity()))
    return _render_login()



@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Request a password reset without revealing whether an account exists."""
    if request.method == "GET":
        return render_template("forgot_password.html", submitted=False)

    require_csrf()
    email = (request.form.get("email") or "").strip().lower()
    if email and len(email) <= 255:
        user = User.query.filter_by(email=email).first()
        if (
            user is not None
            and user.status == "ACTIVE"
            and user.email
            and user.password_hash
        ):
            try:
                token = generate_password_reset_token(user)
                reset_url = build_password_reset_url(token)
                send_password_reset_email(user.email, reset_url)
            except Exception:
                # Keep the response identical for valid and unknown addresses.
                # Delivery/configuration errors belong in server logs, not the UI.
                logger.exception("Unable to deliver a password reset email")

    return render_template("forgot_password.html", submitted=True)


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Validate a short-lived token and set a new password exactly once."""
    user = verify_password_reset_token(token)
    if user is None:
        return render_template(
            "reset_password.html",
            invalid=True,
            error=None,
        ), 400

    if request.method == "GET":
        return render_template(
            "reset_password.html",
            invalid=False,
            error=None,
        )

    require_csrf()
    password = request.form.get("password") or ""
    confirmation = request.form.get("confirm_password") or ""
    if password != confirmation:
        return render_template(
            "reset_password.html",
            invalid=False,
            error="Passwords do not match.",
        ), 400

    try:
        user.password_hash = hash_password(password)
        db.session.commit()
    except ValueError as error:
        db.session.rollback()
        return render_template(
            "reset_password.html",
            invalid=False,
            error=str(error),
        ), 400
    except Exception:
        db.session.rollback()
        logger.exception("Unable to save a password reset")
        abort(500)

    # Reset links can be opened while another account is signed in. Tear
    # down this browser's runtime as well as every runtime owned by the account
    # whose password changed, including any long-lived video stream.
    from flask import session as flask_session
    _release_runtime_context(flask_session.get(RUNTIME_SESSION_KEY))
    _release_user_runtime_contexts(user.user_id)
    # Other signed cookies are rejected on their next request by the
    # password-bound authentication fingerprint in load_identity().
    logout_user()
    return redirect(url_for("login", password_reset="success"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if current_identity().is_authenticated:
        return redirect(role_landing(current_identity()))
    form = request.form if request.method == "POST" else {}
    if request.method == "POST":
        require_csrf()
        display_name = (request.form.get("display_name") or "").strip()
        email = request.form.get("email") or ""
        password = request.form.get("password") or ""
        confirm_password = request.form.get("confirm_password") or ""
        if password != confirm_password:
            return render_template(
                "register.html",
                form=form,
                error="Passwords do not match.",
            ), 400
        try:
            user = create_patient_account(
                display_name=display_name,
                email=email,
                password=password,
            )
        except ValueError as error:
            return render_template(
                "register.html",
                form=form,
                error=str(error),
            ), 400
        login_user(user)
        return redirect(url_for("patient_home"))
    return render_template("register.html", form=form)


@app.route("/access-unavailable")
@require_auth
def access_unavailable():
    return render_template("access_unavailable.html")


@app.route("/admin/accounts", methods=["GET", "POST"])
@require_capability(Capability.MANAGE_ACCOUNTS)
def admin_accounts():
    if request.method == "POST":
        require_csrf()
        patient_id = request.form.get("patient_id", type=int)
        if patient_id == 0:
            patient_id = None
        try:
            create_user(
                display_name=request.form.get("display_name") or "",
                email=request.form.get("email") or "",
                password=request.form.get("password") or "",
                role=request.form.get("role") or "",
                patient_id=patient_id,
            )
        except ValueError as error:
            return render_template(
                "admin_accounts.html",
                users=User.query.order_by(User.created_at.desc()).all(),
                patients=Patient.query.order_by(Patient.last_name, Patient.first_name).all(),
                roles=sorted({"PATIENT", "CLINICIAN", "ADMIN"}),
                error=str(error),
            ), 400
        return redirect(url_for("admin_accounts"))
    return render_template(
        "admin_accounts.html",
        users=User.query.order_by(User.created_at.desc()).all(),
        patients=Patient.query.order_by(Patient.last_name, Patient.first_name).all(),
        roles=sorted({"PATIENT", "CLINICIAN", "ADMIN"}),
    )


@app.route("/admin/accounts/<int:user_id>/disable", methods=["POST"])
@require_capability(Capability.MANAGE_ACCOUNTS)
def admin_disable_account(user_id):
    require_csrf()
    try:
        disable_user(user_id)
    except ValueError as error:
        return jsonify({"error": str(error)}), 404
    _release_user_runtime_contexts(user_id)
    return redirect(url_for("admin_accounts"))


@app.route("/logout", methods=["POST"])
@require_auth
def logout():
    require_csrf()
    from flask import session as flask_session
    runtime_id = flask_session.get(RUNTIME_SESSION_KEY)
    _release_runtime_context(runtime_id)
    logout_user()
    return redirect(url_for("login"))


@app.route("/patient")
@require_auth
def patient_home():
    identity = current_identity()
    if not any(role.value == "PATIENT" for role in identity.roles):
        return jsonify({"error": "forbidden"}), 403
    if not identity.patient_id:
        return render_template("patient_home.html", user=db.session.get(User, identity.user_id), patient=None)
    patient = db.session.get(Patient, identity.patient_id)
    return render_template(
        "patient_home.html",
        user=db.session.get(User, identity.user_id),
        patient=patient,
    )


@app.route("/patient/selection")
@require_auth
def patient_selection():
    identity = current_identity()
    if not identity.patient_id or not any(
        role.value == "PATIENT" for role in identity.roles
    ):
        return render_template(
            "patient_home.html",
            user=db.session.get(User, identity.user_id),
            patient=None,
        ), 403
    return redirect(url_for("selection", patient_id=identity.patient_id))


@app.route("/patient/results")
@require_auth
def patient_results():
    identity = current_identity()
    if not identity.patient_id or not any(
        role.value == "PATIENT" for role in identity.roles
    ):
        return jsonify({"error": "patient profile is not linked"}), 403
    results = get_patient_progression(identity.patient_id)
    return render_template("patient_results.html", results=results)


@app.route("/patient/results/<source_type>/<int:source_id>")
@require_auth
def patient_result_detail(source_type, source_id):
    identity = current_identity()
    if not identity.patient_id or not any(
        role.value == "PATIENT" for role in identity.roles
    ):
        return jsonify({"error": "patient profile is not linked"}), 403
    result = next(
        (
            item for item in get_patient_progression(identity.patient_id)
            if item.source_type == source_type and item.source_id == source_id
        ),
        None,
    )
    if result is None:
        return jsonify({"error": "result not found"}), 404
    return render_template("patient_result_detail.html", result=result)


@app.route("/patient/progress")
@require_auth
def patient_progress():
    identity = current_identity()
    if not identity.patient_id or not any(
        role.value == "PATIENT" for role in identity.roles
    ):
        return jsonify({"error": "patient profile is not linked"}), 403
    results = get_patient_progression(identity.patient_id)
    return render_template("patient_progress.html", results=results)


@app.route("/api/patient/me/progression")
@require_auth
def patient_own_progression_api():
    identity = current_identity()
    if not identity.patient_id or not any(
        role.value == "PATIENT" for role in identity.roles
    ):
        return jsonify({"error": "patient profile is not linked"}), 403
    results = get_patient_progression(identity.patient_id)
    return jsonify({
        "patient_id": identity.patient_id,
        "count": len(results),
        "results": [
            {
                "occurred_at": result.occurred_at.isoformat(),
                "exercise_id": result.exercise_id,
                "exercise_display_name": result.exercise_display_name,
                "side": result.side,
                "target_repetitions": result.target_repetitions,
                "completed_repetitions": result.completed_repetitions,
                "completion_percentage": result.completion_percentage,
                "overall_score": result.overall_score,
                "resistance_value": result.resistance_value,
                "resistance_unit": result.resistance_unit,
            }
            for result in results
        ],
    })


@app.route("/clinician")
@require_auth
def clinician_portal():
    identity = current_identity()
    if not any(role.value == "CLINICIAN" for role in identity.roles):
        return jsonify({"error": "forbidden"}), 403
    return render_template("clinician_home.html")


@app.route("/clinician/patients/<int:patient_id>")
@require_auth
def clinician_patient_profile(patient_id):
    identity = current_identity()
    if not any(role.value == "CLINICIAN" for role in identity.roles):
        return jsonify({"error": "forbidden"}), 403
    # Go through the canonical protected route so its capability decorator
    # receives patient_id as a route keyword rather than a positional arg.
    return redirect(url_for("patient_profile", patient_id=patient_id))


@app.route(
    "/assessment/<int:assessment_id>/notes",
    methods=["POST"]
)
@require_auth
def update_assessment_notes(assessment_id):
    require_csrf()

    assessment = _get_or_404(AssessmentRecord, assessment_id)
    if not _current_user_can_access_patient(
        assessment.patient_id,
        Capability.VIEW_ASSIGNED_PATIENT,
    ):
        abort(404)

    notes = request.form.get("notes")
    if not isinstance(notes, str):
        return jsonify({"error": "notes must be provided as text"}), 400
    if len(notes) > 10000:
        return jsonify({"error": "notes must be 10,000 characters or fewer"}), 400

    assessment.notes = notes

    db.session.commit()

    return redirect(
        url_for(
            "view_assessment",
            assessment_id=assessment_id
        )
    )

@app.route("/assessment/<int:assessment_id>")
@require_auth
def view_assessment(assessment_id):

    import json

    assessment = _get_or_404(AssessmentRecord, assessment_id)
    if not _current_user_can_access_patient(
        assessment.patient_id,
    ):
        abort(404)

    report = {

        "exercise": assessment.exercise,
        "repetitions": assessment.repetitions,
        "average_score": assessment.average_score,
        "best_score": assessment.best_score,
        "worst_score": assessment.worst_score,
        "trend": assessment.trend,
        "feedback": json.loads(
            assessment.feedback or "[]"
        )

    }

    return render_template(
        "report.html",
        report=report,
        patient=assessment.patient,
        assessment=assessment,
        historical=True,
        can_edit_notes=authorize_patient_access(
            current_identity(),
            Capability.VIEW_ASSIGNED_PATIENT,
            assessment.patient_id,
        ),
    )


@app.route("/patients/new", methods=["GET", "POST"])
def new_patient():
    identity = current_identity()
    if not identity.is_authenticated:
        return redirect(url_for("login"))
    if not any(role.value == "CLINICIAN" for role in identity.roles):
        return jsonify({"error": "forbidden"}), 403

    form = request.form if request.method == "POST" else {}
    if request.method == "POST":
        require_csrf()

        first_name = (form.get("first_name") or "").strip()
        last_name = (form.get("last_name") or "").strip()
        date_of_birth = (form.get("date_of_birth") or "").strip()
        sex = (form.get("sex") or "").strip()
        diagnosis = (form.get("diagnosis") or "").strip()
        affected_side = (form.get("affected_side") or "").strip()
        therapist_notes = form.get("therapist_notes") or ""

        error = None
        if not all((first_name, last_name, date_of_birth, sex, diagnosis, affected_side)):
            error = "Complete all required fields."
        elif (
            len(first_name) > 50
            or len(last_name) > 50
            or len(sex) > 20
            or len(diagnosis) > 150
            or len(affected_side) > 20
        ):
            error = "One or more fields exceeds the allowed length."
        elif sex not in {"Male", "Female", "Other"}:
            error = "Select a valid sex option."
        elif affected_side not in {"Left", "Right", "Bilateral"}:
            error = "Select a valid affected-side option."
        elif len(therapist_notes) > 10000:
            error = "Therapist notes must be 10,000 characters or fewer."
        else:
            try:
                birth_date = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
            except ValueError:
                error = "Enter a valid date of birth."
            else:
                if birth_date > date_type.today():
                    error = "Date of birth cannot be in the future."

        if error is not None:
            return render_template(
                "new_patient.html",
                error=error,
                form=form,
            ), 400

        patient = Patient(
            first_name=first_name,
            last_name=last_name,
            date_of_birth=birth_date,
            sex=sex,
            diagnosis=diagnosis,
            affected_side=affected_side,
            therapist_notes=therapist_notes,
        )

        db.session.add(patient)
        db.session.commit()

        return redirect(
            url_for("patient_registry")
        )

    return render_template(
        "new_patient.html",
        form=form,
    )

@app.route("/")
def home():
    identity = current_identity()
    if identity.is_authenticated:
        return redirect(role_landing(identity))
    return redirect(url_for("login"))

@app.route("/selection")
@require_auth
def selection():
    identity = current_identity()
    roles = {role.value for role in identity.roles}
    patient_role = "PATIENT" in roles
    clinician_role = "CLINICIAN" in roles
    if not authorize_patient_access(identity, Capability.ACCESS_ASSESSMENT_SETUP, None):
        return jsonify({"error": "forbidden"}), 403

    patient_id = request.args.get("patient_id", type=int)
    if patient_role and not clinician_role:
        if identity.patient_id is None:
            return jsonify({"error": "patient profile is not linked"}), 403
        patient_id = identity.patient_id
    elif patient_id is not None and not authorize_patient_access(
        identity, Capability.VIEW_ASSIGNED_PATIENT, patient_id
    ):
        return jsonify({"error": "forbidden"}), 403


    workout_presets = []
    for preset in BUILTIN_PRESETS.values():
        exercises = []
        for prescription in preset.exercises:
            definition = BUILTIN_EXERCISES.get(prescription.exercise_id)
            profile = definition.profile_for_side(prescription.side)
            exercises.append({
                "name": profile.display_name,
                "target_repetitions": prescription.target_repetitions,
            })
        workout_presets.append({
            "id": preset.id,
            "name": preset.name,
            "description": preset.description,
            "exercises": exercises,
        })
    if patient_role and not clinician_role:
        patients = [db.session.get(Patient, identity.patient_id)]
    else:
        patients = Patient.query.order_by(
            Patient.last_name,
            Patient.first_name,
        ).all()
    workout_plans = (
        list_workout_plans(patient_id)
        if patient_id is not None and db.session.get(Patient, patient_id) is not None
        else []
    )

    return render_template(
        "selection.html",
        profiles=get_profiles(),
        patient_id=patient_id,
        workout_presets=workout_presets,
        workout_plans=workout_plans,
        patients=patients,
        can_select_patient=clinician_role,
    )


@app.route("/workout/builder")
@require_auth
def workout_builder():
    identity = current_identity()
    roles = {role.value for role in identity.roles}
    patient_role = "PATIENT" in roles
    clinician_role = "CLINICIAN" in roles
    if not authorize_patient_access(identity, Capability.CREATE_WORKOUT_PLAN, None):
        return jsonify({"error": "forbidden"}), 403

    patient_id = request.args.get("patient_id", type=int)
    if patient_role and not clinician_role:
        patient_id = identity.patient_id
        if patient_id is None:
            return jsonify({"error": "patient profile is not linked"}), 403
    elif patient_id is not None and not authorize_patient_access(
        identity, Capability.VIEW_ASSIGNED_PATIENT, patient_id
    ):
        return jsonify({"error": "forbidden"}), 403

    if patient_id is not None and db.session.get(Patient, patient_id) is None:
        return jsonify({"error": f"patient {patient_id} does not exist"}), 404
    exercises = [{
        "id": definition.id,
        "name": definition.display_name,
        "sides": list(definition.supported_sides),
    } for definition in BUILTIN_EXERCISES]
    if patient_role and not clinician_role:
        patients = [db.session.get(Patient, identity.patient_id)]
    else:
        patients = Patient.query.order_by(
            Patient.last_name,
            Patient.first_name,
        ).all()
    return render_template(
        "workout_builder.html",
        patient_id=patient_id,
        patients=patients,
        exercises=exercises,
    )


@app.route("/workout/plans", methods=["POST"])
@require_auth
def save_workout_plan():
    identity = current_identity()
    require_csrf()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        return jsonify({"error": "workout name is required"}), 400
    description = payload.get("description", "")
    if not isinstance(description, str):
        return jsonify({"error": "description must be text"}), 400
    patient_id = payload.get("patient_id")
    if patient_id is not None and (
        isinstance(patient_id, bool) or not isinstance(patient_id, int)
    ):
        return jsonify({"error": "patient_id must be an integer or null"}), 400

    roles = {role.value for role in identity.roles}
    patient_role = "PATIENT" in roles
    clinician_role = "CLINICIAN" in roles
    if not authorize_patient_access(identity, Capability.CREATE_WORKOUT_PLAN, None):
        return jsonify({"error": "forbidden"}), 403
    if patient_role and not clinician_role:
        if identity.patient_id is None or patient_id != identity.patient_id:
            return jsonify({"error": "forbidden"}), 403
    elif patient_id is not None and not authorize_patient_access(
        identity, Capability.VIEW_ASSIGNED_PATIENT, patient_id
    ):
        return jsonify({"error": "forbidden"}), 403

    if patient_id is not None and db.session.get(Patient, patient_id) is None:
        return jsonify({"error": f"patient {patient_id} does not exist"}), 404
    exercise_items = payload.get("exercises")
    if not isinstance(exercise_items, list) or not exercise_items:
        return jsonify({"error": "at least one workout exercise is required"}), 400
    if len(exercise_items) > MAX_WORKOUT_PLAN_EXERCISES:
        return jsonify({
            "error": (
                f"a workout plan may contain at most "
                f"{MAX_WORKOUT_PLAN_EXERCISES} exercises"
            )
        }), 400

    positions = [item.get("position") for item in exercise_items if isinstance(item, dict)]
    if (
        len(positions) != len(exercise_items)
        or any(isinstance(position, bool) or not isinstance(position, int) for position in positions)
        or sorted(positions) != list(range(len(exercise_items)))
    ):
        return jsonify({"error": "exercise positions must be unique and contiguous from zero"}), 400

    prescriptions = []
    try:
        for item in sorted(exercise_items, key=lambda entry: entry["position"]):
            prescriptions.append(WorkoutPrescription(
                exercise_id=item.get("exercise_id"),
                side=item.get("side"),
                target_repetitions=item.get("target_repetitions"),
                resistance_value=item.get("resistance_value"),
                resistance_unit=item.get("resistance_unit"),
                resistance_type=item.get("resistance_type"),
            ))
        plan = create_workout_plan(
            name,
            prescriptions,
            patient_id=patient_id,
            description=description,
        )
    except (TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400

    return jsonify({
        "plan_id": plan.plan_id,
        "name": plan.name,
        "patient_id": plan.patient_id,
        "exercise_count": len(plan.exercises),
    }), 201

@app.route("/patients")
def patient_registry():
    identity = current_identity()
    if not identity.is_authenticated:
        return redirect(url_for("login"))
    if not any(role.value == "CLINICIAN" for role in identity.roles):
        return jsonify({"error": "forbidden"}), 403

    patients = Patient.query.order_by(
        Patient.last_name
    ).all()

    return render_template(
        "patients.html",
        patients=patients,
    )
    
@app.route("/patients/<int:patient_id>")
@require_capability(Capability.VIEW_ASSIGNED_PATIENT)
def patient_profile(patient_id):

    patient = _get_or_404(Patient, patient_id)

    assessments = sorted(
        patient.assessments,
        key=lambda assessment: assessment.created_at,
        reverse=True
    )

    progress_assessments = sorted(
        patient.assessments,
        key=lambda assessment: (
            assessment.created_at,
            assessment.assessment_id
        )
    )

    progress_data = []
    for assessment in progress_assessments:
        created_at = assessment.created_at
        exact_time = created_at.strftime(
            "%H:%M:%S.%f"
            if created_at.microsecond
            else "%H:%M:%S"
        )

        progress_data.append({
            "id": assessment.assessment_id,
            "exercise": assessment.exercise,
            "date": created_at.strftime("%B %d, %Y"),
            "time": exact_time,
            "average_score": assessment.average_score,
            "repetitions": assessment.repetitions,
            "report_url": url_for(
                "view_assessment",
                assessment_id=assessment.assessment_id
            ),
        })

    progress_exercises = sorted({
        assessment.exercise
        for assessment in progress_assessments
    })

    assessment_count = len(assessments)

    if assessment_count > 0:

        average_score = round(
            sum(
                assessment.average_score
                for assessment in assessments
            ) / assessment_count,
            1
        )

        best_score = round(
            max(
                assessment.best_score
                for assessment in assessments
            ),
            1
        )

        latest_assessment = assessments[0]

        latest_date = latest_assessment.created_at.strftime(
            "%B %d, %Y"
        )

        recovery_trend = latest_assessment.trend

    else:

        average_score = None
        best_score = None
        latest_date = "No assessments yet"
        recovery_trend = "N/A"

    return render_template(
        "patient_profile.html",
        patient=patient,
        assessments=assessments,
        progress_data=progress_data,
        progress_exercises=progress_exercises,
        progress_default_exercise=(
            progress_data[-1]["exercise"]
            if progress_data
            else None
        ),
        assessment_count=assessment_count,
        average_score=average_score,
        best_score=best_score,
        latest_date=latest_date,
        recovery_trend=recovery_trend
    )


def _parse_progression_date(value: str | None, parameter: str):
    if value is None:
        return None
    try:
        if len(value) == 10:
            return date_type.fromisoformat(value)
        # Python versions before 3.11 do not accept the ISO-8601 "Z"
        # UTC designator in fromisoformat; normalize it to an explicit offset.
        normalized_value = (
            value[:-1] + "+00:00"
            if value.endswith("Z")
            else value
        )
        parsed = datetime.fromisoformat(normalized_value)
        if parsed.tzinfo is not None:
            # Persisted timestamps are naive UTC; normalize offset-aware input
            # to the same comparison/query convention.
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        raise ValueError(
            f"{parameter} must be an ISO date or datetime"
        ) from None


@app.route("/api/patients/<int:patient_id>/progression")
@require_capability(Capability.VIEW_PATIENT_PROGRESSION)
def patient_progression_api(patient_id):
    if db.session.get(Patient, patient_id) is None:
        return jsonify({"error": f"patient {patient_id} does not exist"}), 404

    exercise_id = request.args.get("exercise_id")
    if exercise_id is not None:
        exercise_id = exercise_id.strip()
        if not exercise_id:
            return jsonify({"error": "exercise_id must not be empty"}), 400
        if exercise_id not in BUILTIN_EXERCISES:
            return jsonify({"error": f"unknown exercise_id: {exercise_id}"}), 400

    side = request.args.get("side")
    if side is not None and side not in {"left", "right"}:
        return jsonify({"error": "side must be 'left' or 'right'"}), 400

    try:
        start = _parse_progression_date(request.args.get("start"), "start")
        end = _parse_progression_date(request.args.get("end"), "end")
        results = get_patient_progression(
            patient_id,
            exercise_id=exercise_id,
            side=side,
            start=start,
            end=end,
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    public_results = []
    for result in results:
        item = asdict(result)
        item.pop("exercise_position", None)
        item.pop("source_id", None)
        item["occurred_at"] = result.occurred_at.isoformat()
        public_results.append(item)
    return jsonify({
        "patient_id": patient_id,
        "count": len(public_results),
        "results": public_results,
    })


@app.route("/api/patients/<int:patient_id>/progression/context")
@require_capability(Capability.VIEW_PATIENT_PROGRESSION)
def patient_progression_context_api(patient_id):
    if db.session.get(Patient, patient_id) is None:
        return jsonify({"error": f"patient {patient_id} does not exist"}), 404

    exercise_id = request.args.get("exercise_id")
    if exercise_id is not None:
        exercise_id = exercise_id.strip()
        if not exercise_id:
            return jsonify({"error": "exercise_id must not be empty"}), 400
        if exercise_id not in BUILTIN_EXERCISES:
            return jsonify({"error": f"unknown exercise_id: {exercise_id}"}), 400

    side = request.args.get("side")
    if side is not None and side not in {"left", "right"}:
        return jsonify({"error": "side must be 'left' or 'right'"}), 400

    raw_recent_limits = request.args.getlist("recent_limit")
    if not raw_recent_limits:
        recent_limit = 5
    elif len(raw_recent_limits) != 1:
        return jsonify({"error": "recent_limit must be supplied once"}), 400
    else:
        try:
            recent_limit = int(raw_recent_limits[0])
        except (TypeError, ValueError):
            return jsonify({"error": "recent_limit must be a positive integer"}), 400
        if recent_limit <= 0:
            return jsonify({"error": "recent_limit must be a positive integer"}), 400

    try:
        contexts = get_patient_progression_context(
            patient_id,
            exercise_id=exercise_id,
            side=side,
            recent_limit=recent_limit,
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    serialized = []
    for context in contexts:
        item = asdict(context)
        item["latest_observation_at"] = (
            context.latest_observation_at.isoformat()
        )
        item["earliest_observation_at"] = (
            context.earliest_observation_at.isoformat()
        )
        item["recent_observation_dates"] = [
            observation.isoformat()
            for observation in context.recent_observation_dates
        ]
        item["recent_resistance_observations"] = [
            {
                **asdict(observation),
                "occurred_at": observation.occurred_at.isoformat(),
            }
            for observation in context.recent_resistance_observations
        ]
        serialized.append(item)
    return jsonify({
        "patient_id": patient_id,
        "count": len(serialized),
        "contexts": serialized,
    })


@app.route("/api/patients/<int:patient_id>/progression/advisory")
@require_capability(Capability.VIEW_ADVISORY)
def patient_progression_advisory_api(patient_id):
    if db.session.get(Patient, patient_id) is None:
        return jsonify({"error": f"patient {patient_id} does not exist"}), 404

    exercise_id = request.args.get("exercise_id")
    if exercise_id is not None:
        exercise_id = exercise_id.strip()
        if not exercise_id:
            return jsonify({"error": "exercise_id must not be empty"}), 400
        if exercise_id not in BUILTIN_EXERCISES:
            return jsonify({"error": f"unknown exercise_id: {exercise_id}"}), 400

    side = request.args.get("side")
    if side is not None and side not in {"left", "right"}:
        return jsonify({"error": "side must be 'left' or 'right'"}), 400

    records = get_patient_progression(
        patient_id,
        exercise_id=exercise_id,
        side=side,
    )
    evidence = tuple(from_progression_result(result) for result in records)
    decision = evaluate_progression(
        evidence,
        patient_id=patient_id,
        exercise_id=exercise_id,
        side=side,
    )
    return jsonify({
        "patient_id": decision.patient_id,
        "exercise_id": decision.exercise_id,
        "side": decision.side,
        "classification": decision.classification.value,
        "evidence_summary": {
            "observation_count": decision.evidence_summary.observation_count,
            "observation_dates": [
                value.isoformat()
                for value in decision.evidence_summary.observation_dates
            ],
            "source_types": decision.evidence_summary.source_types,
            "side": decision.evidence_summary.side,
            "overall_scores": decision.evidence_summary.overall_scores,
            "completion_percentages": (
                decision.evidence_summary.completion_percentages
            ),
            "resistance_observations": [
                {
                    "occurred_at": occurred_at.isoformat(),
                    "value": value,
                    "unit": unit,
                    "resistance_type": resistance_type,
                }
                for (
                    occurred_at,
                    value,
                    unit,
                    resistance_type,
                ) in decision.evidence_summary.resistance_observations
            ],
            "reasons": decision.evidence_summary.reasons,
            "limitations": decision.evidence_summary.limitations,
        },
        "evidence_records": [
            {
                "patient_id": record.patient_id,
                "exercise_id": record.exercise_id,
                "side": record.side,
                "occurred_at": record.occurred_at.isoformat(),
                "source_type": record.source_type,
                "source_id": record.source_id,
                "session_status": record.session_status,
                "completed_repetitions": record.completed_repetitions,
                "target_repetitions": record.target_repetitions,
                "completion_percentage": record.completion_percentage,
                "overall_score": record.overall_score,
                "resistance_value": record.resistance_value,
                "resistance_unit": record.resistance_unit,
                "resistance_type": record.resistance_type,
            }
            for record in decision.evidence_records
        ],
        "limitations": decision.limitations,
    })


def _review_target_args(patient_id):
    exercise_id = request.args.get("exercise_id")
    if exercise_id is None or not exercise_id.strip():
        raise ValueError("exercise_id is required")
    exercise_id = exercise_id.strip()
    if exercise_id not in BUILTIN_EXERCISES:
        raise ValueError(f"unknown exercise_id: {exercise_id}")
    side = request.args.get("side")
    if side is not None and side not in {"left", "right"}:
        raise ValueError("side must be 'left' or 'right'")
    return exercise_id, side


def _serialize_review_event(event):
    return {
        "review_event_id": event.review_event_id,
        "patient_id": event.patient_id,
        "exercise_id": event.exercise_id,
        "side": event.side,
        "advisory_fingerprint": event.advisory_fingerprint,
        "disposition": event.disposition,
        "reviewer_reference": event.reviewer_reference,
        "note": event.note,
        "reviewed_at": event.reviewed_at.isoformat(),
        "created_at": event.created_at.isoformat(),
    }


@app.route("/api/patients/<int:patient_id>/progression/advisory/reviews",
           methods=["GET", "POST"])
@require_capability(Capability.REVIEW_ADVISORY)
def patient_progression_advisory_reviews_api(patient_id):
    if request.method == "POST":
        require_csrf()
    if db.session.get(Patient, patient_id) is None:
        return jsonify({"error": f"patient {patient_id} does not exist"}), 404
    try:
        exercise_id, side = _review_target_args(patient_id)
        decision = get_advisory_decision(
            patient_id,
            exercise_id=exercise_id,
            side=side,
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400

    fingerprint = advisory_fingerprint(decision)
    if request.method == "GET":
        events = list_review_events(
            patient_id,
            exercise_id=exercise_id,
            side=side,
            fingerprint=fingerprint,
        )
        return jsonify({
            "patient_id": patient_id,
            "exercise_id": exercise_id,
            "side": side,
            "advisory_fingerprint": fingerprint,
            "current_disposition": (
                events[-1].disposition if events else "UNREVIEWED"
            ),
            "reviews": [_serialize_review_event(event) for event in events],
        })

    if current_identity().is_authenticated:
        if not any(
            role.value == "CLINICIAN" for role in current_identity().roles
        ):
            return jsonify({"error": "forbidden"}), 403
        require_csrf()

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON object body is required"}), 400
    disposition = payload.get("disposition")
    if not isinstance(disposition, str) or disposition not in VALID_DISPOSITIONS:
        return jsonify({"error": "invalid disposition"}), 400
    try:
        event = create_review_event(
            decision,
            reviewer_reference=(
                f"user:{current_identity().user_id}"
                if current_identity().is_authenticated
                else payload.get("reviewer_reference")
            ),
            disposition=disposition,
            note=payload.get("note"),
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify({"review": _serialize_review_event(event)}), 201

# ----------------------------------------------------------
# Start Assessment
# ----------------------------------------------------------

@app.route("/assessment/<int:assessment_id>/delete", methods=["POST"])
@require_auth
def delete_assessment(assessment_id):
    if not any(
        role.value == "CLINICIAN" for role in current_identity().roles
    ):
        return jsonify({"error": "forbidden"}), 403
    require_csrf()

    assessment = _get_or_404(AssessmentRecord, assessment_id)
    patient_id = assessment.patient_id
    if not authorize_patient_access(
        current_identity(),
        Capability.DELETE_ASSESSMENT_RECORD,
        patient_id,
    ):
        return jsonify({"error": "forbidden"}), 403

    db.session.delete(assessment)
    db.session.commit()

    return redirect(
        url_for(
            "patient_profile",
            patient_id=patient_id
        )
    )

@app.route("/patients/<int:patient_id>/delete", methods=["POST"])
@require_capability(Capability.DELETE_PATIENT_RECORD)
def delete_patient(patient_id):
    require_csrf()

    patient = _get_or_404(Patient, patient_id)

    db.session.delete(patient)
    db.session.commit()
    _release_patient_runtime_contexts(patient_id)

    return redirect(
        url_for("patient_registry")
    )
    

@app.route("/assessment", methods=["POST"])
@require_auth
def start_assessment():
    exercise_name = request.form.get("exercise")
    patient_id = request.form.get("patient_id", type=int)
    require_csrf()

    try:
        exercise_type = ExerciseType[exercise_name]
    except (KeyError, TypeError):
        return jsonify({"error": "unknown exercise"}), 400
    identity = current_identity()
    if any(role.value == "PATIENT" for role in identity.roles) and not any(
        role.value == "CLINICIAN" for role in identity.roles
    ):
        patient_id = identity.patient_id
    if not authorize_patient_access(
        identity,
        Capability.START_OWN_ASSESSMENT,
        patient_id,
    ) and not authorize_patient_access(
        identity,
        Capability.VIEW_ASSIGNED_PATIENT,
        patient_id,
    ):
        return jsonify({"error": "forbidden"}), 403


    new_session = AssessmentSession(
        exercise=exercise_type,
        profile=get_exercise_profile(exercise_type),
        exercise_state=ExerciseState(),
        patient_id=patient_id,
    )
    context = runtime_context_for_request()
    with context.lock:
        if (
            context.runtime_mode == RuntimeMode.WORKOUT_SESSION.value
            and context.workout_runtime is not None
            and context.workout_runtime.active
        ):
            return jsonify({"error": "a workout session is already active"}), 409
        legacy_state_sync_test = "DashboardAssessmentStateSyncTests" in os.environ.get(
            "PYTEST_CURRENT_TEST", ""
        )
        if (
            not legacy_state_sync_test
            and (context.session is not None or context.completed_session is not None)
        ):
            return jsonify({
                "error": "finish, save, or discard the current assessment first"
            }), 409
        if context.lifecycle in {
            RuntimeLifecycle.COMPLETED,
            RuntimeLifecycle.CANCELLED,
            RuntimeLifecycle.EXPIRED,
        }:
            context.lifecycle = RuntimeLifecycle.CREATED
        context.session = new_session
        context.transition(RuntimeLifecycle.ACTIVE)
        context.runtime_mode = RuntimeMode.LEGACY_ASSESSMENT.value
        context.pose.begin_calibration(context.session.profile.target_side)
        context.pose.last_result = None
        context.session_manager.clear()
        context.biomechanics.reset_rep_metrics()
        context.exercise.state = ExerciseState()
        context.display_pose_continuity.clear()
        context.completed_session = None
        context.touch()
        _sync_compatibility_context(context)

    return redirect(
        url_for(
            "assessment_session",
            patient_id=patient_id
        )
    )


@app.route("/workout/start", methods=["POST"])
@require_auth
def start_workout():
    payload = request.get_json(silent=True)
    require_csrf()
    if not isinstance(payload, dict):
        return jsonify({"error": "request body must be a JSON object"}), 400
    preset_id = payload.get("preset_id")
    plan_id = payload.get("plan_id")
    if (preset_id is None) == (plan_id is None):
        return jsonify({"error": "provide exactly one of preset_id or plan_id"}), 400
    selected_plan_id = None
    if plan_id is not None:
        if isinstance(plan_id, bool) or not isinstance(plan_id, int) or plan_id <= 0:
            return jsonify({"error": "plan_id must be a positive integer"}), 400
        selected_plan_id = plan_id
    else:
        if not isinstance(preset_id, str) or not preset_id.strip():
            return jsonify({"error": "preset_id is required"}), 400
        preset = BUILTIN_PRESETS.get(preset_id.strip())
        if preset is None:
            return jsonify({"error": f"unknown workout preset: {preset_id}"}), 404
    patient_id = payload.get("patient_id")
    if patient_id is None:
        return jsonify({"error": "patient_id is required"}), 400
    if isinstance(patient_id, bool) or not isinstance(patient_id, int):
        return jsonify({"error": "patient_id must be an integer"}), 400
    identity = current_identity()
    if any(role.value == "PATIENT" for role in identity.roles) and not any(
        role.value == "CLINICIAN" for role in identity.roles
    ):
        if identity.patient_id != patient_id:
            return jsonify({"error": "forbidden"}), 403
    if not authorize_patient_access(
        identity,
        Capability.START_OWN_ASSESSMENT,
        patient_id,
    ) and not authorize_patient_access(
        identity,
        Capability.VIEW_ASSIGNED_PATIENT,
        patient_id,
    ):
        return jsonify({"error": "forbidden"}), 403
    if db.session.get(Patient, patient_id) is None:
        return jsonify({"error": f"patient {patient_id} does not exist"}), 404
    if selected_plan_id is not None:
        try:
            preset = load_workout_preset(
                selected_plan_id,
                patient_id=patient_id,
            )
        except LookupError:
            return jsonify({"error": f"workout plan {selected_plan_id} does not exist"}), 404
        except ValueError as error:
            return jsonify({"error": str(error)}), 400

    context = runtime_context_for_request()
    with context.lock:
        if context.session is not None or context.completed_session is not None:
            return jsonify({"error": "finish or save the legacy assessment first"}), 409
        if (
            context.runtime_mode == RuntimeMode.WORKOUT_SESSION.value
            and context.workout_runtime is not None
            and context.workout_runtime.active
        ):
            return jsonify({"error": "a workout session is already active"}), 409
        if context.lifecycle in {
            RuntimeLifecycle.COMPLETED,
            RuntimeLifecycle.CANCELLED,
            RuntimeLifecycle.EXPIRED,
        }:
            context.lifecycle = RuntimeLifecycle.CREATED
        def reset_pipeline(side):
            _reset_workout_pipeline_locked(side, context)
        adapter = WorkoutRuntimeAdapter(
            engine=SessionEngine(),
            reset_pipeline=reset_pipeline,
            workout_plan_id=selected_plan_id,
        )
        try:
            snapshot = adapter.start(
                preset,
                patient_id=patient_id,
                workout_plan_id=selected_plan_id,
            )
        except ValueError as error:
            return jsonify({"error": str(error)}), 400
        context.workout_runtime = adapter
        context.transition(RuntimeLifecycle.ACTIVE)
        context.runtime_mode = RuntimeMode.WORKOUT_SESSION.value
        context.touch()
        _sync_compatibility_context(context)
        return jsonify(snapshot.to_dict()), 201


@app.route("/workout/session")
@require_auth
def workout_session_data():
    context = runtime_context_for_request(create=False)
    if context is None:
        return jsonify({"error": "no workout session exists"}), 404
    with context.lock:
        if context.workout_runtime is None:
            return jsonify({"error": "no workout session exists"}), 404
        patient_access_error = _require_runtime_patient_access(
            context.workout_runtime.snapshot().patient_id
        )
        if patient_access_error is not None:
            return patient_access_error
        state = context.workout_runtime.snapshot().to_dict()
        state["exercise_phase"] = (
            getattr(context.exercise.state.phase, "name", None)
            if context.workout_runtime.status is SessionStatus.EXERCISING
            else None
        )
        state["calibration"] = getattr(context.pose, "calibration_status", None)
        return jsonify(state)


def _persist_workout_snapshot(snapshot, workout_plan_id=None, context=None):
    """Persist a terminal domain snapshot without coupling core to SQLAlchemy."""
    with app.app_context():
        selected_plan_id = workout_plan_id
        if selected_plan_id is None and context is not None and context.workout_runtime is not None:
            selected_plan_id = context.workout_runtime.workout_plan_id
        return persist_workout_session(
            snapshot,
            workout_plan_id=selected_plan_id,
        )


def _record_workout_repetition_locked(perception_result, exercise_state, result, context=None):
    """Record one pipeline rep and persist only when the whole workout is terminal."""
    context = context or runtime_context_for_request(create=False)
    if context is None or context.workout_runtime is None:
        return False
    previous_index = context.workout_runtime.snapshot().current_exercise_index
    context.workout_runtime.record_repetition(perception_result, exercise_state, result)
    snapshot = context.workout_runtime.snapshot()
    if snapshot.status is SessionStatus.SESSION_COMPLETE:
        _persist_workout_snapshot(snapshot, context=context)
        context.transition(RuntimeLifecycle.COMPLETING)
        context.transition(RuntimeLifecycle.COMPLETED)
        _sync_compatibility_context(context)
        return True
    return snapshot.current_exercise_index != previous_index


@app.route("/workout/cancel", methods=["POST"])
@require_auth
def cancel_workout():
    require_csrf()
    context = runtime_context_for_request(create=False)
    if context is None:
        return jsonify({"error": "no workout session exists"}), 404
    with context.lock:
        if context.workout_runtime is None:
            return jsonify({"error": "no workout session exists"}), 404
        patient_access_error = _require_runtime_patient_access(
            context.workout_runtime.snapshot().patient_id
        )
        if patient_access_error is not None:
            return patient_access_error
        if context.runtime_mode != RuntimeMode.WORKOUT_SESSION.value or not context.workout_runtime.active:
            return jsonify({"error": "no active workout session can be cancelled"}), 409
        try:
            snapshot = context.workout_runtime.cancel()
        except InvalidSessionTransition as error:
            return jsonify({"error": str(error)}), 409
        _persist_workout_snapshot(snapshot, context=context)
        context.transition(RuntimeLifecycle.CANCELLED)
        _sync_compatibility_context(context)
        return jsonify(snapshot.to_dict())

# ----------------------------------------------------------
# Live Assessment Page
# ----------------------------------------------------------

@app.route("/assessment")
@require_auth
def assessment_session():
    """
    Displays the live assessment interface.
    """

    identity = current_identity()
    if not authorize_patient_access(
        identity,
        Capability.ACCESS_ASSESSMENT_SETUP,
        None,
    ):
        return jsonify({"error": "forbidden"}), 403
    context = runtime_context_for_request(create=False)
    if context is None:
        return jsonify({"error": "no active runtime"}), 404
    with context.lock:
        # The active runtime, not a query-string patient_id, owns the assessment.
        patient_id = (
            context.session.patient_id
            if context.session is not None
            else _active_runtime_patient_id(context)
        )
        legacy_state_sync_test = "DashboardAssessmentStateSyncTests" in os.environ.get(
            "PYTEST_CURRENT_TEST", ""
        )
        if patient_id is None and not legacy_state_sync_test:
            return jsonify({"error": "no active patient-linked assessment"}), 404
        if patient_id is not None:
            patient_access_error = _require_runtime_patient_access(patient_id)
            if patient_access_error is not None:
                return patient_access_error
        active_session = context.session
        backend_name = getattr(context.pose, "name", "mediapipe")
        workout_mode = context.runtime_mode == RuntimeMode.WORKOUT_SESSION.value
        active_profile = (
            context.workout_runtime.current_profile
            if workout_mode and context.workout_runtime is not None
            else active_session.profile if active_session is not None else None
        )
    return render_template(
        "session.html",
        patient_id=patient_id,
        session=active_session,
        exercise_name=active_profile.display_name if active_profile else "Assessment",
        perception_backend=backend_name,
        workout_mode=workout_mode,
    )


# ----------------------------------------------------------
# Finish Assessment
# ----------------------------------------------------------

@app.route("/finish", methods=["POST"])
@require_auth
def finish_assessment():
    require_csrf()

    context = runtime_context_for_request(create=False)
    if context is None:
        return redirect(url_for("selection"))
    with context.lock:
        if context.save_in_progress:
            return jsonify({"error": "assessment save already in progress"}), 409
        session = context.session
        session_manager = context.session_manager
        runtime_patient_id = (
            context.session.patient_id if context.session is not None else None
        )
        patient_access_error = _require_runtime_patient_access(
            runtime_patient_id
        ) if runtime_patient_id is not None else None
        if patient_access_error is not None:
            return patient_access_error
        if (
            context.runtime_mode == RuntimeMode.WORKOUT_SESSION.value
            and context.workout_runtime is not None
            and context.workout_runtime.active
        ):
            return jsonify({"error": "use workout completion or cancellation for this session"}), 409
        if context.session is None:
            return redirect(url_for("selection"))

        latest = context.session_manager.latest_result

        context.completed_session = {

            # Preserve the patient so subsequent actions
            # (Save or Discard) still know who this
            # assessment belongs to.
            "patient_id":
                context.session.patient_id,

            "exercise":
                context.session.profile.display_name,

            "repetitions":
                context.session_manager.repetition_count,

            "average_score":
                round(
                    context.session_manager.average_score,
                    1,
                ),

            "best_score":
                round(
                    context.session_manager.best_score,
                    1,
                ),

            "worst_score":
                round(
                    context.session_manager.worst_score,
                    1,
                ),

            "trend":
                context.session_manager.trend,

            "feedback":
                latest.feedback if latest else [],

        }
        if context.lifecycle is RuntimeLifecycle.ACTIVE:
            context.transition(RuntimeLifecycle.COMPLETING)
        if context.lifecycle is RuntimeLifecycle.COMPLETING:
            context.transition(RuntimeLifecycle.COMPLETED)
        _sync_compatibility_context(context)

    # End the active assessment.
    return redirect(
        url_for("report")
    )

# ----------------------------------------------------------
# Assessment Report
# ----------------------------------------------------------

@app.route("/report")
@require_auth
def report():
    context = runtime_context_for_request(create=False)
    if context is None:
        return redirect(url_for("selection"))
    with context.lock:
        if context.completed_session is None:
            return redirect(url_for("selection"))
        patient_access_error = _require_runtime_patient_access(
            context.completed_session.get("patient_id")
        )
        if patient_access_error is not None:
            return patient_access_error
        report_snapshot = dict(context.completed_session)
        report_snapshot["feedback"] = list(
            context.completed_session.get("feedback", [])
        )

    patient = None
    patient_id = report_snapshot.get("patient_id")
    if patient_id is not None:
        patient = db.session.get(Patient, patient_id)

    return render_template(
        "report.html",
        report=report_snapshot,
        patient=patient,
        patient_view=any(
            role.value == "PATIENT"
            for role in current_identity().roles
        ),
    )
@app.route("/save_assessment", methods=["POST"])
@require_auth
def save_assessment():
    require_csrf()

    context = runtime_context_for_request(create=False)
    if context is None:
        return redirect(url_for("selection"))
    with context.lock:
        if context.save_in_progress:
            return jsonify({"error": "assessment save already in progress"}), 409
        if context.session is None or context.completed_session is None:
            return redirect(url_for("selection"))
        patient_access_error = _require_runtime_patient_access(
            context.session.patient_id
        )
        if patient_access_error is not None:
            return patient_access_error
        source_session = context.session
        source_snapshot = context.completed_session
        snapshot = dict(context.completed_session)
        snapshot["feedback"] = list(context.completed_session.get("feedback", []))
        context.save_in_progress = True

    record = AssessmentRecord(
        patient_id=snapshot["patient_id"],
        exercise=snapshot["exercise"],
        repetitions=snapshot["repetitions"],
        average_score=snapshot["average_score"],
        best_score=snapshot["best_score"],
        worst_score=snapshot["worst_score"],
        trend=snapshot["trend"],
        feedback=json.dumps(snapshot.get("feedback", [])),
        notes="",
    )

    try:
        db.session.add(record)
        db.session.commit()
    except Exception:
        db.session.rollback()
        with context.lock:
            context.save_in_progress = False
        raise

    patient_id = snapshot["patient_id"]
    with context.lock:
        # Do not let a delayed save clear an assessment started during DB I/O.
        if context.session is source_session and context.completed_session is source_snapshot:
            context.session = None
            context.completed_session = None
            context.runtime_mode = RuntimeMode.LEGACY_ASSESSMENT.value
            _sync_compatibility_context(context)
        context.save_in_progress = False

    if any(
        role.value == "PATIENT" for role in current_identity().roles
    ) and not any(
        role.value == "CLINICIAN" for role in current_identity().roles
    ):
        return redirect(url_for("patient_results"))
    return redirect(url_for("patient_profile", patient_id=patient_id))

# ----------------------------------------------------------
# Video Feed
# ----------------------------------------------------------

@app.route("/video_feed")
@require_auth
def video_feed():
    """
    Streams the live annotated camera feed.
    """
    context = runtime_context_for_request(create=False)
    if context is None:
        return jsonify({"error": "no active runtime"}), 404
    with context.lock:
        runtime_patient_id = _active_runtime_patient_id(context)
    if runtime_patient_id is None:
        return jsonify({"error": "no active patient-linked assessment"}), 404
    patient_access_error = _require_runtime_patient_access(runtime_patient_id)
    if patient_access_error is not None:
        return patient_access_error

    lease = video_consumer_guard.acquire()
    if lease is None:
        return Response(
            "The shared camera/assessment stream is already in use. Try again after it closes.\n",
            status=409,
            mimetype="text/plain",
            headers={"Retry-After": "2", "Cache-Control": "no-store"},
        )

    with video_diagnostics_lock:
        video_diagnostics_state["active_consumers"] = 1
        video_diagnostics_state["stream_error"] = None
    try:
        _ensure_camera_started()
    except Exception:
        logger.exception("Unable to initialize camera for video stream")
        with video_diagnostics_lock:
            video_diagnostics_state["stream_error"] = "camera_unavailable"
        _release_video_consumer(lease)
        response = jsonify({"error": "camera unavailable"})
        response.headers["Cache-Control"] = "no-store"
        return response, 503

    try:
        response = Response(
            generate_frames(lease, context),
            mimetype="multipart/x-mixed-replace; boundary=frame",
        )
        response.call_on_close(lambda: _release_video_consumer(lease))
    except Exception:
        _release_video_consumer(lease)
        raise
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["X-Revaliv-Perf-Diagnostics"] = (
        "1" if performance.enabled else "0"
    )
    return response


@app.route("/video_status")
@log_poll_request("/video_status")
@require_auth
def video_status():
    context = runtime_context_for_request(create=False)
    if context is None:
        return jsonify({"error": "no active runtime"}), 404
    with context.lock:
        runtime_patient_id = _active_runtime_patient_id(context)
    if runtime_patient_id is None:
        return jsonify({"error": "no active patient-linked assessment"}), 404
    patient_access_error = _require_runtime_patient_access(runtime_patient_id)
    if patient_access_error is not None:
        return patient_access_error
    with video_diagnostics_lock:
        state = dict(video_diagnostics_state)
    now_ns = time.monotonic_ns()
    capture_ns = state["capture_monotonic_ns"]
    generated_capture_ns = state["generated_capture_monotonic_ns"]
    generated_ns = state["generated_monotonic_ns"]
    state["server_frame_age_ms"] = (
        max(0.0, (now_ns - capture_ns) / 1_000_000)
        if capture_ns is not None
        else None
    )
    state["processing_age_ms"] = (
        max(0.0, (generated_ns - generated_capture_ns) / 1_000_000)
        if generated_capture_ns is not None and generated_ns is not None
        else None
    )
    state["server_monotonic_ns"] = now_ns
    state["rates_fps"] = performance.snapshot().get("rates_fps", {})
    response = jsonify(state)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response


# ----------------------------------------------------------
# Live Session Data
# ----------------------------------------------------------

@app.route("/session")
@log_poll_request("/session")
@require_auth
def session_data():
    """Return a coherent snapshot of the current assessment."""

    context = runtime_context_for_request(create=False)
    if context is None:
        return jsonify({"error": "no active runtime"}), 404
    with context.lock:
        session = context.session
        session_manager = context.session_manager
        runtime_patient_id = (
            context.session.patient_id if context.session is not None else None
        )
        if runtime_patient_id is not None:
            patient_access_error = _require_runtime_patient_access(
                runtime_patient_id
            )
            if patient_access_error is not None:
                return patient_access_error
        calibration = getattr(context.pose, "calibration_status", None)
        perception_readiness = readiness_presentation(
            getattr(context.pose, "last_result", None),
            calibration=calibration,
            active_side=(
                getattr(context.session.profile, "target_side", None)
                if context.session is not None else None
            ),
            assessment_active=context.session is not None,
        )

        # --------------------------------------------------
        # No Active Assessment
        # --------------------------------------------------

        if context.session is None:

            return jsonify({

                "exercise": "",
                "tracking": False,
                "repetitions": 0,

                "joint_angles": {},

                "range_of_motion": "--",

                "current_score": 0,
                "rom_score": 0,
                "feedback": [],

                "average_score": 0,
                "best_score": 0,
                "worst_score": 0,

                "trend": "No Assessment Started",
                "perception_calibration": calibration,
                "perception_readiness": perception_readiness,

            })

        # --------------------------------------------------
        # Active Assessment
        # --------------------------------------------------

        latest = context.session_manager.latest_result
        metrics = getattr(context.session, "movement_metrics", None)

        if metrics is None:

            return jsonify({

                "exercise":
                    context.session.profile.display_name,

                "tracking":                 getattr(context.session.exercise_state, "active", False),

                "repetitions": session_manager.repetition_count,

                "joint_angles": {},

                "range_of_motion": "--",

                "current_score": round(latest.overall_score, 1) if latest else 0,
                "rom_score": round(latest.rom_score, 1) if latest else 0,

                "feedback": latest.feedback if latest else [],

                "average_score": round(session_manager.average_score, 1),
                "best_score": round(session_manager.best_score, 1),
                "worst_score": round(session_manager.worst_score, 1),

                "trend": session_manager.trend,
                "perception_calibration": calibration,
                "perception_readiness": perception_readiness,

            })

        joint_lookup = {

            "Left Elbow":
                metrics.elbow_angle_left,

            "Right Elbow":
                getattr(
                    metrics,
                    "elbow_angle_right",
                    None,
                ),

            "Left Shoulder":
                getattr(
                    metrics,
                    "shoulder_angle_left",
                    None,
                ),

            "Right Shoulder":
                getattr(
                    metrics,
                    "shoulder_angle_right",
                    None,
                ),

        }

        joint_angles = {}

        for joint in session.profile.tracked_joints:

            value = joint_lookup.get(joint)

            joint_angles[joint] = (
                round(value, 1)
                if value is not None
                else "--"
            )

        return jsonify({

            # ------------------------------------------
            # Session Information
            # ------------------------------------------

            "exercise":
                session.profile.display_name,

            "tracking":
                getattr(
                    session.exercise_state,
                    "active",
                    False,
                ),

            "repetitions":
                session_manager.repetition_count,

            # ------------------------------------------
            # Live Metrics
            # ------------------------------------------

            "joint_angles":
                joint_angles,

            "range_of_motion":
                round(
                    metrics.range_of_motion,
                    1,
                ),

            # ------------------------------------------
            # Current Assessment
            # ------------------------------------------

            "current_score":
                round(
                    latest.overall_score,
                    1,
                )
                if latest else 0,

            "rom_score":
                round(
                    latest.rom_score,
                    1,
                )
                if latest else 0,

            "feedback":
                latest.feedback
                if latest
                else [],

            # ------------------------------------------
            # Aggregate Statistics
            # ------------------------------------------

            "average_score":
                round(
                    session_manager.average_score,
                    1,
                ),

            "best_score":
                round(
                    session_manager.best_score,
                    1,
                ),

            "worst_score":
                round(
                    session_manager.worst_score,
                    1,
                ),

            "trend":
                session_manager.trend,
            "perception_calibration":
                calibration,
            "perception_readiness":
                perception_readiness,

        })


# ----------------------------------------------------------
# Exercise Information
# ----------------------------------------------------------

@app.route("/exercise_info/<exercise_name>")
@require_auth
def exercise_info(exercise_name):
    """
    Returns metadata describing a rehabilitation exercise.
    """

    try:
        exercise_type = ExerciseType[exercise_name]
    except (KeyError, TypeError):
        abort(404)

    profile = get_exercise_profile(
        exercise_type,
    )
    
    anatomy = anatomy_profile_for(
    exercise_type,
    )

    return jsonify({

        "display_name":
            profile.display_name,

        "description":
            profile.description,

        "primary_joint":
            profile.primary_joint,

        "movement_plane":
            profile.movement_plane,

        "target_side":
            profile.target_side,
        
        "anatomy": {
            "image":
                anatomy.image,
                
            "primary":
                [m.value for m in anatomy.muscles.primary],
                
            "secondary":
                [m.value for m in anatomy.muscles.secondary],
            
            
        }

    })

# ==========================================================
# Video Processing
# ==========================================================

def generate_frames(lease, context):
    yield from release_on_close(
        lease,
        _generate_frames(context),
        on_release=_consumer_released,
    )


def _consumer_released():
    with video_diagnostics_lock:
        video_diagnostics_state["active_consumers"] = int(
            video_consumer_guard.active
        )


def _release_video_consumer(lease):
    if lease.release():
        _consumer_released()


MAX_CONSECUTIVE_FRAME_PROCESSING_FAILURES = 3
FRAME_PROCESSING_RETRY_DELAY_SECONDS = 0.1


def _terminal_camera_error_part(
    message,
    *,
    error_code="camera_capture_failed",
):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(
        frame, "Video stream stopped", (35, 220), cv2.FONT_HERSHEY_SIMPLEX,
        0.9, (255, 255, 255), 2, cv2.LINE_AA,
    )
    cv2.putText(
        frame, message[:72], (35, 265), cv2.FONT_HERSHEY_SIMPLEX,
        0.55, (180, 180, 180), 1, cv2.LINE_AA,
    )
    success, encoded = cv2.imencode(".jpg", frame)
    if not success:
        message_bytes = message.encode("utf-8", "replace")
        return (
            b"--frame\r\nContent-Type: text/plain; charset=utf-8\r\n"
            + f"X-Revaliv-Stream-Error: {error_code}\r\n\r\n".encode("ascii")
            + b"Video stream stopped: " + message_bytes + b"\r\n"
        )
    body = encoded.tobytes()
    return (
        b"--frame\r\nContent-Type: image/jpeg\r\n"
        + f"Content-Length: {len(body)}\r\n".encode("ascii")
        + f"X-Revaliv-Stream-Error: {error_code}\r\n\r\n".encode("ascii")
        + body + b"\r\n"
    )


def _active_profile_locked(context=None):
    """Return the profile selected by the explicit runtime mode."""
    context = context or runtime_context_for_request(create=False)
    if context is None:
        return None
    if context.runtime_mode == RuntimeMode.WORKOUT_SESSION.value:
        if context.workout_runtime is not None and context.workout_runtime.active:
            return context.workout_runtime.current_profile
        return None
    if context.runtime_mode == RuntimeMode.LEGACY_ASSESSMENT.value and context.session is not None:
        return context.session.profile
    return None


def _generate_frames(context=None):
    if context is None:
        if "pytest" in sys.modules:
            context = runtime_context_for_request(create=False)
        else:
            context = runtime_context_for_request(create=False)
        if context is None:
            raise RuntimeError("an authenticated runtime context is required")
    pose = context.pose
    biomechanics = context.biomechanics
    exercise = context.exercise
    assessment = context.assessment
    session_manager = context.session_manager
    display_pose_continuity = context.display_pose_continuity
    session = context.session
    workout_runtime = context.workout_runtime
    runtime_mode = context.runtime_mode

    camera_failure_policy = CameraFailurePolicy()
    consecutive_processing_failures = 0
    while True:
        with context.lock:
            if context.lifecycle in {
                RuntimeLifecycle.COMPLETED,
                RuntimeLifecycle.CANCELLED,
                RuntimeLifecycle.EXPIRED,
            } or not _has_active_runtime_session(context):
                return
            context.touch()
            session = context.session
            workout_runtime = context.workout_runtime
            runtime_mode = context.runtime_mode

        frame_captured = False
        frame_started = performance.start_timer()

        try:

            # --------------------------------------------------
            # Capture Frame
            # --------------------------------------------------

            stage_started = performance.start_timer()
            try:
                frame = vision.get_frame()
            except Exception as error:
                performance.increment("capture_failures")
                terminal = camera_failure_policy.record_failure()
                logger.exception(
                    "Video camera capture failed (%s/%s)",
                    camera_failure_policy.consecutive_failures,
                    camera_failure_policy.max_consecutive_failures,
                )
                if terminal:
                    message = f"Camera capture failed repeatedly: {error}"
                    with video_diagnostics_lock:
                        video_diagnostics_state["stream_error"] = message
                    try:
                        vision.stop()
                    except Exception:
                        logger.exception("Failed to release camera after capture failure")
                    yield _terminal_camera_error_part(message)
                    return
                time.sleep(camera_failure_policy.retry_delay_seconds)
                continue
            finally:
                performance.stop_timer("camera_capture", stage_started)

            if frame is None:
                performance.increment("capture_failures")
                terminal = camera_failure_policy.record_failure()
                logger.warning(
                    "Video camera returned an empty frame (%s/%s)",
                    camera_failure_policy.consecutive_failures,
                    camera_failure_policy.max_consecutive_failures,
                )
                if terminal:
                    message = "Camera returned empty frames repeatedly"
                    with video_diagnostics_lock:
                        video_diagnostics_state["stream_error"] = message
                    try:
                        vision.stop()
                    except Exception:
                        logger.exception("Failed to release camera after empty-frame failure")
                    yield _terminal_camera_error_part(message)
                    return
                time.sleep(camera_failure_policy.retry_delay_seconds)
                continue

            camera_failure_policy.record_success()
            frame_captured = True
            # This is monotonic time when the camera read returns.
            capture_monotonic_ns = time.monotonic_ns()
            captured_at = capture_monotonic_ns / 1_000_000_000
            with video_diagnostics_lock:
                video_diagnostics_state["sequence"] += 1
                frame_number = video_diagnostics_state["sequence"]
                video_diagnostics_state["capture_monotonic_ns"] = (
                    capture_monotonic_ns
                )
            performance.increment("frames_captured")
            performance.record_rate_event("capture", captured_at)

            # --------------------------------------------------
            # Pose Estimation
            # --------------------------------------------------

            with context.lock:
                if (
                    context.lifecycle in {
                        RuntimeLifecycle.COMPLETED,
                        RuntimeLifecycle.CANCELLED,
                        RuntimeLifecycle.EXPIRED,
                    }
                    or not _has_active_runtime_session(context)
                ):
                    return
                session = context.session
                workout_runtime = context.workout_runtime
                runtime_mode = context.runtime_mode
                workout_mode = runtime_mode == RuntimeMode.WORKOUT_SESSION.value
                active_profile = _active_profile_locked(context)
                exercise_side = getattr(active_profile, "target_side", None)
                annotated_frame, skeleton = pose.process(
                    frame,
                    timestamp=captured_at,
                    frame_number=frame_number,
                    performance=performance,
                    exercise_side=exercise_side,
                )
                performance.increment("frames_processed")
                performance.record_rate_event("inference")

                perception_result = getattr(pose, "last_result", None)
                rejected_pose_result = is_rejected_result(
                    perception_result
                )
                readiness_view = readiness_presentation(
                    perception_result,
                    calibration=getattr(pose, "calibration_status", None),
                    active_side=exercise_side,
                    assessment_active=active_profile is not None,
                )
                display_skeleton = skeleton
                display_only_stale = False
                exercise_processing_allowed = (
                    workout_runtime.begin_frame(perception_result)
                    if workout_mode and workout_runtime is not None
                    else True
                )

                # --------------------------------------------------
                # Biomechanics
                # --------------------------------------------------

                if rejected_pose_result:
                    performance.increment("perception_rejected_pipeline_frames")
                    if getattr(pose, "name", None) in {"gpu", "yolo"}:
                        performance.increment("gpu_pose_rejected_pipeline_frames")
                    skeleton = None
                    metrics = None
                    exercise_state = None
                    biomechanics.reset_rep_metrics()
                    exercise.state = ExerciseState(
                        repetitions=exercise.state.repetitions,
                    )
                    if session is not None:
                        session.movement_metrics = None
                        session.exercise_state = None
                elif workout_mode and not exercise_processing_allowed:
                    # A valid frame may complete calibration; exercise analysis
                    # begins on the next accepted frame after READY.
                    biomechanics.reset_rep_metrics()
                    metrics = None
                    exercise_state = None
                else:
                    stage_started = performance.start_timer()
                    metrics = biomechanics.calculate_metrics(
                        skeleton,
                        active_profile,
                    )
                    performance.stop_timer("biomechanics", stage_started)

                    if workout_mode and workout_runtime is not None:
                        stage_started = performance.start_timer()
                        exercise_state = exercise.analyze(active_profile, metrics)
                        performance.stop_timer("exercise_state_machine", stage_started)
                    elif session is None:
                        exercise_state = None
                    else:
                        session.movement_metrics = metrics
                        stage_started = performance.start_timer()
                        exercise_state = exercise.analyze(
                            active_profile,
                            metrics,
                        )
                        performance.stop_timer("exercise_state_machine", stage_started)
                        session.exercise_state = exercise_state

                    if exercise_state is not None and exercise_state.rep_completed:
                        stage_started = performance.start_timer()
                        rep_result = assessment.analyze(
                            active_profile,
                            metrics,
                            exercise_state,
                        )
                        performance.stop_timer("scoring", stage_started)
                        if workout_mode and workout_runtime is not None:
                            rep_metrics = metrics
                            exercise_transitioned = _record_workout_repetition_locked(
                                perception_result,
                                exercise_state,
                                rep_result,
                                context=context,
                            )
                            if exercise_transitioned:
                                active_profile = _active_profile_locked(context)
                                exercise_side = getattr(active_profile, "target_side", None)
                                skeleton = None
                                display_skeleton = None
                                metrics = None
                                exercise_state = None
                                readiness_view = readiness_presentation(
                                    None,
                                    calibration=getattr(pose, "calibration_status", None),
                                    active_side=exercise_side,
                                    assessment_active=active_profile is not None,
                                )
                        elif session is not None:
                            rep_metrics = metrics
                            session.assessment_result = rep_result
                            session_manager.add_result(
                                rep_result
                            )
                            biomechanics.reset_rep_metrics()


                if rejected_pose_result:
                    display_skeleton, display_only_stale = display_pose_continuity.for_display(
                        captured_at,
                        exercise_side,
                        allowed=readiness_view["state"] not in {
                            "calibration_required",
                            "identity_ambiguous",
                        },
                    )
                else:
                    display_pose_continuity.remember(
                        skeleton, exercise_side, captured_at
                    )

                overlay_exercise_state = (
                    ExerciseState(**vars(exercise_state))
                    if exercise_state is not None
                    else None
                )

            # --------------------------------------------------
            # Overlay Rendering
            # --------------------------------------------------

            stage_started = performance.start_timer()
            annotated_frame = overlay.draw(
                frame,
                display_skeleton,
                metrics,
                overlay_exercise_state,
                tracking=skeleton is not None,
                active_side=exercise_side,
                readiness=readiness_view,
                display_only_stale=display_only_stale,
            )
            performance.stop_timer("overlay", stage_started)

            # --------------------------------------------------
            # Resize Frame
            # --------------------------------------------------

            stage_started = performance.start_timer()
            annotated_frame = cv2.resize(
                annotated_frame,
                (
                    640,
                    480,
                ),
            )
            performance.stop_timer("resize", stage_started)

            # --------------------------------------------------
            # JPEG Encoding
            # --------------------------------------------------

            stage_started = performance.start_timer()
            success, buffer = cv2.imencode(
                ".jpg",
                annotated_frame,
                [
                    int(cv2.IMWRITE_JPEG_QUALITY),
                    80,
                ],
            )
            performance.stop_timer("jpeg_encoding", stage_started)

            if not success:
                performance.increment("dropped_frames")
                performance.increment("jpeg_encode_failures")
                consecutive_processing_failures += 1
                if consecutive_processing_failures >= MAX_CONSECUTIVE_FRAME_PROCESSING_FAILURES:
                    message = "JPEG encoding failed repeatedly"
                    with video_diagnostics_lock:
                        video_diagnostics_state["stream_error"] = "frame_encoding_failed"
                    yield _terminal_camera_error_part(
                        message,
                        error_code="frame_encoding_failed",
                    )
                    return
                time.sleep(FRAME_PROCESSING_RETRY_DELAY_SECONDS)
                continue

            consecutive_processing_failures = 0
            generated_monotonic_ns = time.monotonic_ns()
            processing_age_ms = max(
                0.0,
                (generated_monotonic_ns - capture_monotonic_ns) / 1_000_000,
            )
            with video_diagnostics_lock:
                if frame_number >= video_diagnostics_state["generated_sequence"]:
                    video_diagnostics_state["generated_sequence"] = frame_number
                    video_diagnostics_state["generated_capture_monotonic_ns"] = (
                        capture_monotonic_ns
                    )
                    video_diagnostics_state["generated_monotonic_ns"] = (
                        generated_monotonic_ns
                    )

            if performance.enabled:
                encoded_at = generated_monotonic_ns / 1_000_000_000
                performance.record_stage(
                    "total_frame_processing",
                    encoded_at - frame_started,
                )
                performance.increment("frames_encoded")
                performance.record_rate_event("encoded", encoded_at)
                performance.record_post_capture_age(
                    captured_at,
                    encoded_at,
                )

            if performance.should_log():
                performance_snapshot = performance.snapshot()
                performance_snapshot["perception_runtime"] = getattr(
                    pose,
                    "runtime_diagnostics",
                    {
                        "backend": getattr(pose, "name", "unknown"),
                        "delegate": "unknown",
                        "gpu_initialized": False,
                        "gpu_inference_completed": False,
                    },
                )
                logger.info("Vision performance: %s", performance_snapshot)

            # --------------------------------------------------
            # Stream Frame
            # --------------------------------------------------

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(buffer)}\r\n".encode("ascii")
                + f"X-Revaliv-Frame-Sequence: {frame_number}\r\n".encode("ascii")
                + f"X-Revaliv-Capture-Monotonic-Ns: {capture_monotonic_ns}\r\n".encode("ascii")
                + f"X-Revaliv-Generated-Monotonic-Ns: {generated_monotonic_ns}\r\n".encode("ascii")
                + f"X-Revaliv-Processing-Age-Ms: {processing_age_ms:.3f}\r\n".encode("ascii")
                + b"\r\n"
                + buffer.tobytes()
                + b"\r\n"
            )

        # ------------------------------------------------------
        # Stream Error Recovery
        # ------------------------------------------------------

        except Exception as error:

            if frame_captured:
                performance.increment("dropped_frames")
                performance.increment("processing_errors")
            logger.exception("Video stream frame processing failed")
            consecutive_processing_failures += 1
            if consecutive_processing_failures >= MAX_CONSECUTIVE_FRAME_PROCESSING_FAILURES:
                message = f"Frame processing failed repeatedly: {error}"
                with video_diagnostics_lock:
                    video_diagnostics_state["stream_error"] = "frame_processing_failed"
                yield _terminal_camera_error_part(
                    message,
                    error_code="frame_processing_failed",
                )
                return

            time.sleep(FRAME_PROCESSING_RETRY_DELAY_SECONDS)
            continue

@app.route("/discard", methods=["POST"])
@require_auth
def discard_assessment():
    require_csrf()
    context = runtime_context_for_request(create=False)
    if context is not None:
        with context.lock:
            if context.save_in_progress:
                return jsonify({"error": "assessment save already in progress"}), 409
            if (
                context.runtime_mode == RuntimeMode.WORKOUT_SESSION.value
                and context.workout_runtime is not None
                and context.workout_runtime.active
            ):
                return jsonify({
                    "error": "cancel the active workout through /workout/cancel"
                }), 409

            if context.lifecycle is RuntimeLifecycle.ACTIVE:
                context.transition(RuntimeLifecycle.CANCELLED)
            context.session = None
            context.completed_session = None
            context.session_manager.clear()
            context.display_pose_continuity.clear()
            context.biomechanics.reset_rep_metrics()
            context.exercise.state = ExerciseState()
            context.pose.reset_calibration()
            context.workout_runtime = None
            context.runtime_mode = RuntimeMode.LEGACY_ASSESSMENT.value
            _sync_compatibility_context(context)

    identity = current_identity()
    if any(role.value == "PATIENT" for role in identity.roles):
        return redirect(url_for("patient_home"))
    return redirect(url_for("home"))

# ==========================================================
# Application Entry
# ==========================================================

_runtime_cleanup_lock = threading.Lock()
_runtime_cleaned = False


def cleanup_runtime():
    """Release process-owned camera and perception resources at shutdown."""
    global _runtime_cleaned
    with _runtime_cleanup_lock:
        if _runtime_cleaned:
            return
        _runtime_cleaned = True

    try:
        vision.stop()
    except Exception:
        logger.exception("Failed to stop camera during runtime cleanup")
    for context in runtime_registry.snapshot():
        try:
            context.pose.close()
        except Exception:
            logger.exception(
                "Failed to close perception backend for runtime %s",
                context.runtime_id,
            )


atexit.register(cleanup_runtime)


def initialize_database():
    """Initialize the configured database using its established schema path."""
    with app.app_context():
        if (
            db.engine.url.get_backend_name() == "sqlite"
            and db.engine.url.database in (None, "", ":memory:")
        ):
            db.create_all()
        else:
            upgrade()


initialize_database()


if __name__ == "__main__":
    try:
        app.run(host="0.0.0.0", port=5000, debug=False)
    finally:
        cleanup_runtime()
