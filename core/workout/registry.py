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
    ExerciseDefinition(
        id="triceps_extension",
        display_name="Triceps Extension (Engineering Evaluation Only)",
        profiles=(
            get_profile(ExerciseType.LEFT_TRICEP_EXTENSION),
            get_profile(ExerciseType.RIGHT_TRICEP_EXTENSION),
        ),
    ),
    ExerciseDefinition(
        id="knee_extension",
        display_name="Knee Extension (Engineering Evaluation Only)",
        profiles=(
            get_profile(ExerciseType.LEFT_KNEE_EXTENSION),
            get_profile(ExerciseType.RIGHT_KNEE_EXTENSION),
        ),
    ),
    ExerciseDefinition(
        id="shoulder_abduction",
        display_name="Shoulder Abduction (Engineering Evaluation Only)",
        profiles=(
            get_profile(ExerciseType.LEFT_SHOULDER_ABDUCTION),
            get_profile(ExerciseType.RIGHT_SHOULDER_ABDUCTION),
        ),
    ),
))


def get_exercise_definition(exercise_id: str) -> ExerciseDefinition:
    return BUILTIN_EXERCISES.get(exercise_id)
