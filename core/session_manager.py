"""
session_manager.py

Maintains the assessment history for a rehabilitation session.

Unlike the AssessmentEngine, which evaluates a single repetition,
the SessionManager stores every completed repetition and computes
session-level statistics such as average score, best performance,
and recovery trends.

The SessionManager is exercise-agnostic and can be reused for
any rehabilitation exercise.
"""

from core.models import AssessmentResult


class SessionManager:
    """
    Manages the assessment history for a rehabilitation session.
    """

    def __init__(self):

        self._results: list[AssessmentResult] = []

    # ======================================================
    # Session Management
    # ======================================================

    def add_result(
        self,
        result: AssessmentResult,
    ) -> None:
        """
        Adds a completed repetition assessment to the session.
        """

        self._results.append(result)

        print(f"Stored repetition #{len(self._results)}")

    def clear(self) -> None:
        """
        Clears the current rehabilitation session.
        """

        self._results.clear()

    # ======================================================
    # Accessors
    # ======================================================

    @property
    def results(self) -> tuple[AssessmentResult, ...]:
        """
        Read-only view of the assessment history.
        """

        return tuple(self._results)

    @property
    def repetition_count(self) -> int:

        return len(self._results)

    @property
    def latest_result(self) -> AssessmentResult | None:

        if not self._results:
            return None

        return self._results[-1]

    # ======================================================
    # Statistics
    # ======================================================

    @property
    def average_score(self) -> float:

        if not self._results:
            return 0.0

        return sum(
            result.overall_score
            for result in self._results
        ) / len(self._results)

    @property
    def best_score(self) -> float:

        if not self._results:
            return 0.0

        return max(
            result.overall_score
            for result in self._results
        )

    @property
    def worst_score(self) -> float:

        if not self._results:
            return 0.0

        return min(
            result.overall_score
            for result in self._results
        )

    # ======================================================
    # Trend Analysis
    # ======================================================

    @property
    def trend(self) -> str:

        if len(self._results) < 6:
            return "Collecting Data"

        previous = self._results[-6:-3]
        recent = self._results[-3:]

        previous_average = sum(
            result.overall_score
            for result in previous
        ) / 3

        recent_average = sum(
            result.overall_score
            for result in recent
        ) / 3

        if recent_average > previous_average + 2:
            return "Improving"

        if recent_average < previous_average - 2:
            return "Declining"

        return "Stable"