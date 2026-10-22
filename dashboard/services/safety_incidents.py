"""Safety-case workflow and corrective-action controls.

Risk tiers here are conservative software triage heuristics, not clinically
validated risk predictions. Critical reports trigger precautionary activation
restrictions by default. A linked SHA-256 event chain detects tampering but
must be externally anchored to provide strong tamper evidence.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import hmac
import json
import math
import uuid

from dashboard.database import db
from dashboard.models.identity import User
from dashboard.models.safety import (
    SafetyCorrectiveAction,
    SafetyIncident,
    SafetyIncidentEvent,
)


SEVERITY_VALUES = {"low": 1, "moderate": 3, "serious": 6, "critical": 10}
LIKELIHOOD_VALUES = {"unlikely": 1, "possible": 2, "likely": 4, "very_likely": 5}
EVIDENCE_VALUES = {"weak": 2, "moderate": 4, "strong": 6}
SUPPORTED_RESTRICTION_SCOPES = {
    "workout_activation",
    "clinical_assessment_start",
    "plan_activation",
    "camera_measurement",
    "data_export",
}
DEFAULT_CRITICAL_RESTRICTIONS = (
    "workout_activation",
    "clinical_assessment_start",
    "plan_activation",
)
SAFETY_LEAD_ROLES = {"ADMIN", "CLINICIAN", "OPERATOR"}
_EMPTY_HASH = "0" * 64
_MAX_SUMMARY = 500
_MAX_DETAILS = 10000
_MAX_RATIONALE = 4000


class SafetyWorkflowError(ValueError):
    """Safe, expected refusal from a safety lifecycle transition."""


class SafetyRestrictionError(RuntimeError):
    """An active safety hold prevents a requested clinical operation."""

    def __init__(self, scope: str, incidents: list[SafetyIncident]):
        self.scope = scope
        self.incidents = incidents
        keys = ", ".join(incident.incident_key for incident in incidents)
        super().__init__(
            f"operation blocked by active safety restriction for {scope}; "
            f"incident reference(s): {keys}"
        )


def _active_user(user_id: int) -> User:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise SafetyWorkflowError("a valid active user is required")
    user = db.session.get(User, user_id)
    if user is None or user.status != "ACTIVE":
        raise SafetyWorkflowError("user does not exist or is disabled")
    return user


def _require_safety_lead(user_id: int) -> User:
    user = _active_user(user_id)
    roles = {role.name for role in user.roles}
    if not roles.intersection(SAFETY_LEAD_ROLES):
        raise SafetyWorkflowError("active safety-lead authorization is required")
    return user


def _validate_text(value, field: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise SafetyWorkflowError(f"{field} must be text")
    normalized = value.strip()
    if not minimum <= len(normalized) <= maximum:
        raise SafetyWorkflowError(
            f"{field} must be between {minimum} and {maximum} characters"
        )
    return normalized


def _risk_score(
    severity: str,
    likelihood: str,
    evidence_strength: str,
    exposure_count: int,
    control_failure: bool,
) -> tuple[float, str]:
    if severity not in SEVERITY_VALUES:
        raise SafetyWorkflowError("severity must be low, moderate, serious, or critical")
    if likelihood not in LIKELIHOOD_VALUES:
        raise SafetyWorkflowError("likelihood must be unlikely, possible, likely, or very_likely")
    if evidence_strength not in EVIDENCE_VALUES:
        raise SafetyWorkflowError("evidence_strength must be weak, moderate, or strong")
    if isinstance(exposure_count, bool) or not isinstance(exposure_count, int) or exposure_count < 1:
        raise SafetyWorkflowError("exposure_count must be a positive integer")
    if not isinstance(control_failure, bool):
        raise SafetyWorkflowError("control_failure must be Boolean")

    if exposure_count <= 2:
        exposure_band = 1
    elif exposure_count <= 10:
        exposure_band = 2
    elif exposure_count <= 100:
        exposure_band = 3
    else:
        exposure_band = 4

    score = float(
        SEVERITY_VALUES[severity] * 2
        + LIKELIHOOD_VALUES[likelihood] * exposure_band
        + EVIDENCE_VALUES[evidence_strength]
        + (5 if control_failure else 0)
    )
    # Severity dominates weak or incomplete evidence by design.
    if severity == "critical" or (severity == "serious" and control_failure):
        tier = "critical"
    elif score >= 22:
        tier = "urgent"
    elif score >= 13:
        tier = "elevated"
    else:
        tier = "routine"
    return score, tier


def _response_hours(priority_tier: str) -> int:
    return {"critical": 1, "urgent": 4, "elevated": 24, "routine": 72}[priority_tier]


def _normalize_scopes(scopes) -> list[str]:
    if scopes is None:
        return []
    if not isinstance(scopes, list) or any(not isinstance(scope, str) for scope in scopes):
        raise SafetyWorkflowError("restriction_scopes must be a list of strings")
    normalized = sorted(set(scope.strip().lower() for scope in scopes))
    unsupported = sorted(set(normalized) - SUPPORTED_RESTRICTION_SCOPES)
    if unsupported:
        raise SafetyWorkflowError("unsupported restriction scope(s): " + ", ".join(unsupported))
    return normalized


def _event_payload(
    incident_id: int,
    actor_user_id: int,
    event_type: str,
    previous_status: str,
    new_status: str,
    detail: str,
    occurred_at: datetime,
    previous_hash: str,
) -> bytes:
    value = {
        "incident_id": incident_id,
        "actor_user_id": actor_user_id,
        "event_type": event_type,
        "previous_status": previous_status,
        "new_status": new_status,
        "detail": detail,
        "occurred_at": occurred_at.isoformat(timespec="microseconds"),
        "previous_hash": previous_hash,
    }
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def verify_safety_event_chain(incident_id: int) -> bool:
    incident = db.session.get(SafetyIncident, incident_id)
    if incident is None:
        return False
    events = SafetyIncidentEvent.query.filter_by(incident_id=incident_id).order_by(
        SafetyIncidentEvent.event_id
    ).all()
    if not events:
        return False
    expected_previous = _EMPTY_HASH
    for event in events:
        if event.previous_hash != expected_previous:
            return False
        digest = hashlib.sha256(_event_payload(
            event.incident_id,
            event.actor_user_id,
            event.event_type,
            event.previous_status,
            event.new_status,
            event.detail,
            event.occurred_at,
            event.previous_hash,
        )).hexdigest()
        if not hmac.compare_digest(digest, event.event_hash):
            return False
        expected_previous = event.event_hash
    return events[-1].new_status == incident.status


def _append_event(
    incident: SafetyIncident,
    actor_user_id: int,
    event_type: str,
    previous_status: str,
    detail: str,
) -> SafetyIncidentEvent:
    latest = SafetyIncidentEvent.query.filter_by(incident_id=incident.incident_id).order_by(
        SafetyIncidentEvent.event_id.desc()
    ).first()
    previous_hash = latest.event_hash if latest is not None else _EMPTY_HASH
    occurred_at = datetime.utcnow()
    digest = hashlib.sha256(_event_payload(
        incident.incident_id,
        actor_user_id,
        event_type,
        previous_status,
        incident.status,
        detail,
        occurred_at,
        previous_hash,
    )).hexdigest()
    event = SafetyIncidentEvent(
        incident_id=incident.incident_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        previous_status=previous_status,
        new_status=incident.status,
        detail=detail,
        occurred_at=occurred_at,
        previous_hash=previous_hash,
        event_hash=digest,
    )
    db.session.add(event)
    return event


def _guard_chain(incident: SafetyIncident):
    if SafetyIncidentEvent.query.filter_by(incident_id=incident.incident_id).count() and not verify_safety_event_chain(
        incident.incident_id
    ):
        raise SafetyWorkflowError(
            "safety event history failed integrity verification; lifecycle transition blocked"
        )


def report_safety_incident(
    reporter_user_id: int,
    *,
    category: str,
    summary: str,
    details: str = "",
    severity: str,
    likelihood: str,
    evidence_strength: str,
    exposure_count: int = 1,
    control_failure: bool = False,
    restriction_scopes=None,
    restriction_reason: str | None = None,
) -> SafetyIncident:
    reporter = _active_user(reporter_user_id)
    category = _validate_text(category, "category", 2, 60)
    summary = _validate_text(summary, "summary", 8, _MAX_SUMMARY)
    details = _validate_text(details, "details", 0, _MAX_DETAILS)
    score, tier = _risk_score(
        severity, likelihood, evidence_strength, exposure_count, control_failure
    )
    scopes = _normalize_scopes(restriction_scopes)
    if tier == "critical":
        scopes = sorted(set(scopes).union(DEFAULT_CRITICAL_RESTRICTIONS))
    if scopes and (not isinstance(restriction_reason, str) or not restriction_reason.strip()):
        if tier == "critical":
            restriction_reason = (
                "Precautionary critical-risk hold pending independent triage."
            )
        else:
            raise SafetyWorkflowError("restriction_reason is required when imposing a hold")
    now = datetime.utcnow()
    due = now + timedelta(hours=_response_hours(tier))
    status = "restricted" if scopes else "reported"
    incident = SafetyIncident(
        incident_key=str(uuid.uuid4()),
        category=category,
        summary=summary,
        details=details,
        severity=severity,
        likelihood=likelihood,
        evidence_strength=evidence_strength,
        exposure_count=exposure_count,
        control_failure=control_failure,
        risk_score=score,
        priority_tier=tier,
        status=status,
        restriction_scopes=json.dumps(scopes),
        restriction_reason=restriction_reason.strip() if restriction_reason else None,
        reporter_user_id=reporter.user_id,
        reported_at=now,
        next_review_at=due,
        response_due_at=due,
        created_at=now,
        updated_at=now,
    )
    try:
        db.session.add(incident)
        db.session.flush()
        detail = json.dumps({
            "priority_tier": tier,
            "risk_score": score,
            "restriction_scopes": scopes,
            "policy_version": "provisional-risk-triage-v1",
        }, sort_keys=True)
        _append_event(
            incident, reporter.user_id,
            "reported_and_restricted" if scopes else "reported",
            "reported", detail,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return incident


def triage_safety_incident(
    incident_id: int,
    actor_user_id: int,
    *,
    owner_user_id: int | None = None,
    root_cause_status: str | None = None,
    root_cause_notes: str | None = None,
    restriction_scopes=None,
    restriction_reason: str | None = None,
) -> SafetyIncident:
    actor = _require_safety_lead(actor_user_id)
    incident = db.session.get(SafetyIncident, incident_id)
    if incident is None:
        raise LookupError(f"safety incident {incident_id} does not exist")
    if incident.status == "closed":
        raise SafetyWorkflowError("closed incidents must be reopened before triage")
    _guard_chain(incident)
    old_status = incident.status

    if owner_user_id is not None:
        owner = _active_user(owner_user_id)
        if not ({role.name for role in owner.roles} & SAFETY_LEAD_ROLES):
            raise SafetyWorkflowError("investigation owner must have safety-lead authorization")
        incident.owner_user_id = owner.user_id

    if root_cause_status is not None:
        if root_cause_status not in {"not_assessed", "known", "unknown"}:
            raise SafetyWorkflowError("root_cause_status must be not_assessed, known, or unknown")
        notes = (root_cause_notes or "").strip()
        if root_cause_status in {"known", "unknown"} and len(notes) < 8:
            raise SafetyWorkflowError("root-cause rationale is required for known or unknown status")
        if len(notes) > _MAX_DETAILS:
            raise SafetyWorkflowError("root-cause rationale is too long")
        incident.root_cause_status = root_cause_status
        incident.root_cause_notes = notes or None

    if restriction_scopes is not None:
        scopes = _normalize_scopes(restriction_scopes)
        if incident.priority_tier == "critical":
            scopes = sorted(set(scopes).union(DEFAULT_CRITICAL_RESTRICTIONS))
        if scopes:
            if not isinstance(restriction_reason, str) or len(restriction_reason.strip()) < 8:
                raise SafetyWorkflowError("restriction_reason is required for an active restriction")
            incident.restriction_scopes = json.dumps(scopes)
            incident.restriction_reason = restriction_reason.strip()
            incident.status = "restricted"
        else:
            incident.restriction_scopes = "[]"
            incident.restriction_reason = None
            incident.status = "investigating"
    elif incident.status in {"reported", "reopened"}:
        incident.status = "restricted" if json.loads(incident.restriction_scopes or "[]") else "investigating"

    if incident.acknowledged_at is None:
        incident.acknowledged_at = datetime.utcnow()
        incident.acknowledged_by_user_id = actor.user_id
    incident.updated_at = datetime.utcnow()
    try:
        detail = json.dumps({
            "owner_user_id": incident.owner_user_id,
            "root_cause_status": incident.root_cause_status,
            "restriction_scopes": json.loads(incident.restriction_scopes or "[]"),
            "restriction_reason": incident.restriction_reason,
        }, sort_keys=True)
        _append_event(incident, actor.user_id, "triaged", old_status, detail)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return incident


def create_corrective_action(
    incident_id: int,
    actor_user_id: int,
    *,
    title: str,
    description: str,
    owner_user_id: int,
    due_at: datetime,
) -> SafetyCorrectiveAction:
    actor = _require_safety_lead(actor_user_id)
    incident = db.session.get(SafetyIncident, incident_id)
    if incident is None:
        raise LookupError(f"safety incident {incident_id} does not exist")
    if incident.status == "closed":
        raise SafetyWorkflowError("cannot add corrective actions to a closed incident")
    _guard_chain(incident)
    title = _validate_text(title, "title", 5, 240)
    description = _validate_text(description, "description", 0, _MAX_DETAILS)
    owner = _active_user(owner_user_id)
    if not ({role.name for role in owner.roles} & SAFETY_LEAD_ROLES):
        raise SafetyWorkflowError("corrective-action owner must have safety-lead authorization")
    if not isinstance(due_at, datetime):
        raise SafetyWorkflowError("due_at must be a datetime")
    if due_at <= datetime.utcnow():
        raise SafetyWorkflowError("due_at must be in the future")
    try:
        action = SafetyCorrectiveAction(
            incident_id=incident.incident_id,
            title=title,
            description=description,
            owner_user_id=owner.user_id,
            created_by_user_id=actor.user_id,
            status="open",
            due_at=due_at,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.session.add(action)
        db.session.flush()
        _append_event(
            incident, actor.user_id, "corrective_action_created", incident.status,
            json.dumps({"action_id": action.action_id, "title": title, "owner_user_id": owner.user_id}, sort_keys=True),
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return action


def update_corrective_action(
    incident_id: int,
    action_id: int,
    actor_user_id: int,
    *,
    status: str,
    evidence: str | None = None,
    effectiveness_result: str | None = None,
) -> SafetyCorrectiveAction:
    actor = _active_user(actor_user_id)
    incident = db.session.get(SafetyIncident, incident_id)
    action = db.session.get(SafetyCorrectiveAction, action_id)
    if incident is None or action is None or action.incident_id != incident_id:
        raise LookupError("safety incident or corrective action does not exist")
    if incident.status == "closed":
        raise SafetyWorkflowError("cannot update corrective actions on a closed incident")
    _guard_chain(incident)
    role_names = {role.name for role in actor.roles}
    if actor.user_id != action.owner_user_id and not role_names.intersection(SAFETY_LEAD_ROLES):
        raise SafetyWorkflowError("only the action owner or an authorized safety lead may update it")

    if status == "in_progress" and action.status == "open":
        action.status = status
    elif status == "completed" and action.status in {"open", "in_progress"}:
        action.completion_evidence = _validate_text(evidence, "completion evidence", 8, _MAX_DETAILS)
        action.completed_at = datetime.utcnow()
        action.status = "completed"
    elif status == "verified" and action.status == "completed":
        _require_safety_lead(actor.user_id)
        if actor.user_id in {action.owner_user_id, action.created_by_user_id, incident.owner_user_id}:
            raise SafetyWorkflowError("corrective action verification must be independent of the action owner and author")
        result = _validate_text(effectiveness_result, "effectiveness result", 8, _MAX_DETAILS)
        action.verified_by_user_id = actor.user_id
        action.verified_at = datetime.utcnow()
        action.effectiveness_result = result
        action.status = "verified"
    else:
        raise SafetyWorkflowError(
            f"invalid corrective-action transition from {action.status!r} to {status!r}"
        )
    action.updated_at = datetime.utcnow()
    try:
        _append_event(
            incident, actor.user_id, "corrective_action_" + status, incident.status,
            json.dumps({
                "action_id": action.action_id,
                "status": action.status,
                "verified_by_user_id": action.verified_by_user_id,
            }, sort_keys=True),
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return action


def record_independent_safety_review(
    incident_id: int,
    reviewer_user_id: int,
    rationale: str,
) -> SafetyIncident:
    reviewer = _require_safety_lead(reviewer_user_id)
    incident = db.session.get(SafetyIncident, incident_id)
    if incident is None:
        raise LookupError(f"safety incident {incident_id} does not exist")
    if incident.status == "closed":
        raise SafetyWorkflowError("closed incidents must be reopened before review")
    if reviewer.user_id in {
        incident.reporter_user_id,
        incident.owner_user_id,
    }:
        raise SafetyWorkflowError("independent reviewer must not be the reporter or investigation owner")
    rationale = _validate_text(rationale, "review rationale", 8, _MAX_RATIONALE)
    _guard_chain(incident)
    old_status = incident.status
    incident.independent_reviewer_user_id = reviewer.user_id
    incident.status = "restricted" if json.loads(incident.restriction_scopes or "[]") else "awaiting_independent_review"
    incident.updated_at = datetime.utcnow()
    try:
        _append_event(
            incident, reviewer.user_id, "independent_review_recorded", old_status,
            rationale,
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return incident


def close_safety_incident(
    incident_id: int,
    closure_user_id: int,
    *,
    rationale: str,
    root_cause_status: str,
    root_cause_notes: str,
    external_board_reference: str | None = None,
) -> SafetyIncident:
    closer = _require_safety_lead(closure_user_id)
    incident = db.session.get(SafetyIncident, incident_id)
    if incident is None:
        raise LookupError(f"safety incident {incident_id} does not exist")
    if incident.status == "closed":
        raise SafetyWorkflowError("incident is already closed")
    _guard_chain(incident)
    reviewer_id = incident.independent_reviewer_user_id
    if reviewer_id is None or reviewer_id == closer.user_id:
        raise SafetyWorkflowError("a separate independent review must be recorded before closure")
    if closer.user_id in {incident.reporter_user_id, incident.owner_user_id}:
        raise SafetyWorkflowError("reporter or investigation owner cannot close the incident")
    if root_cause_status not in {"known", "unknown"}:
        raise SafetyWorkflowError("closure requires root_cause_status known or unknown")
    root_notes = _validate_text(root_cause_notes, "root-cause rationale", 8, _MAX_DETAILS)
    closure_rationale = _validate_text(rationale, "closure rationale", 8, _MAX_RATIONALE)
    actions = SafetyCorrectiveAction.query.filter_by(incident_id=incident_id).all()
    incomplete = [action.action_id for action in actions if action.status != "verified"]
    if incomplete:
        raise SafetyWorkflowError(
            "all corrective actions must be independently verified before closure; "
            + ", ".join(map(str, incomplete))
        )
    if incident.severity in {"serious", "critical"} or incident.priority_tier in {"urgent", "critical"}:
        if not isinstance(external_board_reference, str) or len(external_board_reference.strip()) < 6:
            raise SafetyWorkflowError(
                "serious/critical closure requires an external independent-board decision reference"
            )
        incident.external_board_reference = external_board_reference.strip()[:255]
    old_status = incident.status
    incident.root_cause_status = root_cause_status
    incident.root_cause_notes = root_notes
    incident.closure_rationale = closure_rationale
    incident.closed_by_user_id = closer.user_id
    incident.closed_at = datetime.utcnow()
    incident.status = "closed"
    incident.updated_at = datetime.utcnow()
    try:
        _append_event(
            incident, closer.user_id, "incident_closed", old_status,
            json.dumps({
                "closure_rationale": closure_rationale,
                "root_cause_status": root_cause_status,
                "root_cause_notes": root_notes,
                "external_board_reference": incident.external_board_reference,
                "independent_reviewer_user_id": reviewer_id,
            }, sort_keys=True),
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return incident


def reopen_safety_incident(
    incident_id: int,
    actor_user_id: int,
    *,
    trigger: str,
    details: str,
) -> SafetyIncident:
    actor = _require_safety_lead(actor_user_id)
    incident = db.session.get(SafetyIncident, incident_id)
    if incident is None:
        raise LookupError(f"safety incident {incident_id} does not exist")
    if incident.status != "closed":
        raise SafetyWorkflowError("only a closed incident can be reopened")
    allowed_triggers = {
        "new_evidence", "recurrence", "ineffective_corrective_action",
        "changed_exposure", "credible_critical_risk", "cross_case_signal",
    }
    if trigger not in allowed_triggers:
        raise SafetyWorkflowError("unsupported incident-reopen trigger")
    details = _validate_text(details, "reopen rationale", 8, _MAX_DETAILS)
    _guard_chain(incident)
    old_status = incident.status
    if json.loads(incident.restriction_scopes or "[]") or incident.priority_tier == "critical":
        incident.status = "restricted"
    else:
        incident.status = "reopened"
    incident.closed_at = None
    incident.closed_by_user_id = None
    incident.closure_rationale = None
    incident.independent_reviewer_user_id = None
    incident.next_review_at = datetime.utcnow() + timedelta(hours=_response_hours(incident.priority_tier))
    incident.response_due_at = incident.next_review_at
    incident.updated_at = datetime.utcnow()
    try:
        _append_event(
            incident, actor.user_id, "incident_reopened", old_status,
            json.dumps({"trigger": trigger, "details": details}, sort_keys=True),
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return incident


def active_safety_restrictions(scope: str) -> list[SafetyIncident]:
    if scope not in SUPPORTED_RESTRICTION_SCOPES:
        raise SafetyWorkflowError("unsupported restriction scope")
    active = SafetyIncident.query.filter(SafetyIncident.status != "closed").all()
    result = []
    for incident in active:
        try:
            scopes = json.loads(incident.restriction_scopes or "[]")
        except (TypeError, json.JSONDecodeError):
            # Corrupt restriction state must fail closed.
            return active
        if not isinstance(scopes, list) or any(not isinstance(item, str) for item in scopes):
            return active
        if scope in scopes:
            result.append(incident)
    return result


def assert_safety_scope_allowed(scope: str):
    restrictions = active_safety_restrictions(scope)
    if restrictions:
        raise SafetyRestrictionError(scope, restrictions)


def safety_incident_to_dict(incident: SafetyIncident, *, include_events: bool = False) -> dict:
    value = {
        "incident_id": incident.incident_id,
        "incident_key": incident.incident_key,
        "category": incident.category,
        "summary": incident.summary,
        "details": incident.details,
        "severity": incident.severity,
        "likelihood": incident.likelihood,
        "evidence_strength": incident.evidence_strength,
        "exposure_count": incident.exposure_count,
        "control_failure": incident.control_failure,
        "risk_score": incident.risk_score,
        "priority_tier": incident.priority_tier,
        "status": incident.status,
        "restriction_scopes": json.loads(incident.restriction_scopes or "[]"),
        "restriction_reason": incident.restriction_reason,
        "owner_user_id": incident.owner_user_id,
        "root_cause_status": incident.root_cause_status,
        "root_cause_notes": incident.root_cause_notes,
        "reporter_user_id": incident.reporter_user_id,
        "independent_reviewer_user_id": incident.independent_reviewer_user_id,
        "closed_by_user_id": incident.closed_by_user_id,
        "closure_rationale": incident.closure_rationale,
        "external_board_reference": incident.external_board_reference,
        "reported_at": incident.reported_at.isoformat(),
        "acknowledged_at": incident.acknowledged_at.isoformat() if incident.acknowledged_at else None,
        "next_review_at": incident.next_review_at.isoformat(),
        "response_due_at": incident.response_due_at.isoformat(),
        "closed_at": incident.closed_at.isoformat() if incident.closed_at else None,
        "corrective_actions": [
            {
                "action_id": action.action_id,
                "title": action.title,
                "description": action.description,
                "owner_user_id": action.owner_user_id,
                "status": action.status,
                "due_at": action.due_at.isoformat(),
                "completed_at": action.completed_at.isoformat() if action.completed_at else None,
                "completion_evidence": action.completion_evidence,
                "verified_by_user_id": action.verified_by_user_id,
                "verified_at": action.verified_at.isoformat() if action.verified_at else None,
                "effectiveness_result": action.effectiveness_result,
            }
            for action in incident.corrective_actions
        ],
    }
    if include_events:
        value["event_chain_valid"] = verify_safety_event_chain(incident.incident_id)
        value["events"] = [
            {
                "event_id": event.event_id,
                "actor_user_id": event.actor_user_id,
                "event_type": event.event_type,
                "previous_status": event.previous_status,
                "new_status": event.new_status,
                "detail": event.detail,
                "occurred_at": event.occurred_at.isoformat(),
                "previous_hash": event.previous_hash,
                "event_hash": event.event_hash,
            }
            for event in incident.events
        ]
    return value
