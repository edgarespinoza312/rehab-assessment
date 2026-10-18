"""Initial workout definitions assembled from the existing exercise registry."""

from core.exercise_registry import get_profile
from core.models import ExerciseType

from .definitions import ExerciseDefinition, ExerciseDefinitionRegistry


BUILTIN_EXERCISES = ExerciseDefinitionRegistry((
    ExerciseDefinition(
        id="bicep_curl",
        display_name="Bicep Curl",
        profiles=(
            get_profile(ExerciseType.LEFT_BICEP_CURL),
            get_profile(ExerciseType.RIGHT_BICEP_CURL),
        ),
    ),
))


def get_exercise_definition(exercise_id: str) -> ExerciseDefinition:
    return BUILTIN_EXERCISES.get(exercise_id)
