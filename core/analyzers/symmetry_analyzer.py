"""
symmetry_analyzer.py

Computes bilateral symmetry measurements.

Responsibilities
----------------
- Shoulder height difference
- Elbow angle difference
- Wrist height difference

This analyzer measures left/right symmetry only.
It does NOT score movement quality.
"""

from core.models import (
    Skeleton,
    MovementMetrics,
    JointType,
)


class SymmetryAnalyzer:
    """
    Computes bilateral symmetry measurements.
    """

    def __init__(self):
        self.reset()

    # ==========================================================
    # Public API
    # ==========================================================

    def analyze(
        self,
        skeleton: Skeleton,
        metrics: MovementMetrics,
    ):
        """
        Computes symmetry measurements for the current frame.
        """

        joints = self._extract_landmarks(skeleton)

        if joints is None:

            metrics.shoulder_height_difference = 0.0
            metrics.wrist_height_difference = 0.0
            metrics.elbow_angle_difference = 0.0

            return

        (
            left_shoulder,
            right_shoulder,
            left_wrist,
            right_wrist,
        ) = joints

        # ------------------------------------------------------
        # Shoulder Height Difference
        # ------------------------------------------------------

        metrics.shoulder_height_difference = (
            self._compute_shoulder_difference(
                left_shoulder,
                right_shoulder,
            )
        )

        # ------------------------------------------------------
        # Wrist Height Difference
        # ------------------------------------------------------

        metrics.wrist_height_difference = (
            self._compute_wrist_difference(
                left_wrist,
                right_wrist,
            )
        )

        # ------------------------------------------------------
        # Elbow Angle Difference
        # ------------------------------------------------------

        metrics.elbow_angle_difference = (
            self._compute_elbow_difference(
                metrics
            )
        )

    def reset(self):
        """
        No persistent state is maintained.
        """
        pass

    # ==========================================================
    # Landmark Extraction
    # ==========================================================

    def _extract_landmarks(
        self,
        skeleton: Skeleton,
    ):

        left_shoulder = skeleton.get_joint(
            JointType.LEFT_SHOULDER
        )

        right_shoulder = skeleton.get_joint(
            JointType.RIGHT_SHOULDER
        )

        left_wrist = skeleton.get_joint(
            JointType.LEFT_WRIST
        )

        right_wrist = skeleton.get_joint(
            JointType.RIGHT_WRIST
        )

        if (
            left_shoulder is None
            or right_shoulder is None
            or left_wrist is None
            or right_wrist is None
        ):
            return None

        return (
            left_shoulder,
            right_shoulder,
            left_wrist,
            right_wrist,
        )

    # ==========================================================
    # Symmetry Measurements
    # ==========================================================

    def _compute_shoulder_difference(
        self,
        left_shoulder,
        right_shoulder,
    ) -> float:
        """
        Computes the vertical difference between
        the left and right shoulders.
        """

        return abs(
            left_shoulder.y -
            right_shoulder.y
        )

    def _compute_wrist_difference(
        self,
        left_wrist,
        right_wrist,
    ) -> float:
        """
        Computes the vertical difference between
        the left and right wrists.
        """

        return abs(
            left_wrist.y -
            right_wrist.y
        )

    def _compute_elbow_difference(
        self,
        metrics: MovementMetrics,
    ) -> float:
        """
        Computes the difference between the
        left and right elbow flexion angles.
        """

        if (
            metrics.elbow_angle_left is None
            or metrics.elbow_angle_right is None
        ):
            return 0.0

        return abs(
            metrics.elbow_angle_left -
            metrics.elbow_angle_right
        )