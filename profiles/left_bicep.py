"""
left_bicep.py

Anatomy profile for the left bicep curl exercise.
"""

from dashboard.anatomy.profile import AnatomyProfile
from dashboard.anatomy.muscle_groups import MuscleGroup, Muscle


PROFILE = AnatomyProfile(

    muscles=MuscleGroup(

        primary=(

            Muscle.LEFT_BICEPS,
            Muscle.LEFT_BRACHIALIS,

        ),

        secondary=(

            Muscle.LEFT_BRACHIORADIALIS,
            Muscle.LEFT_FOREARM_FLEXORS,

        ),

    ),

    image="left_bicep_curl.png",

)