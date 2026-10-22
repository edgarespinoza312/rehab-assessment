"""Persistence boundary for reusable workout plans and completed sessions."""

import hashlib
import hmac
import json
from datetime import datetime
from statistics import fmean
from typing import Iterable

from sqlalchemy import or_

from core.workout import (
    BUILTIN_EXERCISES,
    SessionSnapshot,
    SessionStatus,
    WorkoutPreset,
    WorkoutPrescription,
)
from dashboard.database import db
from dashboard.models import (
    CompletedWorkoutSession,
    ExerciseIdentity,
    Patient,
    WorkoutExerciseResult,
    WorkoutPlan,
    WorkoutPlanExercise,
    WorkoutPlanReviewEvent,
    User,
)

MAX_WORKOUT_PLAN_NAME_LENGTH = 120
MAX_WORKOUT_PLAN_DESCRIPTION_LENGTH = 10_000
MAX_WORKOUT_PLAN_EXERCISES = 50
MAX_PLAN_REVIEW_RATIONALE_LENGTH = 4000
_EMPTY_REVIEW_HASH = "0" * 64


def _ensure_exercise_identities() -> None:
    for definition in BUILTIN_EXERCISES:
        if db.session.get(ExerciseIdentity, definition.id) is None:
            db.session.add(ExerciseIdentity(exercise_id=definition.id))
    db.session.flush()


def create_workout_plan(
    name: str,
    exercises: Iterable[WorkoutPrescription],
    *,
    patient_id: int | None = None,
    description: str = "",
    created_by_user_id: int | None = None,
) -> WorkoutPlan:
    """Validate and persist an ordered workout plan using registered profiles."""
    prescriptions = tuple(exercises)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("workout plan name is required")
    normalized_name = name.strip()
    if len(normalized_name) > MAX_WORKOUT_PLAN_NAME_LENGTH:
        raise ValueError(
            f"workout plan name must be at most {MAX_WORKOUT_PLAN_NAME_LENGTH} characters"
        )
    if patient_id is not None:
        if (
            isinstance(patient_id, bool)
            or not isinstance(patient_id, int)
            or patient_id <= 0
        ):
            raise ValueError("patient_id must be a positive integer or null")
        if db.session.get(Patient, patient_id) is None:
            raise ValueError("patient does not exist")
    if not isinstance(description, str):
        raise ValueError("workout plan description must be text")
    if len(description) > MAX_WORKOUT_PLAN_DESCRIPTION_LENGTH:
        raise ValueError(
            "workout plan description must be at most "
            f"{MAX_WORKOUT_PLAN_DESCRIPTION_LENGTH} characters"
        )
    normalized_description = description.strip()
    if created_by_user_id is not None:
        if (
            isinstance(created_by_user_id, bool)
            or not isinstance(created_by_user_id, int)
            or created_by_user_id <= 0
        ):
            raise ValueError("created_by_user_id must be a positive integer or null")
        creator = db.session.get(User, created_by_user_id)
        if creator is None or creator.status != "ACTIVE":
            raise ValueError("plan creator does not exist or is disabled")
    if not prescriptions:
        raise ValueError("a workout plan must contain at least one exercise")
    if len(prescriptions) > MAX_WORKOUT_PLAN_EXERCISES:
        raise ValueError(
            f"a workout plan may contain at most {MAX_WORKOUT_PLAN_EXERCISES} exercises"
        )
    if any(not isinstance(item, WorkoutPrescription) for item in prescriptions):
        raise ValueError("workout plan exercises must be WorkoutPrescription values")

    for prescription in prescriptions:
        profile = BUILTIN_EXERCISES.get(prescription.exercise_id).profile_for_side(
            prescription.side
        )
        if profile.target_side.lower() != prescription.side:
            raise ValueError("exercise profile side does not match prescription side")

    try:
        _ensure_exercise_identities()
        plan = WorkoutPlan(
            patient_id=patient_id,
            name=normalized_name,
            description=normalized_description,
            created_by_user_id=created_by_user_id,
            exercises=[
                WorkoutPlanExercise(
                    position=position,
                    exercise_id=prescription.exercise_id,
                    side=prescription.side,
                    target_repetitions=prescription.target_repetitions,
                    resistance_value=prescription.resistance_value,
                    resistance_unit=prescription.resistance_unit,
                    resistance_type=prescription.resistance_type,
                )
                for position, prescription in enumerate(prescriptions)
            ],
        )
        db.session.add(plan)
        db.session.commit()
        return plan
    except Exception:
        db.session.rollback()
        raise


