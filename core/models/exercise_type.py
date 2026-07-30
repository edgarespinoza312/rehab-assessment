from enum import Enum, auto


class ExerciseType(Enum):

    # ==========================================================
    # Elbow
    # ==========================================================

    LEFT_BICEP_CURL = auto()
    RIGHT_BICEP_CURL = auto()

    LEFT_TRICEP_EXTENSION = auto()
    RIGHT_TRICEP_EXTENSION = auto()

    # ==========================================================
    # Shoulder
    # ==========================================================

    LEFT_SHOULDER_FLEXION = auto()
    RIGHT_SHOULDER_FLEXION = auto()

    LEFT_SHOULDER_ABDUCTION = auto()
    RIGHT_SHOULDER_ABDUCTION = auto()

    LEFT_SHOULDER_EXTERNAL_ROTATION = auto()
    RIGHT_SHOULDER_EXTERNAL_ROTATION = auto()

    LEFT_SHOULDER_INTERNAL_ROTATION = auto()
    RIGHT_SHOULDER_INTERNAL_ROTATION = auto()

    # ==========================================================
    # Functional Reach
    # ==========================================================

    FORWARD_REACH = auto()
    LATERAL_REACH = auto()
    OVERHEAD_REACH = auto()

    # ==========================================================
    # Functional Coordination
    # ==========================================================

    HAND_TO_MOUTH = auto()
    HAND_TO_HEAD = auto()
    CROSS_BODY_REACH = auto()

    # ==========================================================
    # Bilateral
    # ==========================================================

    BILATERAL_ARM_RAISE = auto()
    BILATERAL_FORWARD_REACH = auto()