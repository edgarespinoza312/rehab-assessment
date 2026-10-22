"""Controlled corrections as reviewed overlays; original assessment rows stay immutable."""
from __future__ import annotations

from datetime import datetime
import hashlib
import hmac
import json
import math

from dashboard.database import db
from dashboard.models import (
    AssessmentCorrection,
    AssessmentCorrectionEvent,
    AssessmentRecord,
    User,
)


EMPTY_CHAIN_HASH = "0" * 64
CORRECTABLE_FIELDS = {
    "exercise", "repetitions", "average_score", "best_score", "worst_score",
    "trend", "feedback",
}
MAX_REASON_LENGTH = 4000
MAX_FEEDBACK_LENGTH = 30000


class CorrectionWorkflowError(ValueError):
    """A correction request or decision failed governance validation."""


def _active_clinician(user_id: int) -> User:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
        raise CorrectionWorkflowError("a valid clinician identity is required")
    user = db.session.get(User, user_id)
    if user is None or user.status != "ACTIVE":
        raise CorrectionWorkflowError("clinician does not exist or is disabled")
    if not any(role.name == "CLINICIAN" for role in user.roles):
        raise CorrectionWorkflowError("an active clinician role is required")
    return user


def _json_safe(value):
    """Canonicalize broken legacy values without turning them into valid scores."""
    if isinstance(value, float) and not math.isfinite(value):
        return {"__non_finite_float__": repr(value)}
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _canonical_json(value) -> str:
    return json.dumps(
        _json_safe(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _snapshot(record: AssessmentRecord) -> dict:
    return {
        "assessment_id": record.assessment_id,
        "patient_id": record.patient_id,
        "exercise": record.exercise,
        "repetitions": record.repetitions,
        "average_score": record.average_score,
        "best_score": record.best_score,
        "worst_score": record.worst_score,
        "trend": record.trend,
        "feedback": record.feedback,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def assessment_snapshot_hash(record: AssessmentRecord) -> str:
    return hashlib.sha256(_canonical_json(_snapshot(record)).encode("utf-8")).hexdigest()


def _validate_proposed_value(field_name: str, value):
    if not isinstance(field_name, str) or field_name not in CORRECTABLE_FIELDS:
        raise CorrectionWorkflowError(
            "field_name must identify a supported measurement/report field"
        )
    if field_name in {"exercise", "trend"}:
        limit = 100 if field_name == "exercise" else 50
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
            raise CorrectionWorkflowError(
                f"{field_name} must be non-empty text of at most {limit} characters"
            )
        return value.strip()
    if field_name == "repetitions":
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10000:
            raise CorrectionWorkflowError("repetitions must be an integer from 0 through 10000")
        return value
    if field_name in {"average_score", "best_score", "worst_score"}:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or not 0 <= float(value) <= 100
        ):
            raise CorrectionWorkflowError(f"{field_name} must be a finite score from 0 through 100")
        return float(value)
    if field_name == "feedback":
        if not isinstance(value, (str, list, dict)):
            raise CorrectionWorkflowError("feedback must be text, a list, or an object")
        if len(_canonical_json(value)) > MAX_FEEDBACK_LENGTH:
            raise CorrectionWorkflowError("feedback exceeds the maximum permitted size")
        return value
    raise CorrectionWorkflowError("unsupported correction field")


def _event_hash(
    correction_id: int,
    actor_user_id: int,
    event_type: str,
    previous_status: str,
    new_status: str,
    detail: str,
    occurred_at: datetime,
    previous_hash: str,
) -> str:
    payload = {
        "correction_id": correction_id,
        "actor_user_id": actor_user_id,
        "event_type": event_type,
        "previous_status": previous_status,
        "new_status": new_status,
        "detail": detail,
        "occurred_at": occurred_at.isoformat(timespec="microseconds"),
        "previous_hash": previous_hash,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def verify_correction_event_chain(correction_id: int) -> bool:
    correction = db.session.get(AssessmentCorrection, correction_id)
    if correction is None:
        return False
    events = AssessmentCorrectionEvent.query.filter_by(
        correction_id=correction_id
    ).order_by(AssessmentCorrectionEvent.event_id).all()
    if not events:
        return False
    previous = EMPTY_CHAIN_HASH
    for event in events:
        if event.previous_hash != previous:
            return False
        expected = _event_hash(
            event.correction_id, event.actor_user_id, event.event_type,
            event.previous_status, event.new_status, event.detail,
            event.occurred_at, event.previous_hash,
        )
        if not hmac.compare_digest(expected, event.event_hash):
            return False
        previous = event.event_hash
    return events[-1].new_status == correction.status


def _append_event(
    correction: AssessmentCorrection,
    actor_user_id: int,
    event_type: str,
    previous_status: str,
    detail: str,
) -> AssessmentCorrectionEvent:
    prior = AssessmentCorrectionEvent.query.filter_by(
        correction_id=correction.correction_id
    ).order_by(AssessmentCorrectionEvent.event_id.desc()).first()
    previous_hash = prior.event_hash if prior else EMPTY_CHAIN_HASH
    now = datetime.utcnow()
    event = AssessmentCorrectionEvent(
        correction_id=correction.correction_id,
        actor_user_id=actor_user_id,
        event_type=event_type,
        previous_status=previous_status,
        new_status=correction.status,
        detail=detail,
        occurred_at=now,
        previous_hash=previous_hash,
        event_hash=_event_hash(
            correction.correction_id, actor_user_id, event_type,
            previous_status, correction.status, detail, now, previous_hash,
        ),
    )
    db.session.add(event)
    return event


def request_assessment_correction(
    assessment_id: int,
    requester_user_id: int,
    *,
    field_name: str,
    proposed_value,
    reason: str,
    evidence_reference: str | None = None,
) -> AssessmentCorrection:
    requester = _active_clinician(requester_user_id)
    record = db.session.get(AssessmentRecord, assessment_id)
    if record is None:
        raise LookupError(f"assessment {assessment_id} does not exist")
    value = _validate_proposed_value(field_name, proposed_value)
    if not isinstance(reason, str) or not 8 <= len(reason.strip()) <= MAX_REASON_LENGTH:
        raise CorrectionWorkflowError("reason must be 8 to 4000 characters")
    if evidence_reference is not None and (
        not isinstance(evidence_reference, str) or len(evidence_reference.strip()) > 500
    ):
        raise CorrectionWorkflowError("evidence_reference must be text of at most 500 characters")

    original_value = getattr(record, field_name)
    if original_value == value:
        raise CorrectionWorkflowError("proposed value is identical to the recorded value")
    existing = AssessmentCorrection.query.filter(
        AssessmentCorrection.assessment_id == assessment_id,
        AssessmentCorrection.field_name == field_name,
        AssessmentCorrection.status.in_(("pending", "accepted")),
    ).first()
    if existing is not None:
        raise CorrectionWorkflowError(
            "a pending or accepted correction already exists for this field; "
            "review or reconcile it before creating another"
        )
    correction = AssessmentCorrection(
        assessment_id=record.assessment_id,
        patient_id=record.patient_id,
        field_name=field_name,
        original_value_json=_canonical_json(original_value),
        proposed_value_json=_canonical_json(value),
        source_snapshot_hash=assessment_snapshot_hash(record),
        reason=reason.strip(),
        evidence_reference=evidence_reference.strip() if evidence_reference else None,
        status="pending",
        requested_by_user_id=requester.user_id,
        requested_at=datetime.utcnow(),
    )
    try:
        db.session.add(correction)
        db.session.flush()
        _append_event(
            correction,
            requester.user_id,
            "requested",
            "pending",
            _canonical_json({
                "field_name": field_name,
                "reason": reason.strip(),
                "evidence_reference": evidence_reference.strip() if evidence_reference else None,
                "source_snapshot_hash": correction.source_snapshot_hash,
            }),
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return correction


def review_assessment_correction(
    correction_id: int,
    reviewer_user_id: int,
    *,
    decision: str,
    rationale: str,
) -> AssessmentCorrection:
    reviewer = _active_clinician(reviewer_user_id)
    if not isinstance(decision, str) or decision not in {"accept", "reject"}:
        raise CorrectionWorkflowError("decision must be accept or reject")
    if not isinstance(rationale, str) or not 8 <= len(rationale.strip()) <= MAX_REASON_LENGTH:
        raise CorrectionWorkflowError("review rationale must be 8 to 4000 characters")
    correction = db.session.get(AssessmentCorrection, correction_id)
    if correction is None:
        raise LookupError(f"correction {correction_id} does not exist")
    if correction.status != "pending":
        raise CorrectionWorkflowError("only pending corrections can be reviewed")
    if reviewer.user_id == correction.requested_by_user_id:
        raise CorrectionWorkflowError("the correction requester cannot approve their own correction")
    if not verify_correction_event_chain(correction_id):
        raise CorrectionWorkflowError("correction event chain failed integrity verification")
    record = db.session.get(AssessmentRecord, correction.assessment_id)
    if record is None:
        raise LookupError(f"source assessment {correction.assessment_id} does not exist")
    try:
        if not hmac.compare_digest(
            correction.source_snapshot_hash,
            assessment_snapshot_hash(record),
        ):
            old_status = correction.status
            correction.status = "stale"
            correction.reviewed_by_user_id = reviewer.user_id
            correction.reviewed_at = datetime.utcnow()
            correction.review_rationale = (
                "Source assessment changed after the correction request. "
                + rationale.strip()
            )
            _append_event(
                correction,
                reviewer.user_id,
                "stale_source_rejected",
                old_status,
                _canonical_json({
                    "expected_snapshot_hash": correction.source_snapshot_hash,
                    "actual_snapshot_hash": assessment_snapshot_hash(record),
                    "rationale": rationale.strip(),
                }),
            )
            db.session.commit()
            return correction

        old_status = correction.status
        correction.status = "accepted" if decision == "accept" else "rejected"
        correction.reviewed_by_user_id = reviewer.user_id
        correction.reviewed_at = datetime.utcnow()
        correction.review_rationale = rationale.strip()
        _append_event(
            correction,
            reviewer.user_id,
            "accepted" if decision == "accept" else "rejected",
            old_status,
            _canonical_json({
                "decision": decision,
                "rationale": rationale.strip(),
                "source_snapshot_hash": correction.source_snapshot_hash,
            }),
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return correction


def effective_assessment_values(assessment_id: int) -> dict:
    """Return report-facing overlay values while leaving the source row unchanged."""
    record = db.session.get(AssessmentRecord, assessment_id)
    if record is None:
        raise LookupError(f"assessment {assessment_id} does not exist")
    values = _snapshot(record)
    values["effective_corrections"] = []
    values["stale_correction_ids"] = []
    corrections = AssessmentCorrection.query.filter_by(
        assessment_id=assessment_id,
        status="accepted",
    ).order_by(AssessmentCorrection.reviewed_at, AssessmentCorrection.correction_id).all()
    digest = assessment_snapshot_hash(record)
    for correction in corrections:
        if not hmac.compare_digest(correction.source_snapshot_hash, digest):
            values["stale_correction_ids"].append(correction.correction_id)
            continue
        if not verify_correction_event_chain(correction.correction_id):
            values["stale_correction_ids"].append(correction.correction_id)
            continue
        try:
            values[correction.field_name] = json.loads(correction.proposed_value_json)
        except (TypeError, json.JSONDecodeError):
            values["stale_correction_ids"].append(correction.correction_id)
            continue
        values["effective_corrections"].append({
            "correction_id": correction.correction_id,
            "field_name": correction.field_name,
            "reviewed_by_user_id": correction.reviewed_by_user_id,
            "reviewed_at": correction.reviewed_at.isoformat() if correction.reviewed_at else None,
            "reason": correction.reason,
            "evidence_reference": correction.evidence_reference,
        })
    values["source_snapshot_hash"] = digest
    return values


def correction_to_dict(correction: AssessmentCorrection, *, include_events: bool = False) -> dict:
    value = {
        "correction_id": correction.correction_id,
        "assessment_id": correction.assessment_id,
        "patient_id": correction.patient_id,
        "field_name": correction.field_name,
        "original_value": json.loads(correction.original_value_json),
        "proposed_value": json.loads(correction.proposed_value_json),
        "source_snapshot_hash": correction.source_snapshot_hash,
        "reason": correction.reason,
        "evidence_reference": correction.evidence_reference,
        "status": correction.status,
        "requested_by_user_id": correction.requested_by_user_id,
        "reviewed_by_user_id": correction.reviewed_by_user_id,
        "review_rationale": correction.review_rationale,
        "requested_at": correction.requested_at.isoformat(),
        "reviewed_at": correction.reviewed_at.isoformat() if correction.reviewed_at else None,
    }
    if include_events:
        events = AssessmentCorrectionEvent.query.filter_by(
            correction_id=correction.correction_id
        ).order_by(AssessmentCorrectionEvent.event_id).all()
        value["event_chain_valid"] = verify_correction_event_chain(correction.correction_id)
        value["events"] = [{
            "event_id": event.event_id,
            "actor_user_id": event.actor_user_id,
            "event_type": event.event_type,
            "previous_status": event.previous_status,
            "new_status": event.new_status,
            "occurred_at": event.occurred_at.isoformat(),
            "detail": event.detail,
            "event_hash": event.event_hash,
        } for event in events]
    return value
