"""
exercise_registry.py

Registry of rehabilitation exercises currently implemented
by the assessment system.
"""

from core.exercise_catalog import get_exercise_profile
from core.models import ExerciseType


# Only include exercises that actually have profiles
_IMPLEMENTED_EXERCISES = [

    ExerciseType.LEFT_BICEP_CURL,
    ExerciseType.RIGHT_BICEP_CURL,

    # Add more here as you implement them
    # ExerciseType.LEFT_SHOULDER_FLEXION,
    # ExerciseType.RIGHT_SHOULDER_FLEXION,
]


def get_profiles():
    """
    Returns all implemented ExerciseProfiles.
    """

    return [
        get_exercise_profile(exercise)
        for exercise in _IMPLEMENTED_EXERCISES
    ]


def get_profile(exercise: ExerciseType):
    """
    Returns the ExerciseProfile for a single exercise.
    """

    if exercise not in _IMPLEMENTED_EXERCISES:
        raise ValueError(
            f"{exercise.name} has not been implemented."
        )

    return get_exercise_profile(exercise)