"""
anatomy_regions.py

Defines the mapping between NeuroMotion muscle identifiers
and regions inside the anatomy SVG.

This module is intentionally free of rendering logic.
Its only responsibility is to provide a stable lookup
between the application's muscle model and graphical assets.
"""

from dashboard.anatomy.muscle_groups import Muscle


# ==========================================================
# SVG Region Mapping
# ==========================================================

SVG_REGION_IDS = {

    # Right Arm

    Muscle.RIGHT_BICEPS:
        "right_biceps",

    Muscle.RIGHT_BRACHIALIS:
        "right_brachialis",

    Muscle.RIGHT_BRACHIORADIALIS:
        "right_brachioradialis",

    Muscle.RIGHT_FOREARM_FLEXORS:
        "right_forearm_flexors",


    # Left Arm

    Muscle.LEFT_BICEPS:
        "left_biceps",

    Muscle.LEFT_BRACHIALIS:
        "left_brachialis",

    Muscle.LEFT_BRACHIORADIALIS:
        "left_brachioradialis",

    Muscle.LEFT_FOREARM_FLEXORS:
        "left_forearm_flexors",

}


# ==========================================================
# Lookup
# ==========================================================

def svg_region(muscle: Muscle) -> str:
    """
    Returns the SVG region identifier associated
    with a muscle.

    Raises
    ------
    KeyError
        If no SVG region has been defined.
    """

    return SVG_REGION_IDS[muscle]