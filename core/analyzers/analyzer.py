"""
analyzer.py

Defines the common interface implemented by all
biomechanical analyzers.
"""

from abc import ABC, abstractmethod

from core.models import (
    Skeleton,
    MovementMetrics,
)


class BiomechanicsAnalyzer(ABC):

    @abstractmethod
    def analyze(
        self,
        skeleton: Skeleton,
        metrics: MovementMetrics,
    ):
        """
        Computes biomechanical measurements.
        """
        pass

    def reset(self):
        """
        Resets analyzer state between repetitions.
        """
        pass