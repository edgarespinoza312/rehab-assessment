"""Persistence boundary for reusable workout plans and completed sessions."""

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
    WorkoutExerciseResult,
    WorkoutPlan,
    WorkoutPlanExercise,
)


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
) -> WorkoutPlan:
    """Validate and persist an ordered workout plan using registered profiles."""
    prescriptions = tuple(exercises)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("workout plan name is required")
    if not isinstance(description, str):
        raise ValueError("workout plan description must be text")
    if not prescriptions:
        raise ValueError("a workout plan must contain at least one exercise")
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
            name=name.strip(),
            description=description.strip() if isinstance(description, str) else "",
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
) -> WorkoutPreset:
    """Load a shared or patient-authorized plan as a domain preset."""
    plan = db.session.get(WorkoutPlan, plan_id)
    if plan is None or (
        patient_id is not None and plan.patient_id not in (None, patient_id)
    ):
        raise LookupError(f"workout plan {plan_id} does not exist")
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
    return preset


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

        _ensure_exercise_identities()
        plan = None
        if workout_plan_id is not None:
            plan = db.session.get(WorkoutPlan, workout_plan_id)
            if plan is None:
                raise ValueError(f"workout plan {workout_plan_id} does not exist")
            if plan.patient_id not in (None, snapshot.patient_id):
                raise ValueError("workout plan belongs to a different patient")

        results = [dict(result) for result in snapshot.completed_exercises]
        result_rows = []
        for position, result in enumerate(results):
            exercise_id = result.get("exercise_id")
            side = result.get("side")
            if not isinstance(exercise_id, str) or exercise_id not in BUILTIN_EXERCISES:
                raise ValueError(f"unknown exercise identity: {exercise_id}")
            BUILTIN_EXERCISES.get(exercise_id).profile_for_side(side)
            repetition_results = result.get("repetition_results") or []
            result_plan_exercise_id = None
            if plan is not None and position < len(plan.exercises):
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
