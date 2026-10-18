"""Workout prescription and session orchestration domain."""

from .definitions import ExerciseDefinition, ExerciseDefinitionRegistry
from .engine import InvalidSessionTransition, SessionEngine
from .models import (
    ExerciseCompletionStatus,
    ExerciseResult,
    SessionSnapshot,
    SessionStatus,
    WorkoutPreset,
    WorkoutPrescription,
    WorkoutSession,
)
from .registry import BUILTIN_EXERCISES, get_exercise_definition
from .presets import BUILTIN_PRESETS, STARTER_BICEP_CURL_PRESET, get_workout_preset

__all__ = [
    "BUILTIN_EXERCISES",
    "BUILTIN_PRESETS",
    "ExerciseCompletionStatus",
    "ExerciseDefinition",
    "ExerciseDefinitionRegistry",
    "ExerciseResult",
    "InvalidSessionTransition",
    "SessionEngine",
    "SessionSnapshot",
    "SessionStatus",
    "STARTER_BICEP_CURL_PRESET",
    "WorkoutPreset",
    "WorkoutPrescription",
    "WorkoutSession",
    "get_exercise_definition",
    "get_workout_preset",
]
