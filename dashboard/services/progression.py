"""Read-only longitudinal progression projections and context."""

from dataclasses import dataclass
from datetime import date, datetime, time
from core.workout.registry import BUILTIN_EXERCISES
from dashboard.database import db
MAX_RECENT_PROGRESSION_LIMIT = 100


from dashboard.models import (
    AssessmentRecord,
    CompletedWorkoutSession,
    WorkoutExerciseResult,
)


@dataclass(frozen=True)
class ProgressionResult:
    """One exercise result projected into the longitudinal history contract."""

    patient_id: int
    occurred_at: datetime
    exercise_id: str | None
    exercise_display_name: str
    side: str | None
    source_type: str
    session_status: str
    target_repetitions: int | None
    completed_repetitions: int | None
    completion_percentage: float | None
    overall_score: float | None
    rom_score: float | None
    tempo_score: float | None
    completion_score: float | None
    stability_score: float | None
    compensation_score: float | None
    symmetry_score: float | None
    resistance_value: float | None
    resistance_unit: str | None
    resistance_type: str | None = None
    exercise_position: int | None = None
    source_id: int = 0


@dataclass(frozen=True)
class ResistanceObservation:
    """One historical resistance observation without unit normalization."""

    occurred_at: datetime
    value: float | None
    unit: str | None
    resistance_type: str | None


@dataclass(frozen=True)
class ProgressionContext:
    """Recent read-only context for one exercise and explicit side."""

    patient_id: int
    exercise_id: str | None
    exercise_display_name: str
    side: str | None
    latest_observation_at: datetime
    previous_completed_repetitions: int | None
    previous_target_repetitions: int | None
    previous_completion_percentage: float | None
    previous_overall_score: float | None
    previous_resistance_value: float | None
    previous_resistance_unit: str | None
    previous_resistance_type: str | None
    source_type: str
    session_status: str
    recent_record_count: int
    earliest_observation_at: datetime
    recent_observation_dates: tuple[datetime, ...]
    recent_overall_scores: tuple[float | None, ...]
    recent_completion_percentages: tuple[float | None, ...]
    recent_resistance_observations: tuple[ResistanceObservation, ...]


def _as_datetime(value: datetime | date | None, *, end: bool = False) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.combine(value, time.max if end else time.min)


def _completion_percentage(
    completed: int | None,
    target: int | None,
) -> float | None:
    if target is None or completed is None or target <= 0:
        return None
    return completed / target * 100


def _legacy_exercise_id(display_name: str) -> str | None:
    for definition in BUILTIN_EXERCISES:
        if any(
            profile.display_name == display_name
            for profile in definition.profiles
        ):
            return definition.id
    return None


def _legacy_matches(
    record: AssessmentRecord,
    *,
    exercise_id: str | None,
    side: str | None,
) -> bool:
    mapped_id = _legacy_exercise_id(record.exercise)
    if exercise_id is not None and mapped_id != exercise_id:
        return False
    # AssessmentRecord has no explicit side. Do not infer one from its label.
    return side is None


def _workout_results(
    patient_id: int,
    *,
    exercise_id: str | None,
    side: str | None,
    start: datetime | None,
    end: datetime | None,
) -> list[ProgressionResult]:
    query = (
        db.session.query(CompletedWorkoutSession, WorkoutExerciseResult)
        .join(
            WorkoutExerciseResult,
            WorkoutExerciseResult.workout_session_id
            == CompletedWorkoutSession.workout_session_id,
        )
        .filter(CompletedWorkoutSession.patient_id == patient_id)
    )
    if exercise_id is not None:
        query = query.filter(WorkoutExerciseResult.exercise_id == exercise_id)
    if side is not None:
        query = query.filter(WorkoutExerciseResult.side == side)
    if start is not None:
        query = query.filter(CompletedWorkoutSession.started_at >= start)
    if end is not None:
        query = query.filter(CompletedWorkoutSession.started_at <= end)

    rows = query.order_by(
        CompletedWorkoutSession.started_at,
        WorkoutExerciseResult.position,
        WorkoutExerciseResult.workout_exercise_result_id,
    ).all()
    return [
        ProgressionResult(
            patient_id=session.patient_id,
            occurred_at=session.started_at,
            exercise_id=result.exercise_id,
            exercise_display_name=result.display_name,
            side=result.side,
            source_type="workout",
            session_status=session.status,
            target_repetitions=result.target_repetitions,
            completed_repetitions=result.completed_repetitions,
            completion_percentage=_completion_percentage(
                result.completed_repetitions,
                result.target_repetitions,
            ),
            overall_score=result.average_score,
            rom_score=result.rom_score,
            tempo_score=result.tempo_score,
            completion_score=result.completion_score,
            stability_score=result.stability_score,
            compensation_score=result.compensation_score,
            symmetry_score=result.symmetry_score,
            resistance_value=(
                float(result.resistance_value)
                if result.resistance_value is not None
                else None
            ),
            resistance_unit=result.resistance_unit,
            resistance_type=result.resistance_type,
            exercise_position=result.position,
            source_id=result.workout_exercise_result_id,
        )
        for session, result in rows
    ]


