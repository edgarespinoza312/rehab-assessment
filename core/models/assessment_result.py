"""
assessment_result.py

Represents the outcome of evaluating a rehabilitation exercise.

The AssessmentResult is produced by the Assessment Engine after
analyzing a completed or ongoing exercise. It summarizes movement
quality through individual assessment domains, an overall performance
score, and clinician-style feedback.

The model is intentionally independent of any specific exercise.
Different exercises may evaluate different movement characteristics,
but all assessments produce the same result structure.
"""

from dataclasses import dataclass, field


@dataclass
class AssessmentResult:
    """
    Stores the results of a rehabilitation assessment.
    """

    # --------------------------------------------------
    # Overall Assessment
    # --------------------------------------------------

    overall_score: float = 0.0

    # --------------------------------------------------
    # Domain Scores
    # --------------------------------------------------

    rom_score: float = 0.0
    tempo_score: float = 0.0
    completion_score: float = 0.0

    stability_score: float = 0.0
    compensation_score: float = 0.0
    symmetry_score: float = 0.0

    # --------------------------------------------------
    # Clinical Feedback
    # --------------------------------------------------

    feedback: list[str] = field(default_factory=list)