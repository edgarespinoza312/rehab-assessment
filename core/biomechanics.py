"""
biomechanics.py

Coordinates all biomechanical analyzers.

The BiomechanicsEngine does not perform biomechanical
calculations itself. Instead, it delegates responsibility
to specialized analyzers and aggregates their outputs into
a single MovementMetrics object.
"""

from core.models import (
    Skeleton,
    MovementMetrics,
    ExerciseProfile,
)

from core.analyzers.joint_analyzer import JointAnalyzer
from core.analyzers.stability_analyzer import StabilityAnalyzer
from core.analyzers.temporal_analyzer import TemporalAnalyzer
from core.analyzers.compensation_analyzer import CompensationAnalyzer
from core.analyzers.symmetry_analyzer import SymmetryAnalyzer


class BiomechanicsEngine:
    """
    Coordinates all biomechanical analyzers.
    """

    def __init__(self):
        """
        Initializes all biomechanics analyzers.
        """

        self._joint_analyzer = JointAnalyzer()
        self._stability_analyzer = StabilityAnalyzer()
        self._temporal_analyzer = TemporalAnalyzer()
        self._compensation_analyzer = CompensationAnalyzer()
        self._symmetry_analyzer = SymmetryAnalyzer()

        self._analyzers = [
            self._joint_analyzer,
            self._stability_analyzer,
            self._temporal_analyzer,
            self._compensation_analyzer,
            self._symmetry_analyzer,
        ]

    # ==========================================================
    # Public API
    # ==========================================================

    def calculate_metrics(
        self,
        skeleton: Skeleton,
        profile: ExerciseProfile | None = None,
    ) -> MovementMetrics:
        """
        Calculates all biomechanical measurements for
        the current frame.
        """

        metrics = MovementMetrics()

        for analyzer in self._analyzers:
            if (
                analyzer is self._joint_analyzer
                or analyzer is self._temporal_analyzer
            ):
                analyzer.analyze(skeleton, metrics, profile)
            else:
                analyzer.analyze(skeleton, metrics)

        return metrics

    def reset_rep_metrics(self):
        """
        Resets any analyzer state that persists across
        repetitions.
        """

        for analyzer in self._analyzers:

            if hasattr(
                analyzer,
                "reset",
            ):
                analyzer.reset()