def load_workout_preset(
    plan_id: int,
    *,
    patient_id: int | None = None,
    require_approved: bool = False,
    allow_engineering_only: bool = False,
) -> WorkoutPreset:
    """Load a shared or patient-authorized plan as a domain preset."""
    plan = db.session.get(WorkoutPlan, plan_id)
    if plan is None or (
        patient_id is not None and plan.patient_id not in (None, patient_id)
    ):
        raise LookupError(f"workout plan {plan_id} does not exist")
    if require_approved:
        if plan.approval_status != "approved":
            raise ValueError("workout plan is not clinician-approved")
        if not verify_workout_plan_review_chain(plan.plan_id):
            raise ValueError("workout plan review history integrity check failed; activation blocked")
    prescriptions = tuple(
        WorkoutPrescription(
            exercise_id=item.exercise_id,
            side=item.side,
            target_repetitions=item.target_repetitions,
            resistance_value=(
                float(item.resistance_value)
                if item.resistance_value is not None
                else None
            ),
            resistance_unit=item.resistance_unit,
            resistance_type=item.resistance_type,
        )
        for item in plan.exercises
    )
    preset = WorkoutPreset(
        id=f"workout_plan_{plan.plan_id}",
        name=plan.name,
        description=plan.description,
        exercises=prescriptions,
    )
    preset.validate(BUILTIN_EXERCISES)
    if not allow_engineering_only:
        for prescription in prescriptions:
            profile = BUILTIN_EXERCISES.get(prescription.exercise_id).profile_for_side(
                prescription.side
            )
            if profile.validation_status == "engineering_only":
                raise ValueError(
                    f"{profile.display_name} is not enabled for clinical sessions"
                )
    return preset


