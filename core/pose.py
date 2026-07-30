"""
pose.py

Implements the Pose Layer of the rehabilitation assessment system.

Responsibilities
----------------
- Initialize MediaPipe Pose.
- Detect anatomical landmarks from a camera frame.
- Build the ESPZ Rehabilitation Skeleton.
- Draw pose landmarks on a copy of the frame.

This module intentionally performs no biomechanics,
exercise recognition, repetition counting, or assessment.
"""

import cv2
import mediapipe as mp

from core.models import Joint
from core.models import JointType
from core.models import Skeleton


LANDMARK_MAP = {
    # =========================
    # Head
    # =========================
    0: JointType.NOSE,

    # =========================
    # Upper Body
    # =========================
    11: JointType.LEFT_SHOULDER,
    12: JointType.RIGHT_SHOULDER,

    13: JointType.LEFT_ELBOW,
    14: JointType.RIGHT_ELBOW,

    15: JointType.LEFT_WRIST,
    16: JointType.RIGHT_WRIST,

    # =========================
    # Lower Body
    # =========================
    23: JointType.LEFT_HIP,
    24: JointType.RIGHT_HIP,

    25: JointType.LEFT_KNEE,
    26: JointType.RIGHT_KNEE,

    27: JointType.LEFT_ANKLE,
    28: JointType.RIGHT_ANKLE,

    29: JointType.LEFT_HEEL,
    30: JointType.RIGHT_HEEL,

    31: JointType.LEFT_TOE,
    32: JointType.RIGHT_TOE,
}


