from enum import Enum


class JointType(Enum):
    """
    ESPZ Rehabilitation Skeleton v1.0

    Defines all anatomical and derived landmarks used throughout
    the rehabilitation assessment framework.
    """

    # ==========================================================
    # Head
    # ==========================================================

    NOSE = "nose"

    HEAD_CENTER = "head_center"
    CHIN = "chin"

    # ==========================================================
    # Trunk
    # ==========================================================

    NECK = "neck"

    LEFT_SHOULDER = "left_shoulder"
    RIGHT_SHOULDER = "right_shoulder"

    SHOULDER_CENTER = "shoulder_center"
    STERNUM = "sternum"
    CHEST_CENTER = "chest_center"

    LEFT_HIP = "left_hip"
    RIGHT_HIP = "right_hip"

    PELVIS_CENTER = "pelvis_center"
    BODY_CENTER = "body_center"

    # ==========================================================
    # Left Upper Limb
    # ==========================================================

    LEFT_UPPER_ARM = "left_upper_arm"
    LEFT_ELBOW = "left_elbow"
    LEFT_FOREARM = "left_forearm"
    LEFT_WRIST = "left_wrist"
    LEFT_HAND = "left_hand"

    # ==========================================================
    # Right Upper Limb
    # ==========================================================

    RIGHT_UPPER_ARM = "right_upper_arm"
    RIGHT_ELBOW = "right_elbow"
    RIGHT_FOREARM = "right_forearm"
    RIGHT_WRIST = "right_wrist"
    RIGHT_HAND = "right_hand"

    # ==========================================================
    # Left Lower Limb
    # ==========================================================

    LEFT_THIGH = "left_thigh"
    LEFT_KNEE = "left_knee"
    LEFT_SHANK = "left_shank"
    LEFT_ANKLE = "left_ankle"
    LEFT_HEEL = "left_heel"
    LEFT_TOE = "left_toe"

    # ==========================================================
    # Right Lower Limb
    # ==========================================================

    RIGHT_THIGH = "right_thigh"
    RIGHT_KNEE = "right_knee"
    RIGHT_SHANK = "right_shank"
    RIGHT_ANKLE = "right_ankle"
    RIGHT_HEEL = "right_heel"
    RIGHT_TOE = "right_toe"