"""
registry.py

Maps rehabilitation exercises to anatomy profiles.
"""

from core.models.exercise_type import ExerciseType

from profiles.right_bicep import PROFILE as RIGHT_BICEP
from profiles.left_bicep import PROFILE as LEFT_BICEP


ANATOMY_PROFILES = {

    ExerciseType.RIGHT_BICEP_CURL: RIGHT_BICEP,
    ExerciseType.LEFT_BICEP_CURL: LEFT_BICEP,

}


def anatomy_profile_for(
    exercise: ExerciseType,
):
    return ANATOMY_PROFILES[exercise]