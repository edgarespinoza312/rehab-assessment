"""In-memory workout prescription, runtime, and result models."""

from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
import math
from types import MappingProxyType
from typing import Mapping
from uuid import uuid4

from core.models import AssessmentResult

from .definitions import ExerciseDefinitionRegistry, normalize_side


def _freeze_snapshot_value(value):
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze_snapshot_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_snapshot_value(item) for item in value)
    return value


def _thaw_snapshot_value(value):
    if isinstance(value, Mapping):
        return {key: _thaw_snapshot_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_snapshot_value(item) for item in value]
    return value


class SessionStatus(str, Enum):
    NOT_STARTED = "session_not_started"
    CALIBRATING = "calibrating"
    READY = "ready"
    EXERCISING = "exercising"
    EXERCISE_COMPLETE = "exercise_complete"
    TRANSITIONING = "transitioning"
    SESSION_COMPLETE = "session_complete"
    CANCELLED = "cancelled"


class ExerciseCompletionStatus(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"


@dataclass(frozen=True)
class WorkoutPrescription:
    """What a patient is prescribed to do for one exercise."""

    exercise_id: str
    side: str
    target_repetitions: int
    resistance_value: float | None = None
    resistance_unit: str | None = None
    resistance_type: str | None = None

    def __post_init__(self):
        if not isinstance(self.exercise_id, str) or not self.exercise_id.strip():
            raise ValueError("exercise_id is required")
        object.__setattr__(self, "exercise_id", self.exercise_id.strip())
        object.__setattr__(self, "side", normalize_side(self.side))
        if isinstance(self.target_repetitions, bool) or not isinstance(self.target_repetitions, int):
            raise ValueError("target_repetitions must be a positive integer")
        if self.target_repetitions <= 0:
            raise ValueError("target_repetitions must be a positive integer")
        if self.resistance_value is None:
            if self.resistance_unit is not None:
                raise ValueError("resistance_unit requires resistance_value")
            if self.resistance_type is not None:
                raise ValueError("resistance_type requires resistance_value")
            return
        if (
            isinstance(self.resistance_value, bool)
            or not isinstance(self.resistance_value, (int, float))
            or not math.isfinite(self.resistance_value)
            or self.resistance_value < 0
        ):
            raise ValueError("resistance_value must be a non-negative number")
        if not isinstance(self.resistance_unit, str) or not self.resistance_unit.strip():
            raise ValueError("resistance_unit is required when resistance is set")
        object.__setattr__(self, "resistance_value", float(self.resistance_value))
        object.__setattr__(self, "resistance_unit", self.resistance_unit.strip())
        if self.resistance_type is not None:
            if not isinstance(self.resistance_type, str) or not self.resistance_type.strip():
                raise ValueError("resistance_type must be non-empty when provided")
            object.__setattr__(self, "resistance_type", self.resistance_type.strip())


@dataclass(frozen=True)
class WorkoutPreset:
    id: str
    name: str
    exercises: tuple[WorkoutPrescription, ...]
    description: str = ""

    def __post_init__(self):
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValueError("preset id is required")
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("preset name is required")
        exercises = tuple(self.exercises)
        if not exercises:
            raise ValueError("a workout preset must contain at least one exercise")
        if any(not isinstance(item, WorkoutPrescription) for item in exercises):
            raise ValueError("preset exercises must be WorkoutPrescription values")
        object.__setattr__(self, "id", self.id.strip())
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "description", self.description.strip())
        object.__setattr__(self, "exercises", exercises)

    def validate(self, registry: ExerciseDefinitionRegistry) -> None:
        for prescription in self.exercises:
            registry.get(prescription.exercise_id).profile_for_side(prescription.side)


