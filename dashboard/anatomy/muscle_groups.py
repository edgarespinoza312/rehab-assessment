"""
muscle_groups.py

Defines the core anatomical data models used by the
NeuroMotion anatomy subsystem.

Responsibilities
----------------
- Defines anatomical muscle identifiers.
- Defines the MuscleGroup data model.

This module contains no exercise mappings,
rendering logic, or UI behavior.
"""

from dataclasses import dataclass
from enum import Enum


# ==========================================================
# Muscle Definitions
# ==========================================================

class Muscle(Enum):
    """
    Enumerates all anatomical muscle regions recognized
    by the NeuroMotion anatomy subsystem.

    These identifiers serve as the canonical muscle
    vocabulary shared by anatomy profiles, renderers,
    and visualization components.
    """

    # ------------------------------------------------------
    # Upper Arm
    # ------------------------------------------------------

    LEFT_BICEPS = "left_biceps"
    RIGHT_BICEPS = "right_biceps"

    LEFT_BRACHIALIS = "left_brachialis"
    RIGHT_BRACHIALIS = "right_brachialis"

    LEFT_TRICEPS = "left_triceps"
    RIGHT_TRICEPS = "right_triceps"

    LEFT_DELTOID = "left_deltoid"
    RIGHT_DELTOID = "right_deltoid"

    # ------------------------------------------------------
    # Forearm
    # ------------------------------------------------------

    LEFT_BRACHIORADIALIS = "left_brachioradialis"
    RIGHT_BRACHIORADIALIS = "right_brachioradialis"

    LEFT_FOREARM_FLEXORS = "left_forearm_flexors"
    RIGHT_FOREARM_FLEXORS = "right_forearm_flexors"

    LEFT_FOREARM_EXTENSORS = "left_forearm_extensors"
    RIGHT_FOREARM_EXTENSORS = "right_forearm_extensors"


# ==========================================================
# Muscle Group
# ==========================================================

@dataclass(frozen=True)
class MuscleGroup:
    """
    Represents the muscles involved in a rehabilitation
    exercise.

    Attributes
    ----------
    primary:
        The primary muscles responsible for producing the
        movement.

    secondary:
        Supporting muscles that stabilize or assist the
        primary movers.
    """

    primary: tuple[Muscle, ...]
    secondary: tuple[Muscle, ...]