"""
assessment_session.py

Represents an active rehabilitation assessment session.

The AssessmentSession stores the currently selected assessment,
its profile, the live exercise state, and the most recent
assessment result.

As the system grows, this class will become the central object
for session management, assessment results, reporting, and
patient interaction.
"""

from dataclasses import dataclass, field

from .assessment_result import AssessmentResult
from .exercise_profile import ExerciseProfile
from .exercise_state import ExerciseState
from .exercise_type import ExerciseType
from .movement_metrics import MovementMetrics
from dataclasses import dataclass, field
from typing import Optional
@dataclass
class AssessmentSession:
    """
    Represents an active rehabilitation assessment session.
    """

    exercise: ExerciseType

    profile: ExerciseProfile

    exercise_state: ExerciseState

    # Patient associated with this assessment
    patient_id: Optional[int] = None

    movement_metrics: MovementMetrics = field(
        default_factory=MovementMetrics
    )

    assessment_result: AssessmentResult = field(
        default_factory=AssessmentResult
    )