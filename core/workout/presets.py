"""Small in-memory preset catalog used by the initial workout runtime."""

from types import MappingProxyType

from .models import WorkoutPreset, WorkoutPrescription


STARTER_BICEP_CURL_PRESET = WorkoutPreset(
    id="bilateral_bicep_curl_2",
    name="Bilateral Bicep Curl Starter",
    description="Two right-arm curls followed by two left-arm curls.",
    exercises=(
        WorkoutPrescription("bicep_curl", "right", 2),
        WorkoutPrescription("bicep_curl", "left", 2),
    ),
)

BUILTIN_PRESETS = MappingProxyType({
    STARTER_BICEP_CURL_PRESET.id: STARTER_BICEP_CURL_PRESET,
})


def get_workout_preset(preset_id: str) -> WorkoutPreset:
    try:
        return BUILTIN_PRESETS[preset_id]
    except KeyError as error:
        raise ValueError(f"unknown workout preset: {preset_id}") from error