def _legacy_results(
    patient_id: int,
    *,
    exercise_id: str | None,
    side: str | None,
    start: datetime | None,
    end: datetime | None,
) -> list[ProgressionResult]:
    query = AssessmentRecord.query.filter(AssessmentRecord.patient_id == patient_id)
    if start is not None:
        query = query.filter(AssessmentRecord.created_at >= start)
    if end is not None:
        query = query.filter(AssessmentRecord.created_at <= end)

    records = query.order_by(
        AssessmentRecord.created_at,
        AssessmentRecord.assessment_id,
    ).all()
    results = []
    for record in records:
        if not _legacy_matches(record, exercise_id=exercise_id, side=side):
            continue
        results.append(ProgressionResult(
            patient_id=record.patient_id,
            occurred_at=record.created_at,
            exercise_id=_legacy_exercise_id(record.exercise),
            exercise_display_name=record.exercise,
            side=None,
            source_type="legacy_assessment",
            session_status="completed",
            target_repetitions=None,
            completed_repetitions=record.repetitions,
            completion_percentage=None,
            overall_score=record.average_score,
            rom_score=None,
            tempo_score=None,
            completion_score=None,
            stability_score=None,
            compensation_score=None,
            symmetry_score=None,
            resistance_value=None,
            resistance_unit=None,
            resistance_type=None,
            exercise_position=None,
            source_id=record.assessment_id,
        ))
    return results


def get_patient_progression(
    patient_id: int,
    *,
    exercise_id: str | None = None,
    side: str | None = None,
    start: datetime | date | None = None,
    end: datetime | date | None = None,
) -> list[ProgressionResult]:
    """Return deterministic longitudinal results for one patient.

    Workout results include completed exercises from both completed and
    cancelled sessions. Legacy records are included only for fields they
    actually store; their side and resistance remain unknown.
    """
    if isinstance(patient_id, bool) or not isinstance(patient_id, int):
        raise ValueError("patient_id must be an integer")
    if side is not None and side not in {"left", "right"}:
        raise ValueError("side must be 'left', 'right', or None")

    start_at = _as_datetime(start)
    end_at = _as_datetime(end, end=True)
    if start_at is not None and end_at is not None and start_at > end_at:
        raise ValueError("start must not be after end")

    results = _workout_results(
        patient_id,
        exercise_id=exercise_id,
        side=side,
        start=start_at,
        end=end_at,
    )
    results.extend(_legacy_results(
        patient_id,
        exercise_id=exercise_id,
        side=side,
        start=start_at,
        end=end_at,
    ))
    return sorted(
        results,
        key=lambda result: (
            result.occurred_at,
            result.exercise_position if result.exercise_position is not None else -1,
            result.source_id,
        ),
    )


def get_patient_progression_context(
    patient_id: int,
    *,
    exercise_id: str | None = None,
    side: str | None = None,
    recent_limit: int = 5,
) -> list[ProgressionContext]:
    """Return bounded, read-only recent context grouped by exercise and side.

    The underlying records and their ordering come directly from
    ``get_patient_progression``. No recommendations, normalization, or
    prescription decisions are made here.
    """
    if isinstance(recent_limit, bool) or not isinstance(recent_limit, int):
        raise ValueError("recent_limit must be an integer")
    if recent_limit <= 0:
        raise ValueError("recent_limit must be positive")
    if recent_limit > MAX_RECENT_PROGRESSION_LIMIT:
        raise ValueError(
            f"recent_limit must not exceed {MAX_RECENT_PROGRESSION_LIMIT}"
        )

    records = get_patient_progression(
        patient_id,
        exercise_id=exercise_id,
        side=side,
    )
    grouped: dict[tuple[str | None, str | None, str], list[ProgressionResult]] = {}
    for record in records:
        key = (
            record.exercise_id,
            record.side,
            record.exercise_display_name,
        )
        grouped.setdefault(key, []).append(record)

    contexts = []
    for (record_exercise_id, record_side, display_name), history in grouped.items():
        recent = history[-recent_limit:]
        latest = recent[-1]
        contexts.append(ProgressionContext(
            patient_id=latest.patient_id,
            exercise_id=record_exercise_id,
            exercise_display_name=display_name,
            side=record_side,
            latest_observation_at=latest.occurred_at,
            previous_completed_repetitions=latest.completed_repetitions,
            previous_target_repetitions=latest.target_repetitions,
            previous_completion_percentage=latest.completion_percentage,
            previous_overall_score=latest.overall_score,
            previous_resistance_value=latest.resistance_value,
            previous_resistance_unit=latest.resistance_unit,
            previous_resistance_type=latest.resistance_type,
            source_type=latest.source_type,
            session_status=latest.session_status,
            recent_record_count=len(history),
            earliest_observation_at=history[0].occurred_at,
            recent_observation_dates=tuple(
                item.occurred_at for item in recent
            ),
            recent_overall_scores=tuple(
                item.overall_score for item in recent
            ),
            recent_completion_percentages=tuple(
                item.completion_percentage for item in recent
            ),
            recent_resistance_observations=tuple(
                ResistanceObservation(
                    occurred_at=item.occurred_at,
                    value=item.resistance_value,
                    unit=item.resistance_unit,
                    resistance_type=item.resistance_type,
                )
                for item in recent
            ),
        ))

    return sorted(
        contexts,
        key=lambda context: (
            context.latest_observation_at,
            context.exercise_id or "",
            context.side or "",
            context.exercise_display_name,
        ),
    )
