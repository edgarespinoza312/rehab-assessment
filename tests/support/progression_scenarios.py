"""Deterministic, database-free synthetic progression scenarios.

These objects describe synthetic observations for software validation only.
They are deliberately independent of Flask, SQLAlchemy, and production
persistence so constructing a scenario cannot write to the configured DB.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping


@dataclass(frozen=True)
class SyntheticObservation:
    """One synthetic historical observation, never a clinical conclusion."""

    patient_id: str
    exercise_id: str
    side: str | None
    occurred_at: datetime
    source_type: str
    session_status: str | None
    completed_repetitions: int | None
    target_repetitions: int | None
    overall_score: float | None
    rom_score: float | None = None
    tempo_score: float | None = None
    stability_score: float | None = None
    compensation_score: float | None = None
    symmetry_score: float | None = None
    resistance_value: float | None = None
    resistance_unit: str | None = None
    resistance_type: str | None = None
    session_id: str | None = None
    source_id: str | None = None

    @property
    def completion_percentage(self) -> float | None:
        if self.completed_repetitions is None or not self.target_repetitions:
            return None
        return self.completed_repetitions / self.target_repetitions * 100


@dataclass(frozen=True)
class ExpectedCharacteristics:
    """Descriptive expectations used by scenario contract tests."""

    observation_count: int
    source_types: tuple[str, ...] = ()
    sides: tuple[str | None, ...] = ()
    resistance_units: tuple[str, ...] = ()
    repeated_observations: bool = False
    missing_metrics: bool = False
    cancelled_session_count: int = 0
    cancelled_sessions_with_results: int = 0
    cancelled_sessions_without_results: int = 0
    patient_ids: tuple[str, ...] = ()
    exercise_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProgressionScenario:
    """Stable synthetic scenario containing observations, not decisions."""

    id: str
    description: str
    observations: tuple[SyntheticObservation, ...]
    expected_characteristics: ExpectedCharacteristics


BASE = datetime(2026, 1, 1, 9, 0, 0)
EXERCISE = "bicep_curl"


def _workout(
    patient_id: str,
    day: int,
    *,
    side: str = "right",
    completed: int = 3,
    target: int = 3,
    score: float | None = 80,
    resistance: float | None = 5,
    unit: str | None = "lb",
    resistance_type: str | None = "dumbbell",
    exercise_id: str = EXERCISE,
    status: str = "completed",
    session_id: str | None = None,
    **metrics,
) -> SyntheticObservation:
    timestamp = BASE + timedelta(days=day)
    return SyntheticObservation(
        patient_id=patient_id,
        exercise_id=exercise_id,
        side=side,
        occurred_at=timestamp,
        source_type="workout",
        session_status=status,
        completed_repetitions=completed,
        target_repetitions=target,
        overall_score=score,
        resistance_value=resistance,
        resistance_unit=unit,
        resistance_type=resistance_type,
        session_id=session_id or f"{patient_id}-session-{day}",
        source_id=f"{patient_id}-result-{day}",
        **metrics,
    )


def _legacy(
    patient_id: str,
    day: int,
    *,
    repetitions: int = 3,
    score: float = 75,
    exercise_id: str = EXERCISE,
) -> SyntheticObservation:
    return SyntheticObservation(
        patient_id=patient_id,
        exercise_id=exercise_id,
        side=None,
        occurred_at=BASE + timedelta(days=day),
        source_type="legacy_assessment",
        session_status="completed",
        completed_repetitions=repetitions,
        target_repetitions=None,
        overall_score=score,
        source_id=f"{patient_id}-assessment-{day}",
    )


def _scenario(
    scenario_id: str,
    description: str,
    observations: tuple[SyntheticObservation, ...],
    *,
    cancelled_session_count: int = 0,
    cancelled_sessions_with_results: int = 0,
    cancelled_sessions_without_results: int = 0,
    missing_metrics: bool = False,
) -> ProgressionScenario:
    characteristics = ExpectedCharacteristics(
        observation_count=len(observations),
        source_types=tuple(sorted({item.source_type for item in observations})),
        sides=tuple(sorted(
            {item.side for item in observations},
            key=lambda side: "" if side is None else side,
        )),
        resistance_units=tuple(sorted({
            item.resistance_unit
            for item in observations
            if item.resistance_unit is not None
        })),
        repeated_observations=len(observations) > 1,
        missing_metrics=missing_metrics or any(
            item.overall_score is None
            or item.rom_score is None
            or item.tempo_score is None
            or item.stability_score is None
            or item.compensation_score is None
            or item.symmetry_score is None
            or item.resistance_value is None
            for item in observations
        ),
        cancelled_session_count=cancelled_session_count,
        cancelled_sessions_with_results=cancelled_sessions_with_results,
        cancelled_sessions_without_results=cancelled_sessions_without_results,
        patient_ids=tuple(sorted({item.patient_id for item in observations})),
        exercise_ids=tuple(sorted({item.exercise_id for item in observations})),
    )
    return ProgressionScenario(
        id=scenario_id,
        description=description,
        observations=observations,
        expected_characteristics=characteristics,
    )


SCENARIOS: Mapping[str, ProgressionScenario] = {
    "no_history": _scenario(
        "no_history",
        "A synthetic patient with no progression observations.",
        (),
    ),
    "single_observation": _scenario(
        "single_observation",
        "One complete right-sided workout observation with resistance.",
        (_workout("synthetic-patient-001", 1, score=82),),
    ),
    "consistent_performance": _scenario(
        "consistent_performance",
        "Three stable right-sided observations at the same target and resistance.",
        tuple(
            _workout("synthetic-patient-001", day, score=score)
            for day, score in ((1, 82), (2, 84), (3, 86))
        ),
    ),
    "improving_performance": _scenario(
        "improving_performance",
        "Descriptively increasing completion and score values.",
        (
            _workout("synthetic-patient-001", 1, completed=2, score=70),
            _workout("synthetic-patient-001", 2, score=78),
            _workout("synthetic-patient-001", 3, score=84),
        ),
    ),
    "declining_performance": _scenario(
        "declining_performance",
        "Descriptively decreasing completion and score values.",
        (
            _workout("synthetic-patient-001", 1, score=86),
            _workout("synthetic-patient-001", 2, score=79),
            _workout("synthetic-patient-001", 3, completed=2, score=68),
        ),
    ),
    "inconsistent_performance": _scenario(
        "inconsistent_performance",
        "Alternating strong and weak synthetic observations.",
        (
            _workout("synthetic-patient-001", 1, score=85),
            _workout("synthetic-patient-001", 2, completed=1, score=62),
            _workout("synthetic-patient-001", 3, score=84),
        ),
    ),
    "observed_resistance_increase": _scenario(
        "observed_resistance_increase",
        "Observed resistance values change from 5 lb to 7.5 lb.",
        (
            _workout("synthetic-patient-001", 1, resistance=5),
            _workout("synthetic-patient-001", 2, resistance=7.5),
            _workout("synthetic-patient-001", 3, resistance=7.5),
        ),
    ),
    "observed_resistance_decrease": _scenario(
        "observed_resistance_decrease",
        "Observed resistance values change from 7.5 lb to 5 lb.",
        (
            _workout("synthetic-patient-001", 1, resistance=7.5),
            _workout("synthetic-patient-001", 2, completed=2, resistance=5),
            _workout("synthetic-patient-001", 3, resistance=5),
        ),
    ),
    "mixed_resistance_units": _scenario(
        "mixed_resistance_units",
        "Observed resistance preserves lb and kg as separate units.",
        (
            _workout("synthetic-patient-001", 1, resistance=5, unit="lb"),
            _workout("synthetic-patient-001", 2, resistance=2.5, unit="kg"),
            _workout("synthetic-patient-001", 3, resistance=5, unit="lb"),
        ),
    ),
    "missing_resistance": _scenario(
        "missing_resistance",
        "One observation has no resistance metadata.",
        (
            _workout("synthetic-patient-001", 1, resistance=5),
            _workout("synthetic-patient-001", 2, resistance=None, unit=None,
                     resistance_type=None),
            _workout("synthetic-patient-001", 3, resistance=5),
        ),
    ),
    "left_right_independent_history": _scenario(
        "left_right_independent_history",
        "Left and right histories remain explicit and independent.",
        (
            _workout("synthetic-patient-001", 1, side="left"),
            _workout("synthetic-patient-001", 2, side="left"),
            _workout("synthetic-patient-001", 1, side="right", completed=2),
            _workout("synthetic-patient-001", 2, side="right"),
        ),
    ),
    "side_unspecified_legacy_history": _scenario(
        "side_unspecified_legacy_history",
        "Legacy assessments retain a null side.",
        (
            _legacy("synthetic-patient-001", 1),
            _legacy("synthetic-patient-001", 2, score=78),
        ),
    ),
    "mixed_legacy_workout_history": _scenario(
        "mixed_legacy_workout_history",
        "Legacy and workout observations retain distinct provenance.",
        (
            _legacy("synthetic-patient-001", 1),
            _workout("synthetic-patient-001", 2, side="right"),
        ),
    ),
    "cancelled_session_with_completed_result": _scenario(
        "cancelled_session_with_completed_result",
        "A cancelled session retains one completed exercise result.",
        (
            _workout(
                "synthetic-patient-001", 1, status="cancelled",
                session_id="synthetic-patient-001-cancelled-1",
            ),
        ),
        cancelled_session_count=1,
        cancelled_sessions_with_results=1,
    ),
    "cancelled_session_without_completed_result": _scenario(
        "cancelled_session_without_completed_result",
        "A cancelled session has no exercise-result observation.",
        (),
        cancelled_session_count=1,
        cancelled_sessions_without_results=1,
    ),
    "multiple_exercises": _scenario(
        "multiple_exercises",
        "Two stable exercise IDs remain separate.",
        (
            _workout("synthetic-patient-001", 1, exercise_id="bicep_curl"),
            _workout(
                "synthetic-patient-001", 1,
                exercise_id="shoulder_abduction",
                side="left",
            ),
        ),
    ),
    "multiple_patients": _scenario(
        "multiple_patients",
        "Two synthetic patients have otherwise similar observations.",
        (
            _workout("synthetic-patient-001", 1),
            _workout("synthetic-patient-002", 1),
        ),
    ),
    "sparse_irregular_timeline": _scenario(
        "sparse_irregular_timeline",
        "Observations use deliberately irregular synthetic intervals.",
        (
            _workout("synthetic-patient-001", 1),
            _workout("synthetic-patient-001", 10),
            _workout("synthetic-patient-001", 45),
        ),
    ),
    "missing_metric_fields": _scenario(
        "missing_metric_fields",
        "Domain metrics and resistance are intentionally absent.",
        (
            _workout(
                "synthetic-patient-001",
                1,
                score=None,
                resistance=None,
                unit=None,
                resistance_type=None,
                rom_score=None,
                tempo_score=None,
                stability_score=None,
                compensation_score=None,
                symmetry_score=None,
            ),
        ),
        missing_metrics=True,
    ),
    "conflicting_data_quality": _scenario(
        "conflicting_data_quality",
        "Mixed units, missing metrics, side-unspecified legacy data, and cancellation.",
        (
            _legacy("synthetic-patient-001", 1),
            _workout(
                "synthetic-patient-001", 2, resistance=2.5, unit="kg",
                score=None, rom_score=None,
            ),
            _workout(
                "synthetic-patient-001", 3, resistance=5, unit="lb",
                status="cancelled",
            ),
        ),
        cancelled_session_count=1,
        cancelled_sessions_with_results=1,
        missing_metrics=True,
    ),
}


def get_scenario(scenario_id: str) -> ProgressionScenario:
    """Return a stable scenario by ID."""

    return SCENARIOS[scenario_id]
