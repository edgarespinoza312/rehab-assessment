"""
exercise_catalog.py

Registers every rehabilitation assessment supported by the
ESPZ Rehabilitation Assessment System.

Each ExerciseType maps to a corresponding ExerciseProfile.

The Assessment Engine, Exercise Engine, and UI use this registry
to retrieve the active exercise profile.
"""

from core.models import (
    ExerciseProfile,
    ExerciseType,
)

EXERCISE_CATALOG = {

    # ==========================================================
    # Elbow
    # ==========================================================

    ExerciseType.LEFT_BICEP_CURL: ExerciseProfile(
        exercise=ExerciseType.LEFT_BICEP_CURL,
        display_name="Left Bicep Curl",
        category="Elbow",
        description="Repeated elbow flexion of the left arm.",

        primary_joint="Elbow",
        movement_plane="Sagittal",
        target_side="Left",

        # NEW
        tracked_joints=[
            "Left Elbow",
        ],

        # ------------------------------------------------------
        # Assessment Targets
        # ------------------------------------------------------

        # Approximately 175° → 35° elbow motion
        target_rom=140.0,

        # Fully extended elbow
        target_extension=175.0,

        # Fully flexed elbow
        target_flexion=35.0,

        # One smooth repetition
        ideal_rep_time=2.0,

        # Acceptable timing window
        minimum_rep_time=1.0,
        maximum_rep_time=4.0,
    ),

    ExerciseType.RIGHT_BICEP_CURL: ExerciseProfile(
        exercise=ExerciseType.RIGHT_BICEP_CURL,
        display_name="Right Bicep Curl",
        category="Elbow",
        description="Repeated elbow flexion of the right arm.",

        primary_joint="Elbow",
        movement_plane="Sagittal",
        target_side="Right",

        # NEW
        tracked_joints=[
            "Right Elbow",
        ],

        # ------------------------------------------------------
        # Assessment Targets
        # ------------------------------------------------------

        target_rom=140.0,
        target_extension=175.0,
        target_flexion=35.0,

        ideal_rep_time=2.0,
        minimum_rep_time=1.0,
        maximum_rep_time=4.0,
    ),

}


def get_exercise_profile(exercise: ExerciseType) -> ExerciseProfile:
    """
    Returns the ExerciseProfile associated with an ExerciseType.

    Parameters
    ----------
    exercise : ExerciseType
        The rehabilitation assessment to retrieve.

    Returns
    -------
    ExerciseProfile
        The corresponding exercise profile.
    """
    return EXERCISE_CATALOG[exercise]