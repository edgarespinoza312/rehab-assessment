"""
right_bicep.py

Anatomy profile for the right bicep curl exercise.
"""

from dashboard.anatomy.profile import AnatomyProfile
from dashboard.anatomy.muscle_groups import MuscleGroup, Muscle


PROFILE = AnatomyProfile(

    muscles=MuscleGroup(

        primary=(

            Muscle.RIGHT_BICEPS,
            Muscle.RIGHT_BRACHIALIS,

        ),

        secondary=(

            Muscle.RIGHT_BRACHIORADIALIS,
            Muscle.RIGHT_FOREARM_FLEXORS,

        ),

    ),

    image="right_bicep_curl.png",

)