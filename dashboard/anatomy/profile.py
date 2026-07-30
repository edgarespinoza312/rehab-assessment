"""
profile.py

Defines the anatomy profile model used throughout the
NeuroMotion anatomy subsystem.
"""

from dataclasses import dataclass

from dashboard.anatomy.muscle_groups import MuscleGroup


@dataclass(frozen=True)
class AnatomyProfile:
    """
    Complete anatomical description of a rehabilitation exercise.
    """

    muscles: MuscleGroup

    image: str