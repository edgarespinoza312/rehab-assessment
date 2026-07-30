"""
temporal_analyzer.py

Computes time-based movement metrics.

Responsibilities
----------------
- Instantaneous velocity
- Peak velocity
- Average velocity

This analyzer measures temporal biomechanics only.
It does NOT detect exercise repetitions.
"""

import time

from core.models import (
    Skeleton,
    MovementMetrics,
)


class TemporalAnalyzer:
    """
    Computes temporal biomechanical measurements.
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
        Updates temporal movement metrics using the
        current skeleton frame.
        """

        # ---------------------------------------------
        # Choose the primary joint to monitor.
        #
        # Currently:
        #   - Left elbow if available
        #   - Otherwise right elbow
        #
        # Later this can become exercise-specific.
        # ---------------------------------------------

        angle = None

        if metrics.elbow_angle_left is not None:
            angle = metrics.elbow_angle_left

        elif metrics.elbow_angle_right is not None:
            angle = metrics.elbow_angle_right

        # No tracked joint.

        if angle is None:

            self.previous_time = None
            self.previous_angle = None

            metrics.peak_velocity = 0.0
            metrics.average_velocity = 0.0

            return

        current_time = time.monotonic()

        # First frame.

        if self.previous_time is None:

            self.previous_time = current_time
            self.previous_angle = angle

            metrics.peak_velocity = 0.0
            metrics.average_velocity = 0.0

            return

        # ---------------------------------------------
        # Time delta
        # ---------------------------------------------

        delta_time = current_time - self.previous_time

        if delta_time <= 0.0:

            self.previous_time = current_time
            self.previous_angle = angle

            return

        # ---------------------------------------------
        # Angular velocity
        # ---------------------------------------------

        delta_angle = angle - self.previous_angle

        velocity = abs(delta_angle) / delta_time

        # ---------------------------------------------
        # Running statistics
        # ---------------------------------------------

        self.velocity_sum += velocity
        self.velocity_samples += 1

        if velocity > self.peak_velocity:
            self.peak_velocity = velocity

        # ---------------------------------------------
        # Output metrics
        # ---------------------------------------------

        metrics.peak_velocity = self.peak_velocity

        metrics.average_velocity = (
            self.velocity_sum /
            self.velocity_samples
        )

        # ---------------------------------------------
        # Save history
        # ---------------------------------------------

        self.previous_time = current_time
        self.previous_angle = angle

    def reset(self):
        """
        Clears all temporal history.
        """

        self.previous_time = None
        self.previous_angle = None

        self.velocity_sum = 0.0
        self.velocity_samples = 0

        self.peak_velocity = 0.0