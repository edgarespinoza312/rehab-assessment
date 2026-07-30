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

        self._analyzers = [

            JointAnalyzer(),

            StabilityAnalyzer(),

            TemporalAnalyzer(),

            CompensationAnalyzer(),

            SymmetryAnalyzer(),

        ]

    # ==========================================================
    # Public API
    # ==========================================================

    def calculate_metrics(
        self,
        skeleton: Skeleton,
    ) -> MovementMetrics:
        """
        Calculates all biomechanical measurements for
        the current frame.
        """

        metrics = MovementMetrics()

        for analyzer in self._analyzers:

            analyzer.analyze(
                skeleton,
                metrics,
            )

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