"""
compensation_analyzer.py

Computes compensatory movement measurements.

Responsibilities
----------------
- Shoulder hiking
- Trunk lean

This analyzer measures compensatory movement patterns.
It does NOT score movement quality.
"""

import math

from core.models import (
    Skeleton,
    MovementMetrics,
    JointType,
)


class CompensationAnalyzer:
    """
    Computes compensatory movement measurements.
    """

    # ----------------------------------------------------------
    # Detection Thresholds
    # ----------------------------------------------------------

    SHOULDER_HIKE_THRESHOLD = 0.03
    TRUNK_LEAN_THRESHOLD = 8.0  # degrees

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
        Computes compensation measurements from the
        current skeleton.
        """

        joints = self._extract_landmarks(skeleton)

        if joints is None:

            metrics.shoulder_hike = 0.0
            metrics.trunk_lean = 0.0

            metrics.shoulder_hike_detected = False
            metrics.trunk_lean_detected = False

            return

        (
            left_shoulder,
            right_shoulder,
            shoulder_center,
            pelvis_center,
        ) = joints

        # ------------------------------------------------------
        # Shoulder Hiking
        # ------------------------------------------------------

        shoulder_hike = self._compute_shoulder_hike(
            left_shoulder,
            right_shoulder,
        )

        metrics.shoulder_hike = shoulder_hike

        metrics.shoulder_hike_detected = (
            shoulder_hike >
            self.SHOULDER_HIKE_THRESHOLD
        )

        # ------------------------------------------------------
        # Trunk Lean
        # ------------------------------------------------------

        trunk_lean = self._compute_trunk_lean(
            shoulder_center,
            pelvis_center,
        )

        metrics.trunk_lean = trunk_lean

        metrics.trunk_lean_detected = (
            trunk_lean >
            self.TRUNK_LEAN_THRESHOLD
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

        shoulder_center = skeleton.get_joint(
            JointType.SHOULDER_CENTER
        )

        pelvis_center = skeleton.get_joint(
            JointType.PELVIS_CENTER
        )

        if (
            left_shoulder is None
            or right_shoulder is None
            or shoulder_center is None
            or pelvis_center is None
        ):
            return None

        return (
            left_shoulder,
            right_shoulder,
            shoulder_center,
            pelvis_center,
        )

    # ==========================================================
    # Compensation Measurements
    # ==========================================================

    def _compute_shoulder_hike(
        self,
        left_shoulder,
        right_shoulder,
    ) -> float:
        """
        Computes the vertical difference between
        both shoulders.
        """

        return abs(
            left_shoulder.y -
            right_shoulder.y
        )

    def _compute_trunk_lean(
        self,
        shoulder_center,
        pelvis_center,
    ) -> float:
        """
        Computes torso lean relative to vertical.
        """

        dx = (
            shoulder_center.x -
            pelvis_center.x
        )

        dy = (
            pelvis_center.y -
            shoulder_center.y
        )

        if dy == 0:
            return 90.0

        angle = math.degrees(
            math.atan2(
                abs(dx),
                abs(dy),
            )
        )

        return angle