def _review_event_hash(
    *,
    plan_id: int,
    reviewer_user_id: int,
    decision: str,
    previous_status: str,
    new_status: str,
    rationale: str,
    occurred_at: datetime,
    previous_hash: str,
) -> str:
    payload = {
        "plan_id": plan_id,
        "reviewer_user_id": reviewer_user_id,
        "decision": decision,
        "previous_status": previous_status,
        "new_status": new_status,
        "rationale": rationale,
        "occurred_at": occurred_at.isoformat(timespec="microseconds"),
        "previous_hash": previous_hash,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_workout_plan_review_chain(plan_id: int) -> bool:
    """Verify that all plan-review records link by hash and match current status."""
    plan = db.session.get(WorkoutPlan, plan_id)
    if plan is None:
        return False
    events = WorkoutPlanReviewEvent.query.filter_by(plan_id=plan_id).order_by(
        WorkoutPlanReviewEvent.event_id
    ).all()
    if not events:
        return False
    expected_previous_hash = _EMPTY_REVIEW_HASH
    for event in events:
        if event.previous_hash != expected_previous_hash:
            return False
        expected_hash = _review_event_hash(
            plan_id=event.plan_id,
            reviewer_user_id=event.reviewer_user_id,
            decision=event.decision,
            previous_status=event.previous_status,
            new_status=event.new_status,
            rationale=event.rationale,
            occurred_at=event.occurred_at,
            previous_hash=event.previous_hash,
        )
        if not hmac.compare_digest(expected_hash, event.event_hash):
            return False
        expected_previous_hash = event.event_hash
    latest = events[-1]
    if latest.new_status != plan.approval_status:
        return False
    if plan.approval_status == "approved":
        return (
            latest.decision == "approve"
            and plan.approved_by_user_id == latest.reviewer_user_id
            and plan.approved_at == latest.occurred_at
        )
    return plan.approved_by_user_id is None and plan.approved_at is None


def review_workout_plan(
    plan_id: int,
    reviewer_user_id: int,
    decision: str,
    rationale: str,
) -> tuple[WorkoutPlan, WorkoutPlanReviewEvent]:
    """Apply a role-checked plan review and append its hash-linked audit event."""
    if decision not in {"approve", "reject", "suspend"}:
        raise ValueError("decision must be approve, reject, or suspend")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ValueError("a review rationale is required")
    rationale = rationale.strip()
    if len(rationale) > MAX_PLAN_REVIEW_RATIONALE_LENGTH:
        raise ValueError(
            f"review rationale must be at most {MAX_PLAN_REVIEW_RATIONALE_LENGTH} characters"
        )
    reviewer = db.session.get(User, reviewer_user_id)
    if reviewer is None or reviewer.status != "ACTIVE":
        raise ValueError("reviewer does not exist or is disabled")
    if not any(role.name == "CLINICIAN" for role in reviewer.roles):
        raise ValueError("only an active clinician may review a workout plan")

    plan = db.session.get(WorkoutPlan, plan_id)
    if plan is None:
        raise LookupError(f"workout plan {plan_id} does not exist")
    if decision == "approve" and (
        plan.created_by_user_id is not None
        and plan.created_by_user_id == reviewer_user_id
    ):
        raise ValueError("the plan author cannot approve their own plan")

    transitions = {
        "draft": {"approve": "approved", "reject": "rejected"},
        "rejected": {},
        "approved": {"suspend": "suspended"},
        "suspended": {"approve": "approved", "reject": "rejected"},
    }
    new_status = transitions.get(plan.approval_status, {}).get(decision)
    if new_status is None:
        raise ValueError(
            f"cannot apply decision {decision!r} to plan status {plan.approval_status!r}"
        )
    existing_events = WorkoutPlanReviewEvent.query.filter_by(plan_id=plan_id).order_by(
        WorkoutPlanReviewEvent.event_id
    ).all()
    if existing_events and not verify_workout_plan_review_chain(plan_id):
        raise ValueError("plan review history integrity check failed")
    previous_hash = existing_events[-1].event_hash if existing_events else _EMPTY_REVIEW_HASH
    previous_status = plan.approval_status
    occurred_at = datetime.utcnow()
    event_hash = _review_event_hash(
        plan_id=plan_id,
        reviewer_user_id=reviewer_user_id,
        decision=decision,
        previous_status=previous_status,
        new_status=new_status,
        rationale=rationale,
        occurred_at=occurred_at,
        previous_hash=previous_hash,
    )
    event = WorkoutPlanReviewEvent(
        plan_id=plan_id,
        reviewer_user_id=reviewer_user_id,
        decision=decision,
        previous_status=previous_status,
        new_status=new_status,
        rationale=rationale,
        occurred_at=occurred_at,
        previous_hash=previous_hash,
        event_hash=event_hash,
    )
    try:
        plan.approval_status = new_status
        plan.approval_note = rationale
        if new_status == "approved":
            plan.approved_by_user_id = reviewer_user_id
            plan.approved_at = occurred_at
        else:
            plan.approved_by_user_id = None
            plan.approved_at = None
        db.session.add(event)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return plan, event


def list_workout_plans(patient_id: int) -> list[dict]:
    """Return shared and patient-owned plans visible to one patient."""
    visibility = WorkoutPlan.patient_id.is_(None)
    if patient_id is not None:
        visibility = or_(visibility, WorkoutPlan.patient_id == patient_id)
    plans = WorkoutPlan.query.filter(visibility).order_by(
        WorkoutPlan.name,
        WorkoutPlan.plan_id,
    ).all()
    return [{
        "plan_id": plan.plan_id,
        "name": plan.name,
        "description": plan.description,
        "patient_id": plan.patient_id,
        "scope": "shared" if plan.patient_id is None else "patient",
        "exercise_count": len(plan.exercises),
        "approval_status": plan.approval_status,
        "created_by_user_id": plan.created_by_user_id,
        "approved_by_user_id": plan.approved_by_user_id,
        "approved_at": plan.approved_at.isoformat() if plan.approved_at else None,
    } for plan in plans]


def _to_datetime(value) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise ValueError("workout result timestamps must be datetimes or ISO strings")


def _average_score(repetition_results, field: str) -> float | None:
    values = [
        float(result[field])
        for result in repetition_results
        if result.get(field) is not None
    ]
    return fmean(values) if values else None


def persist_workout_session(
    snapshot: SessionSnapshot,
    *,
    workout_plan_id: int | None = None,
) -> CompletedWorkoutSession:
    """Persist one finished/cancelled SessionEngine snapshot transactionally.

    Calling this more than once for the same runtime session is safe and returns
    the already-persisted record, provided it belongs to the same patient.
    """
    if not isinstance(snapshot, SessionSnapshot):
        raise TypeError("snapshot must be a SessionSnapshot")
    status = snapshot.status
    if status not in {SessionStatus.SESSION_COMPLETE, SessionStatus.CANCELLED}:
        raise ValueError("only completed or cancelled workout sessions can be persisted")
    if snapshot.patient_id is None:
        raise ValueError("a patient-linked workout session requires patient_id")
    if snapshot.started_at is None or snapshot.ended_at is None:
        raise ValueError("workout session start and completion timestamps are required")
    try:
        existing = db.session.query(CompletedWorkoutSession).filter_by(
            runtime_session_id=snapshot.session_id
        ).one_or_none()
        if existing is not None:
            if existing.patient_id != snapshot.patient_id:
                raise ValueError("runtime session is already persisted for another patient")
            return existing

        if (
            snapshot.preset_id.startswith("workout_plan_")
            and workout_plan_id is None
        ):
            raise ValueError(
                "workout_plan_id is required for plan-backed sessions"
            )

        _ensure_exercise_identities()
        plan = None
        if workout_plan_id is not None:
            plan = db.session.get(WorkoutPlan, workout_plan_id)
            if plan is None:
                raise ValueError(f"workout plan {workout_plan_id} does not exist")
            if plan.patient_id not in (None, snapshot.patient_id):
                raise ValueError("workout plan belongs to a different patient")
            if snapshot.preset_id != f"workout_plan_{plan.plan_id}":
                raise ValueError("session preset does not match the selected workout plan")
            if snapshot.total_exercises != len(plan.exercises):
                raise ValueError("session exercise count does not match the selected workout plan")

        results = [dict(result) for result in snapshot.completed_exercises]
        if plan is not None and status is SessionStatus.SESSION_COMPLETE:
            if len(results) != len(plan.exercises):
                raise ValueError(
                    "completed exercise count does not match the selected workout plan"
                )
        result_rows = []
        for position, result in enumerate(results):
            exercise_id = result.get("exercise_id")
            side = result.get("side")
            if not isinstance(exercise_id, str) or exercise_id not in BUILTIN_EXERCISES:
                raise ValueError(f"unknown exercise identity: {exercise_id}")
            BUILTIN_EXERCISES.get(exercise_id).profile_for_side(side)
            repetition_results = result.get("repetition_results") or []
            result_plan_exercise_id = None
            if plan is not None:
                if position >= len(plan.exercises):
                    raise ValueError(
                        "completed exercise count exceeds the selected workout plan"
                    )
                prescribed = plan.exercises[position]
                result_resistance = result.get("resistance_value")
                prescribed_resistance = prescribed.resistance_value
                resistance_matches = (
                    result_resistance is None and prescribed_resistance is None
                ) or (
                    result_resistance is not None
                    and prescribed_resistance is not None
                    and float(result_resistance) == float(prescribed_resistance)
                )
                if (
                    prescribed.exercise_id != exercise_id
                    or prescribed.side != side
                    or prescribed.target_repetitions != result.get("target_repetitions")
                    or not resistance_matches
                    or prescribed.resistance_unit != result.get("resistance_unit")
                    or prescribed.resistance_type != result.get("resistance_type")
                ):
                    raise ValueError(
                        "completed exercise order does not match the selected workout plan"
                    )
                result_plan_exercise_id = prescribed.plan_exercise_id

            feedback = [
                message
                for repetition in repetition_results
                for message in repetition.get("feedback", [])
            ]
            result_rows.append(WorkoutExerciseResult(
                workout_plan_exercise_id=result_plan_exercise_id,
                position=position,
                exercise_id=exercise_id,
                display_name=result["exercise"],
                side=side,
                target_repetitions=result["target_repetitions"],
                completed_repetitions=result["completed_repetitions"],
                status=result["status"],
                resistance_value=result.get("resistance_value"),
                resistance_unit=result.get("resistance_unit"),
                resistance_type=result.get("resistance_type"),
                average_score=result.get("average_score")
                    if result.get("average_score") is not None
                    else _average_score(repetition_results, "overall_score"),
                best_score=result.get("best_score"),
                worst_score=result.get("worst_score"),
                rom_score=_average_score(repetition_results, "rom_score"),
                tempo_score=_average_score(repetition_results, "tempo_score"),
                completion_score=_average_score(repetition_results, "completion_score"),
                stability_score=_average_score(repetition_results, "stability_score"),
                compensation_score=_average_score(repetition_results, "compensation_score"),
                symmetry_score=_average_score(repetition_results, "symmetry_score"),
                feedback=json.dumps(feedback),
                started_at=_to_datetime(result.get("started_at")) or snapshot.started_at,
                completed_at=_to_datetime(result.get("completed_at")),
            ))

        session = CompletedWorkoutSession(
            runtime_session_id=snapshot.session_id,
            patient_id=snapshot.patient_id,
            workout_plan_id=workout_plan_id,
            preset_id=snapshot.preset_id,
            workout_name=snapshot.preset_name,
            status=(
                "completed"
                if status is SessionStatus.SESSION_COMPLETE
                else "cancelled"
            ),
            started_at=snapshot.started_at,
            completed_at=snapshot.ended_at,
            exercise_results=result_rows,
        )
        db.session.add(session)
        db.session.commit()
        return session
    except Exception:
        db.session.rollback()
        raise
