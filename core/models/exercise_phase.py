from enum import Enum, auto


class ExercisePhase(Enum):
    """
    Represents the current phase of an exercise.

    These phases describe the movement progression of an exercise and
    are used by the ExerciseEngine to recognize movement sequences and
    count repetitions.
    """

    IDLE = auto()

    LOWERED = auto()

    LIFTING = auto()

    TOP = auto()

    LOWERING = auto()