"""Append-only human review service for advisory progression evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from dashboard.database import db
from dashboard.models import ProgressionReviewEvent
from dashboard.services.advisory_progression import (
    ProgressionDecision,
    evaluate_progression,
    from_progression_result,
)
from dashboard.services.progression import get_patient_progression


VALID_DISPOSITIONS = frozenset({"REVIEWED", "ACKNOWLEDGED", "DISMISSED"})
MAX_REVIEWER_REFERENCE_LENGTH = 120
MAX_NOTE_LENGTH = 2000


def advisory_fingerprint(decision: ProgressionDecision) -> str:
    """Return a stable identity for the exact selected advisory evidence."""

    payload = {
        "patient_id": decision.patient_id,
        "exercise_id": decision.exercise_id,
        "side": decision.side,
        "evidence": [
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
                "overall_score": record.overall_score,
                "resistance_value": record.resistance_value,
                "resistance_unit": record.resistance_unit,
                "resistance_type": record.resistance_type,
            }
            for record in decision.evidence_records
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def get_advisory_decision(
    patient_id: int,
    *,
    exercise_id: str,
    side: str | None = None,
) -> ProgressionDecision:
    """Compute the authoritative current advisory from canonical evidence."""

    results = get_patient_progression(
        patient_id,
        exercise_id=exercise_id,
        side=side,
    )
    return evaluate_progression(
        tuple(from_progression_result(result) for result in results),
        patient_id=patient_id,
        exercise_id=exercise_id,
        side=side,
    )


def normalize_reviewer_reference(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("reviewer_reference must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("reviewer_reference is required")
    if len(normalized) > MAX_REVIEWER_REFERENCE_LENGTH:
        raise ValueError(
            f"reviewer_reference must be at most "
            f"{MAX_REVIEWER_REFERENCE_LENGTH} characters"
        )
    return normalized


def normalize_note(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("note must be a string or null")
    normalized = value.strip()
    if len(normalized) > MAX_NOTE_LENGTH:
        raise ValueError(
            f"note must be at most {MAX_NOTE_LENGTH} characters"
        )
    return normalized or None


def list_review_events(
    patient_id: int,
    *,
    exercise_id: str,
    side: str | None = None,
    fingerprint: str | None = None,
) -> list[ProgressionReviewEvent]:
    query = ProgressionReviewEvent.query.filter_by(
        patient_id=patient_id,
        exercise_id=exercise_id,
    )
    if side is None:
        query = query.filter(ProgressionReviewEvent.side.is_(None))
    else:
        query = query.filter_by(side=side)
    if fingerprint is not None:
        query = query.filter_by(advisory_fingerprint=fingerprint)
    return query.order_by(
        ProgressionReviewEvent.reviewed_at,
        ProgressionReviewEvent.review_event_id,
    ).all()


def create_review_event(
    decision: ProgressionDecision,
    *,
    reviewer_reference: str,
    disposition: str,
    note: str | None = None,
    reviewed_at: datetime | None = None,
) -> ProgressionReviewEvent:
    if disposition not in VALID_DISPOSITIONS:
        raise ValueError("invalid disposition")
    if not decision.evidence_records:
        raise ValueError("cannot review an advisory with no evidence")

    event = ProgressionReviewEvent(
        patient_id=decision.patient_id,
        exercise_id=decision.exercise_id,
        side=decision.side,
        advisory_fingerprint=advisory_fingerprint(decision),
        disposition=disposition,
        reviewer_reference=normalize_reviewer_reference(reviewer_reference),
        note=normalize_note(note),
        reviewed_at=reviewed_at or datetime.utcnow(),
    )
    db.session.add(event)
    db.session.commit()
    return event
