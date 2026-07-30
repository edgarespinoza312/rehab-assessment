"""
stability_analyzer.py

Computes whole-body stability measurements.

Responsibilities
----------------
- Shoulder displacement
- Torso displacement
- Overall stability score

This analyzer measures body stability only.
It does NOT determine movement compensation.
"""

import math

from core.models import (
    Skeleton,
    MovementMetrics,
    JointType,
)


class StabilityAnalyzer:
    """
    Computes body stability metrics.
    """

    # ----------------------------------------------------------
    # Tunable scoring constants
    # ----------------------------------------------------------

    SHOULDER_WEIGHT = 250.0
    TORSO_WEIGHT = 400.0

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
        Computes body stability for the current frame.
        """

        landmarks = self._extract_landmarks(skeleton)

        if landmarks is None:

            metrics.shoulder_displacement = 0.0
            metrics.torso_displacement = 0.0
            metrics.stability_score = 100.0

            self.reset()
            return

        (
            left_shoulder,
            right_shoulder,
        ) = landmarks

        shoulder_disp = self._compute_shoulder_displacement(
            left_shoulder,
            right_shoulder,
        )

        torso_disp = self._compute_torso_displacement(
            left_shoulder,
            right_shoulder,
        )

        metrics.shoulder_displacement = shoulder_disp
        metrics.torso_displacement = torso_disp

        metrics.stability_score = self._compute_stability_score(
            shoulder_disp,
            torso_disp,
        )

        self.previous_left_shoulder = left_shoulder.position
        self.previous_right_shoulder = right_shoulder.position

        self.previous_torso_center = (
            (left_shoulder.x + right_shoulder.x) / 2.0,
            (left_shoulder.y + right_shoulder.y) / 2.0,
        )

    def reset(self):
        """
        Clears all stored frame history.
        """

        self.previous_left_shoulder = None
        self.previous_right_shoulder = None
        self.previous_torso_center = None

    # ==========================================================
    # Landmark Extraction
    # ==========================================================

    def _extract_landmarks(
        self,
        skeleton: Skeleton,
    ):

        left = skeleton.get_joint(
            JointType.LEFT_SHOULDER
        )

        right = skeleton.get_joint(
            JointType.RIGHT_SHOULDER
        )

        if left is None or right is None:
            return None

        return (
            left,
            right,
        )

    # ==========================================================
    # Measurements
    # ==========================================================

    def _compute_shoulder_displacement(
        self,
        left,
        right,
    ) -> float:

        if (
            self.previous_left_shoulder is None
            or self.previous_right_shoulder is None
        ):
            return 0.0

        left_disp = self._distance(
            self.previous_left_shoulder,
            left.position,
        )

        right_disp = self._distance(
            self.previous_right_shoulder,
            right.position,
        )

        return (left_disp + right_disp) / 2.0

    def _compute_torso_displacement(
        self,
        left,
        right,
    ) -> float:

        center = (
            (left.x + right.x) / 2.0,
            (left.y + right.y) / 2.0,
        )

        if self.previous_torso_center is None:
            return 0.0

        return self._distance(
            self.previous_torso_center,
            center,
        )

    def _compute_stability_score(
        self,
        shoulder_disp: float,
        torso_disp: float,
    ) -> float:

        score = (
            100.0
            - shoulder_disp * self.SHOULDER_WEIGHT
            - torso_disp * self.TORSO_WEIGHT
        )

        return self._clamp(score)

    # ==========================================================
    # Utilities
    # ==========================================================

    def _distance(
        self,
        p1,
        p2,
    ) -> float:

        return math.sqrt(
            (p1[0] - p2[0]) ** 2
            + (p1[1] - p2[1]) ** 2
        )

    def _clamp(
        self,
        value: float,
    ) -> float:

        return max(
            0.0,
            min(
                100.0,
                value,
            ),
        )