class PoseEngine:
    """
    Runs MediaPipe Pose on incoming camera frames.
    """

    def _build_skeleton(self, results):
        """
        Builds the ESPZ Rehabilitation Skeleton from MediaPipe landmarks.
        """

        skeleton = Skeleton()

        if not results.pose_landmarks:
            return skeleton

        # Build primary landmarks
        for index, landmark in enumerate(results.pose_landmarks.landmark):

            # Ignore MediaPipe landmarks we don't use
            if index not in LANDMARK_MAP:
                continue

            joint_type = LANDMARK_MAP[index]

            joint = Joint(
                name=joint_type,
                x=landmark.x,
                y=landmark.y,
                z=landmark.z,
                visibility=landmark.visibility,
            )

            skeleton.add_joint(joint)

        # Generate derived landmarks
        self._add_derived_landmarks(skeleton)

        return skeleton

    def _create_midpoint(
        self,
        skeleton: Skeleton,
        joint_a: JointType,
        joint_b: JointType,
        new_joint: JointType,
    ):
        """
        Creates a new joint at the midpoint between two existing joints.
        """

        first = skeleton.get_joint(joint_a)
        second = skeleton.get_joint(joint_b)

        if first is None or second is None:
            return

        midpoint = Joint(
            name=new_joint,
            x=(first.x + second.x) / 2,
            y=(first.y + second.y) / 2,
            z=(first.z + second.z) / 2,
            visibility=min(first.visibility, second.visibility),
        )

        skeleton.add_joint(midpoint)

    def _create_copy(
        self,
        skeleton: Skeleton,
        source_joint: JointType,
        new_joint: JointType,
    ):
        """
        Creates a new joint by copying an existing joint.
        """

        source = skeleton.get_joint(source_joint)

        if source is None:
            return

        copied_joint = Joint(
            name=new_joint,
            x=source.x,
            y=source.y,
            z=source.z,
            visibility=source.visibility,
            confidence=source.confidence,
        )

        skeleton.add_joint(copied_joint)

    def _add_trunk_landmarks(self, skeleton: Skeleton):
        """
        Generates derived trunk and head landmarks.
        """

        # Shoulder center
        self._create_midpoint(
            skeleton,
            JointType.LEFT_SHOULDER,
            JointType.RIGHT_SHOULDER,
            JointType.SHOULDER_CENTER,
        )

        # Pelvis center
        self._create_midpoint(
            skeleton,
            JointType.LEFT_HIP,
            JointType.RIGHT_HIP,
            JointType.PELVIS_CENTER,
        )

        # Body center
        self._create_midpoint(
            skeleton,
            JointType.SHOULDER_CENTER,
            JointType.PELVIS_CENTER,
            JointType.BODY_CENTER,
        )

        # Chest center
        self._create_midpoint(
            skeleton,
            JointType.SHOULDER_CENTER,
            JointType.BODY_CENTER,
            JointType.CHEST_CENTER,
        )

        # Neck
        self._create_midpoint(
            skeleton,
            JointType.NOSE,
            JointType.SHOULDER_CENTER,
            JointType.NECK,
        )

        # Head center
        self._create_midpoint(
            skeleton,
            JointType.NOSE,
            JointType.NECK,
            JointType.HEAD_CENTER,
        )

        # Placeholder sternum
        self._create_copy(
            skeleton,
            JointType.CHEST_CENTER,
            JointType.STERNUM,
        )

        # Placeholder chin
        self._create_copy(
            skeleton,
            JointType.HEAD_CENTER,
            JointType.CHIN,
        )

    def _add_arm_landmarks(self, skeleton: Skeleton):
        """
        Generates derived upper-limb landmarks.
        """

        # Left upper arm
        self._create_midpoint(
            skeleton,
            JointType.LEFT_SHOULDER,
            JointType.LEFT_ELBOW,
            JointType.LEFT_UPPER_ARM,
        )

        # Left forearm
        self._create_midpoint(
            skeleton,
            JointType.LEFT_ELBOW,
            JointType.LEFT_WRIST,
            JointType.LEFT_FOREARM,
        )

        # Left hand
        self._create_copy(
            skeleton,
            JointType.LEFT_WRIST,
            JointType.LEFT_HAND,
        )

        # Right upper arm
        self._create_midpoint(
            skeleton,
            JointType.RIGHT_SHOULDER,
            JointType.RIGHT_ELBOW,
            JointType.RIGHT_UPPER_ARM,
        )

        # Right forearm
        self._create_midpoint(
            skeleton,
            JointType.RIGHT_ELBOW,
            JointType.RIGHT_WRIST,
            JointType.RIGHT_FOREARM,
        )

        # Right hand
        self._create_copy(
            skeleton,
            JointType.RIGHT_WRIST,
            JointType.RIGHT_HAND,
        )

    def _add_leg_landmarks(self, skeleton: Skeleton):
        """
        Generates derived lower-limb landmarks.
        """

        # Left thigh
        self._create_midpoint(
            skeleton,
            JointType.LEFT_HIP,
            JointType.LEFT_KNEE,
            JointType.LEFT_THIGH,
        )

        # Left shank
        self._create_midpoint(
            skeleton,
            JointType.LEFT_KNEE,
            JointType.LEFT_ANKLE,
            JointType.LEFT_SHANK,
        )

        # Right thigh
        self._create_midpoint(
            skeleton,
            JointType.RIGHT_HIP,
            JointType.RIGHT_KNEE,
            JointType.RIGHT_THIGH,
        )

        # Right shank
        self._create_midpoint(
            skeleton,
            JointType.RIGHT_KNEE,
            JointType.RIGHT_ANKLE,
            JointType.RIGHT_SHANK,
        )

    def _add_derived_landmarks(self, skeleton: Skeleton):
        """
        Generates all derived landmarks for the ESPZ Skeleton.

        For now, only SHOULDER_CENTER is created as a proof of concept.
        """

        self._add_trunk_landmarks(skeleton)
        self._add_arm_landmarks(skeleton)
        self._add_leg_landmarks(skeleton)

        self._create_midpoint(
            skeleton,
            JointType.LEFT_SHOULDER,
            JointType.RIGHT_SHOULDER,
            JointType.SHOULDER_CENTER,
        )

    def __init__(self):
        """
        Initializes the MediaPipe Pose model.
        """

        self.mp_pose = mp.solutions.pose
        self.mp_drawing = mp.solutions.drawing_utils

        self.pose = self.mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )

    def process(self, frame):
        """
        Processes a single camera frame.

        Returns
        -------
        annotated_frame
            Frame with pose landmarks drawn.

        skeleton
        """

        # Convert BGR → RGB
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Run pose estimation
        results = self.pose.process(rgb_frame)

        # Build skeleton
        skeleton = self._build_skeleton(results)

        
    

        # Copy frame for visualization
        annotated_frame = frame.copy()

        # Draw MediaPipe landmarks
        if results.pose_landmarks:
            self.mp_drawing.draw_landmarks(
                annotated_frame,
                results.pose_landmarks,
                self.mp_pose.POSE_CONNECTIONS,
            )

        return annotated_frame, skeleton

    def close(self):
        """
        Releases MediaPipe resources.
        """

        self.pose.close()