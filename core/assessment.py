"""
assessment.py

Implements the Assessment Layer of the rehabilitation
assessment system.

Responsibilities
----------------
- Interpret biomechanical measurements.
- Evaluate rehabilitation performance.
- Generate domain-specific rehabilitation scores.
- Produce an overall assessment.

This module performs interpretation only.

It does NOT perform:
- Pose estimation
- Joint angle calculation
- Biomechanical analysis
"""

from core.models.exercise_profile import ExerciseProfile
from core.models.exercise_state import ExerciseState
from core.models.movement_metrics import MovementMetrics
from core.models.assessment_result import AssessmentResult


class AssessmentEngine:
    """
    Interprets biomechanical measurements and converts
    them into clinician-style rehabilitation scores.
    """

    # ==========================================================
    # Assessment Weights
    # ==========================================================

    ROM_WEIGHT = 0.25
    TEMPO_WEIGHT = 0.15
    COMPLETION_WEIGHT = 0.20
    STABILITY_WEIGHT = 0.15
    COMPENSATION_WEIGHT = 0.15
    SYMMETRY_WEIGHT = 0.10

    # ==========================================================
    # Construction
    # ==========================================================

    def __init__(self):
        pass

    # ==========================================================
    # Public API
    # ==========================================================

    def analyze(
        self,
        profile: ExerciseProfile,
        metrics: MovementMetrics,
        exercise_state: ExerciseState,
    ) -> AssessmentResult:

        result = AssessmentResult()

        result.rom_score = self._evaluate_rom(
            profile,
            metrics,
        )

        result.tempo_score = self._evaluate_tempo(
            profile,
            metrics,
        )

        result.completion_score = self._evaluate_completion(
            profile,
            metrics,
            exercise_state,
        )

        result.stability_score = self._evaluate_stability(
            metrics,
        )

        result.compensation_score = (
            self._evaluate_compensation(
                metrics,
            )
        )

        result.symmetry_score = self._evaluate_symmetry(
            metrics,
        )

        result.overall_score = self._calculate_overall(
            result,
        )

        result.feedback = self._generate_feedback(
            result,
            metrics,
        )

        return result

    # ==========================================================
    # Range of Motion
    # ==========================================================

    def _evaluate_rom(
        self,
        profile: ExerciseProfile,
        metrics: MovementMetrics,
    ) -> float:

        if profile.target_rom <= 0:
            return 0.0

        score = (
            metrics.range_of_motion /
            profile.target_rom
        ) * 100.0

        return self._clamp(score)

    # ==========================================================
    # Tempo
    # ==========================================================

    def _evaluate_tempo(
        self,
        profile: ExerciseProfile,
        metrics: MovementMetrics,
    ) -> float:

        duration = metrics.rep_duration

        if duration <= 0:
            return 0.0

        if profile.ideal_rep_time <= 0:
            return 100.0

        difference = abs(
            duration -
            profile.ideal_rep_time
        )

        tolerance = max(
            profile.ideal_rep_time * 0.20,
            0.25,
        )

        if difference <= tolerance:
            return 100.0

        penalty = (
            difference /
            profile.ideal_rep_time
        ) * 100.0

        return self._clamp(
            100.0 - penalty
        )

    # ==========================================================
    # Completion
    # ==========================================================

    def _evaluate_completion(
        self,
        profile: ExerciseProfile,
        metrics: MovementMetrics,
        exercise_state: ExerciseState,
    ) -> float:

        if not exercise_state.rep_completed:
            return 0.0

        if profile.target_rom <= 0:
            return 100.0

        completion = (
            metrics.range_of_motion /
            profile.target_rom
        ) * 100.0

        return self._clamp(completion)

    # ==========================================================
    # Stability
    # ==========================================================

    def _evaluate_stability(
        self,
        metrics: MovementMetrics,
    ) -> float:

        shoulder_penalty = (
            metrics.shoulder_displacement * 800.0
        )

        torso_penalty = (
            metrics.torso_displacement * 1200.0
        )

        score = (
            100.0 -
            shoulder_penalty -
            torso_penalty
        )

        return self._clamp(score)

    # ==========================================================
    # Compensation
    # ==========================================================

    def _evaluate_compensation(
        self,
        metrics: MovementMetrics,
    ) -> float:

        score = 100.0

        score -= (
            metrics.shoulder_hike * 1000.0
        )

        score -= (
            metrics.trunk_lean * 2.0
        )

        return self._clamp(score)

    # ==========================================================
    # Symmetry
    # ==========================================================

    def _evaluate_symmetry(
        self,
        metrics: MovementMetrics,
    ) -> float:

        shoulder = max(
            0.0,
            100.0 -
            metrics.shoulder_height_difference * 1000.0
        )

        wrist = max(
            0.0,
            100.0 -
            metrics.wrist_height_difference * 1000.0
        )

        elbow = max(
            0.0,
            100.0 -
            metrics.elbow_angle_difference
        )

        score = (
            shoulder +
            wrist +
            elbow
        ) / 3.0

        return self._clamp(score)

    # ==========================================================
    # Overall Assessment
    # ==========================================================

    def _calculate_overall(
        self,
        result: AssessmentResult,
    ) -> float:

        overall = (

            result.rom_score *
            self.ROM_WEIGHT +

            result.tempo_score *
            self.TEMPO_WEIGHT +

            result.completion_score *
            self.COMPLETION_WEIGHT +

            result.stability_score *
            self.STABILITY_WEIGHT +

            result.compensation_score *
            self.COMPENSATION_WEIGHT +

            result.symmetry_score *
            self.SYMMETRY_WEIGHT

        )

        return round(
            self._clamp(overall),
            1,
        )

    # ==========================================================
    # Utility
    # ==========================================================

    def _clamp(
        self,
        score: float,
    ) -> float:

        return max(
            0.0,
            min(
                score,
                100.0,
            ),
        )

    # ==========================================================
    # Clinical Feedback
    # ==========================================================

    def _generate_feedback(
        self,
        result: AssessmentResult,
        metrics: MovementMetrics,
    ) -> list[str]:
        """
        Generates clinician-style rehabilitation feedback.

        Feedback is organized by assessment domain rather than
        individual measurements.
        """

        feedback: list[str] = []

        # ------------------------------------------------------
        # Range of Motion
        # ------------------------------------------------------

        if result.rom_score >= 90:

            feedback.append(
                "✓ Full range of motion achieved."
            )

        elif result.rom_score >= 70:

            feedback.append(
                "Increase the range of motion slightly to reach the target position."
            )

        else:

            feedback.append(
                "Significantly increase the range of motion during the exercise."
            )

        # ------------------------------------------------------
        # Tempo
        # ------------------------------------------------------

        if metrics.rep_duration <= 0:

            feedback.append(
                "Movement timing could not be evaluated."
            )

        elif result.tempo_score >= 90:

            feedback.append(
                "✓ Movement speed was well controlled."
            )

        elif result.tempo_score >= 70:

            feedback.append(
                "Perform the exercise at a more consistent pace."
            )

        else:

            feedback.append(
                "Slow down and maintain a controlled movement speed."
            )

        # ------------------------------------------------------
        # Completion
        # ------------------------------------------------------

        if result.completion_score >= 90:

            feedback.append(
                "✓ Exercise repetition completed successfully."
            )

        elif result.completion_score >= 70:

            feedback.append(
                "Complete the entire movement before returning."
            )

        else:

            feedback.append(
                "Focus on completing the prescribed repetition."
            )

        # ------------------------------------------------------
        # Stability
        # ------------------------------------------------------

        if result.stability_score >= 90:

            feedback.append(
                "✓ Stable upper-body posture maintained."
            )

        else:

            if metrics.torso_displacement > 0.02:

                feedback.append(
                    "Reduce unnecessary torso movement."
                )

            if metrics.shoulder_displacement > 0.015:

                feedback.append(
                    "Keep the shoulders steadier throughout the exercise."
                )

        # ------------------------------------------------------
        # Compensation
        # ------------------------------------------------------

        if result.compensation_score >= 90:

            feedback.append(
                "✓ Minimal compensatory movement detected."
            )

        else:

            if metrics.trunk_lean_detected:

                feedback.append(
                    "Reduce trunk leaning during the movement."
                )

            if metrics.shoulder_hike_detected:

                feedback.append(
                    "Avoid elevating the shoulder while lifting the arm."
                )

        # ------------------------------------------------------
        # Symmetry
        # ------------------------------------------------------

        if result.symmetry_score >= 90:

            feedback.append(
                "✓ Good left-right movement symmetry."
            )

        else:

            if metrics.elbow_angle_difference > 10:

                feedback.append(
                    "Keep both elbows moving through a similar range."
                )

            if metrics.shoulder_height_difference > 0.02:

                feedback.append(
                    "Maintain level shoulders throughout the exercise."
                )

            if metrics.wrist_height_difference > 0.02:

                feedback.append(
                    "Keep both hands moving at similar heights."
                )

        # ------------------------------------------------------
        # Overall Assessment
        # ------------------------------------------------------

        if result.overall_score >= 95:

            feedback.append(
                "Overall assessment: Excellent rehabilitation performance."
            )

        elif result.overall_score >= 85:

            feedback.append(
                "Overall assessment: Very good movement quality."
            )

        elif result.overall_score >= 70:

            feedback.append(
                "Overall assessment: Good performance with minor improvements recommended."
            )

        else:

            feedback.append(
                "Overall assessment: Continue practicing to improve movement quality."
            )

        return feedback