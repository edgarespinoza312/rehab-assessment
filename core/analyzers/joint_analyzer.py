"""
joint_analyzer.py

Computes joint kinematics from the tracked skeleton.

Responsibilities
----------------
- Joint angle calculation
- Peak flexion tracking
- Peak extension tracking
- Range of motion tracking

This analyzer performs measurements only.
It does not assess movement quality.
"""

import math

from core.models import (
    Joint,
    JointType,
    Skeleton,
    MovementMetrics,
)


class JointAnalyzer:
    """
    Computes joint kinematics.
    """

    MIN_VISIBILITY = 0.6

    def __init__(self):
        """
        Stores joint state across frames.
        """

        self._peak_extension = None
        self._peak_flexion = None

    # ==========================================================
    # Public API
    # ==========================================================

    def analyze(
        self,
        skeleton: Skeleton,
        metrics: MovementMetrics,
    ):
        """
        Computes all joint-related biomechanics.
        """

        self._calculate_upper_limb_metrics(
            skeleton,
            metrics,
        )

        self._calculate_lower_limb_metrics(
            skeleton,
            metrics,
        )

    def reset(self):
        """
        Clears stored measurements between repetitions.
        """

        self._peak_extension = None
        self._peak_flexion = None

    # ==========================================================
    # Upper Limb Metrics
    # ==========================================================

    def _calculate_upper_limb_metrics(
        self,
        skeleton: Skeleton,
        metrics: MovementMetrics,
    ):
        """
        Calculates upper-limb biomechanics.
        """

    # ------------------------------------------------------
    # Left Elbow
    # ------------------------------------------------------

        metrics.elbow_angle_left = self._calculate_angle_from_types(
        skeleton,
        JointType.LEFT_SHOULDER,
        JointType.LEFT_ELBOW,
        JointType.LEFT_WRIST,
    )

    # ------------------------------------------------------
    # Right Elbow
    # ------------------------------------------------------

        metrics.elbow_angle_right = self._calculate_angle_from_types(
        skeleton,
        JointType.RIGHT_SHOULDER,
        JointType.RIGHT_ELBOW,
        JointType.RIGHT_WRIST,
    )

    # ------------------------------------------------------
    # Select Active Measurement
    # ------------------------------------------------------

        if metrics.elbow_angle_left is not None:

            active_angle = metrics.elbow_angle_left

        elif metrics.elbow_angle_right is not None:

            active_angle = metrics.elbow_angle_right

        else:

            return

    # ------------------------------------------------------
    # Peak Tracking
    # ------------------------------------------------------

        if (
            self._peak_extension is None
            or active_angle > self._peak_extension
        ):
            self._peak_extension = active_angle

        if (
            self._peak_flexion is None
            or active_angle < self._peak_flexion
        ):
            self._peak_flexion = active_angle

        metrics.peak_extension = self._peak_extension
        metrics.peak_flexion = self._peak_flexion

        metrics.range_of_motion = (
            self._peak_extension -
            self._peak_flexion
        )

    # ==========================================================
    # Lower Limb Metrics
    # ==========================================================

    def _calculate_lower_limb_metrics(
        self,
        skeleton: Skeleton,
        metrics: MovementMetrics,
    ):
        """
        Calculates lower-limb biomechanics.

        Placeholder for future implementation.
        """

        pass

    # ==========================================================
    # Geometry Helpers
    # ==========================================================

    def _calculate_angle_from_types(
        self,
        skeleton: Skeleton,
        joint_a: JointType,
        joint_b: JointType,
        joint_c: JointType,
    ) -> float | None:
        """
        Calculates a joint angle directly from three JointTypes.
        """

        first = skeleton.get_joint(joint_a)
        second = skeleton.get_joint(joint_b)
        third = skeleton.get_joint(joint_c)

        if (
            not self._joint_is_valid(first)
            or not self._joint_is_valid(second)
            or not self._joint_is_valid(third)
        ):
            return None

        return self._calculate_joint_angle(
            first,
            second,
            third,
        )

    def _calculate_joint_angle(
        self,
        joint_a: Joint,
        joint_b: Joint,
        joint_c: Joint,
    ) -> float | None:
        """
        Calculates the angle formed by three joints.
        """

        vector1_x = joint_a.x - joint_b.x
        vector1_y = joint_a.y - joint_b.y

        vector2_x = joint_c.x - joint_b.x
        vector2_y = joint_c.y - joint_b.y

        dot_product = (
            vector1_x * vector2_x +
            vector1_y * vector2_y
        )

        magnitude1 = math.sqrt(
            vector1_x ** 2 +
            vector1_y ** 2
        )

        magnitude2 = math.sqrt(
            vector2_x ** 2 +
            vector2_y ** 2
        )

        if magnitude1 == 0 or magnitude2 == 0:
            return None

        cosine = dot_product / (magnitude1 * magnitude2)
        cosine = max(-1.0, min(1.0, cosine))

        return math.degrees(
            math.acos(cosine)
        )

    def _joint_is_valid(
        self,
        joint: Joint | None,
    ) -> bool:
        """
        Returns True if a joint exists and has sufficient visibility.
        """

        return (
            joint is not None
            and joint.visibility >= self.MIN_VISIBILITY
        )