from dataclasses import dataclass

from .exercise_phase import ExercisePhase


@dataclass
class ExerciseState:
    """
    Represents the current state of an exercise.

    This model stores the output of the ExerciseEngine, describing
    the recognized exercise, its current movement phase, repetition
    count, and one-frame exercise events.
    """

    # ----------------------------------------------------------
    # Exercise Information
    # ----------------------------------------------------------

    exercise_name: str | None = None

    active: bool = False

    confidence: float = 1.0

    # ----------------------------------------------------------
    # Movement State
    # ----------------------------------------------------------

    phase: ExercisePhase = ExercisePhase.IDLE

    repetitions: int = 0

    # ----------------------------------------------------------
    # Repetition Timing
    # ----------------------------------------------------------

    # Timestamp when the current repetition began.
    # None indicates no repetition is currently active.
    rep_start_time: float | None = None

    # ----------------------------------------------------------
    # Exercise Events
    # ----------------------------------------------------------

    # Becomes True for one frame when a new repetition begins.
    rep_started: bool = False

    # Becomes True for one frame when a repetition finishes.
    rep_completed: bool = False