@dataclass(frozen=True)
class ExerciseResult:
    """Results from one prescribed exercise, using existing repetition scores."""

    exercise_id: str
    display_name: str
    side: str
    target_repetitions: int
    repetition_results: tuple[AssessmentResult, ...]
    status: ExerciseCompletionStatus
    started_at: datetime
    completed_at: datetime | None
    resistance_value: float | None = None
    resistance_unit: str | None = None
    resistance_type: str | None = None

    def __post_init__(self):
        object.__setattr__(self, "side", normalize_side(self.side))
        if self.target_repetitions <= 0:
            raise ValueError("target_repetitions must be positive")
        copied = tuple(replace(result, feedback=list(result.feedback)) for result in self.repetition_results)
        if len(copied) > self.target_repetitions:
            raise ValueError("completed repetitions cannot exceed the target")
        if self.status is ExerciseCompletionStatus.COMPLETE and len(copied) != self.target_repetitions:
            raise ValueError("a complete exercise result must meet its repetition target")
        object.__setattr__(self, "repetition_results", copied)

    @property
    def completed_repetitions(self) -> int:
        return len(self.repetition_results)

    @property
    def average_score(self) -> float | None:
        if not self.repetition_results:
            return None
        return sum(result.overall_score for result in self.repetition_results) / len(self.repetition_results)

    @property
    def best_score(self) -> float | None:
        return max((result.overall_score for result in self.repetition_results), default=None)

    @property
    def worst_score(self) -> float | None:
        return min((result.overall_score for result in self.repetition_results), default=None)

    def to_dict(self) -> dict:
        repetition_results = []
        for result in self.repetition_results:
            repetition_results.append({
                "overall_score": result.overall_score,
                "rom_score": result.rom_score,
                "tempo_score": result.tempo_score,
                "completion_score": result.completion_score,
                "stability_score": result.stability_score,
                "compensation_score": result.compensation_score,
                "symmetry_score": result.symmetry_score,
                "feedback": list(result.feedback),
            })
        return {
            "exercise_id": self.exercise_id,
            "exercise": self.display_name,
            "side": self.side,
            "target_repetitions": self.target_repetitions,
            "resistance_value": self.resistance_value,
            "resistance_unit": self.resistance_unit,
            "resistance_type": self.resistance_type,
            "completed_repetitions": self.completed_repetitions,
            "status": self.status.value,
            "average_score": self.average_score,
            "best_score": self.best_score,
            "worst_score": self.worst_score,
            "repetition_scores": [result.overall_score for result in self.repetition_results],
            "repetition_results": repetition_results,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class WorkoutSession:
    """Mutable in-memory execution state for one workout preset."""

    preset: WorkoutPreset
    patient_id: int | None
    session_id: str = field(default_factory=lambda: str(uuid4()))
    status: SessionStatus = SessionStatus.NOT_STARTED
    current_exercise_index: int = 0
    completed_exercises: list[ExerciseResult] = field(default_factory=list)
    current_repetition_results: list[AssessmentResult] = field(default_factory=list)
    started_at: datetime | None = None
    current_exercise_started_at: datetime | None = None
    ended_at: datetime | None = None


@dataclass(frozen=True)
class SessionSnapshot:
    """Immutable scalar view of current workflow state for future consumers."""

    session_id: str
    patient_id: int | None
    preset_id: str
    preset_name: str
    status: SessionStatus
    current_exercise_index: int
    total_exercises: int
    current_exercise_id: str | None
    current_exercise_name: str | None
    current_side: str | None
    target_repetitions: int
    completed_repetitions: int
    completed_exercises: tuple[Mapping[str, object], ...]
    started_at: datetime | None
    ended_at: datetime | None
    resistance_value: float | None = None
    resistance_unit: str | None = None
    resistance_type: str | None = None

    def __post_init__(self):
        object.__setattr__(
            self,
            "completed_exercises",
            tuple(_freeze_snapshot_value(dict(result)) for result in self.completed_exercises),
        )

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "patient_id": self.patient_id,
            "preset_id": self.preset_id,
            "preset_name": self.preset_name,
            "status": self.status.value,
            "current_exercise_index": self.current_exercise_index,
            "total_exercises": self.total_exercises,
            "current_side": self.current_side,
            "target_repetitions": self.target_repetitions,
            "completed_repetitions": self.completed_repetitions,
            "current_exercise": ({
                "exercise_id": self.current_exercise_id,
                "name": self.current_exercise_name,
                "side": self.current_side,
                "target_repetitions": self.target_repetitions,
                "completed_repetitions": self.completed_repetitions,
                "resistance_value": self.resistance_value,
                "resistance_unit": self.resistance_unit,
                "resistance_type": self.resistance_type,
            } if self.current_exercise_id is not None else None),
            "completed_exercises": [
                _thaw_snapshot_value(result) for result in self.completed_exercises
            ],
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
        }
