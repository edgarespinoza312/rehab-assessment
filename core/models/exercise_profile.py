"""
exercise_profile.py

Defines the expected characteristics of a rehabilitation assessment.

An ExerciseProfile describes both the exercise itself and the
expected movement targets used by the Assessment Engine to evaluate
performance.

The profile contains no assessment logic. Instead, it provides the
reference values against which movement measurements are compared.
"""

from dataclasses import dataclass, field
from typing import Optional
from core.models.exercise_type import ExerciseType
@dataclass
class ExerciseProfile:
    """
    Describes a rehabilitation assessment protocol.
    """

    # ----------------------------------------------------------
    # Basic Information
    # ----------------------------------------------------------

    exercise: ExerciseType

    display_name: str

    category: str

    description: str

    # ----------------------------------------------------------
    # Exercise Characteristics
    # ----------------------------------------------------------

    primary_joint: Optional[str] = None

    movement_plane: Optional[str] = None

    target_side: Optional[str] = None

    # NEW:
    # Joints whose live angles should appear on the dashboard.
    tracked_joints: list[str] = field(default_factory=list)

    # ----------------------------------------------------------
    # Assessment Targets
    # ----------------------------------------------------------

    # Desired range of motion (degrees)
    target_rom: float = 0.0

    # Expected joint angle at full extension (degrees)
    target_extension: float = 0.0

    # Expected joint angle at full flexion (degrees)
    target_flexion: float = 0.0

    # Ideal duration for one repetition (seconds)
    ideal_rep_time: float = 0.0

    # Acceptable repetition duration range (seconds)
    minimum_rep_time: float = 0.0

    maximum_rep_time: float = 0.0