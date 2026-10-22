"""Registry of movement patterns with an implemented measurement pipeline."""
from core.exercise_catalog import get_exercise_profile
from core.models import ExerciseType


_IMPLEMENTED_EXERCISES = (
    ExerciseType.LEFT_BICEP_CURL,
    ExerciseType.RIGHT_BICEP_CURL,
    ExerciseType.LEFT_TRICEP_EXTENSION,
    ExerciseType.RIGHT_TRICEP_EXTENSION,
    ExerciseType.LEFT_SHOULDER_ABDUCTION,
    ExerciseType.RIGHT_SHOULDER_ABDUCTION,
)


def get_profiles():
    """Return all exercise profiles whose measurement path is implemented."""
    return [get_exercise_profile(exercise) for exercise in _IMPLEMENTED_EXERCISES]


def get_profile(exercise: ExerciseType):
    """Return one implemented profile; reject enum values without an engine."""
    if exercise not in _IMPLEMENTED_EXERCISES:
        raise ValueError(f"{exercise.name} has not been implemented.")
    return get_exercise_profile(exercise)
