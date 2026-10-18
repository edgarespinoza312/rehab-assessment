"""Logical exercise definitions backed by the existing ExerciseProfiles."""

from dataclasses import dataclass

from core.models import ExerciseProfile


def normalize_side(side: str) -> str:
    if not isinstance(side, str) or side.strip().lower() not in {"left", "right"}:
        raise ValueError("side must be 'left' or 'right'")
    return side.strip().lower()


@dataclass(frozen=True)
class ExerciseDefinition:
    """An exercise concept with side-specific existing pipeline profiles."""

    id: str
    display_name: str
    profiles: tuple[ExerciseProfile, ...]

    def __post_init__(self):
        if not self.id or not self.id.strip():
            raise ValueError("exercise definition id is required")
        if not self.display_name or not self.display_name.strip():
            raise ValueError("exercise definition display_name is required")
        profiles = tuple(self.profiles)
        if not profiles:
            raise ValueError("an exercise definition requires at least one profile")
        sides = [normalize_side(profile.target_side) for profile in profiles]
        if len(sides) != len(set(sides)):
            raise ValueError("exercise definition profiles must have unique sides")
        object.__setattr__(self, "profiles", profiles)

    @property
    def supported_sides(self) -> tuple[str, ...]:
        return tuple(normalize_side(profile.target_side) for profile in self.profiles)

    def profile_for_side(self, side: str) -> ExerciseProfile:
        normalized = normalize_side(side)
        for profile in self.profiles:
            if normalize_side(profile.target_side) == normalized:
                return profile
        raise ValueError(f"{self.display_name} does not support the {normalized} side")


class ExerciseDefinitionRegistry:
    """Read-only lookup for the exercise definitions available to presets."""

    def __init__(self, definitions):
        definitions = tuple(definitions)
        by_id = {definition.id: definition for definition in definitions}
        if len(by_id) != len(definitions):
            raise ValueError("exercise definition ids must be unique")
        self._definitions = by_id

    def get(self, exercise_id: str) -> ExerciseDefinition:
        try:
            return self._definitions[exercise_id]
        except KeyError as error:
            raise ValueError(f"unknown exercise definition: {exercise_id}") from error

    def __contains__(self, exercise_id: str) -> bool:
        return exercise_id in self._definitions

    def __iter__(self):
        return iter(self._definitions.values())
