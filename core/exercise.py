import time

from core.models import (
    ExerciseProfile,
    ExerciseState,
    ExercisePhase,
    ExerciseType,
    MovementMetrics,
)


class ExerciseEngine:
    """
    Recognizes rehabilitation exercises from biomechanical metrics.

    Responsibilities
    ----------------
    - Detect exercise phases
    - Count repetitions
    - Measure repetition duration
    - Generate one-frame exercise events

    This class does NOT compute biomechanics.
    """

    LOWERED_THRESHOLD = 150.0
    TOP_THRESHOLD = 60.0

    def __init__(self):
        self.state = ExerciseState()

    # ==========================================================
    # Public API
    # ==========================================================

    def analyze(
        self,
        profile: ExerciseProfile,
        metrics: MovementMetrics,
    ) -> ExerciseState:
        """
        Analyze the current biomechanical metrics and update the
        current exercise state.
        """

        # ------------------------------------------------------
        # Events only last one frame.
        # ------------------------------------------------------

        self.state.rep_started = False
        self.state.rep_completed = False

        match profile.exercise:

            case ExerciseType.LEFT_BICEP_CURL:
                self._analyze_bicep_curl(
                    ExerciseType.LEFT_BICEP_CURL,
                    metrics.elbow_angle_left,
                    metrics,
                )

            case ExerciseType.RIGHT_BICEP_CURL:
                self._analyze_bicep_curl(
                    ExerciseType.RIGHT_BICEP_CURL,
                    metrics.elbow_angle_right,
                    metrics,
                )

            case ExerciseType.LEFT_TRICEP_EXTENSION:
                self._analyze_reverse_angle(
                    ExerciseType.LEFT_TRICEP_EXTENSION, metrics.elbow_angle_left,
                    metrics, start_threshold=90.0, end_threshold=150.0,
                )

            case ExerciseType.RIGHT_TRICEP_EXTENSION:
                self._analyze_reverse_angle(
                    ExerciseType.RIGHT_TRICEP_EXTENSION, metrics.elbow_angle_right,
                    metrics, start_threshold=90.0, end_threshold=150.0,
                )

            case ExerciseType.LEFT_KNEE_EXTENSION:
                self._analyze_reverse_angle(
                    ExerciseType.LEFT_KNEE_EXTENSION, metrics.knee_angle_left,
                    metrics, start_threshold=110.0, end_threshold=150.0,
                )

            case ExerciseType.RIGHT_KNEE_EXTENSION:
                self._analyze_reverse_angle(
                    ExerciseType.RIGHT_KNEE_EXTENSION, metrics.knee_angle_right,
                    metrics, start_threshold=110.0, end_threshold=150.0,
                )

            case ExerciseType.LEFT_SHOULDER_ABDUCTION:
                self._analyze_reverse_angle(
                    ExerciseType.LEFT_SHOULDER_ABDUCTION, metrics.shoulder_angle_left,
                    metrics, start_threshold=25.0, end_threshold=70.0,
                )

            case ExerciseType.RIGHT_SHOULDER_ABDUCTION:
                self._analyze_reverse_angle(
                    ExerciseType.RIGHT_SHOULDER_ABDUCTION, metrics.shoulder_angle_right,
                    metrics, start_threshold=25.0, end_threshold=70.0,
                )

            case _:
                raise NotImplementedError(
                    f"{profile.display_name} is not yet supported."
                )

        return self.state

    # ==========================================================
    # Exercise Implementations
    # ==========================================================

    def _analyze_bicep_curl(
        self,
        exercise: ExerciseType,
        angle: float,
        metrics: MovementMetrics,
    ):
        """
        Detects and tracks a bicep curl using the elbow angle.
        """

        # ------------------------------------------------------
        # Tracking Lost
        # ------------------------------------------------------

        if angle is None:

            self.state.active = False
            self.state.exercise_name = None
            self.state.rep_start_time = None

            self._transition_to(
                ExercisePhase.IDLE
            )

            return

        self.state.active = True

        # Store the actual exercise being analyzed
        self.state.exercise_name = exercise.name

        # ------------------------------------------------------
        # Lowered Position
        # ------------------------------------------------------

        if angle >= self.LOWERED_THRESHOLD:

            # Finished a repetition.

            if self.state.phase == ExercisePhase.LOWERING:
                if self.state.rep_start_time is not None:

                    duration = (
                        time.monotonic()
                        - self.state.rep_start_time
                    )
                    if duration > 0:
                        metrics.rep_duration = duration
                        self.state.repetitions += 1
                        self.state.rep_completed = True

                # A completion without a valid start is not a scored rep.
                self.state.rep_start_time = None

            self._transition_to(
                ExercisePhase.LOWERED
            )

            return

        # ------------------------------------------------------
        # Top Position
        # ------------------------------------------------------

        if angle <= self.TOP_THRESHOLD:

            self._transition_to(
                ExercisePhase.TOP
            )

            return

        # ------------------------------------------------------
        # Middle Range
        # ------------------------------------------------------

        if self.state.phase == ExercisePhase.LOWERED:

            # Started a new repetition.

            self.state.rep_started = True

            # Record when the repetition began.
            self.state.rep_start_time = time.monotonic()

            self._transition_to(
                ExercisePhase.LIFTING
            )

            return

        if self.state.phase == ExercisePhase.TOP:

            self._transition_to(
                ExercisePhase.LOWERING
            )

            return

    # ==========================================================
    # Internal Helpers
    # ==========================================================

    def _transition_to(
        self,
        phase: ExercisePhase,
    ):
        """
        Transition to a new exercise phase.

        Prevents unnecessary writes when the phase
        has not actually changed.
        """

        if self.state.phase == phase:
            return

        self.state.phase = phase


    def _analyze_reverse_angle(
        self,
        exercise: ExerciseType,
        angle: float | None,
        metrics: MovementMetrics,
        *,
        start_threshold: float,
        end_threshold: float,
    ):
        """Recognize movements whose tracked angle increases during the lift."""
        if angle is None:
            self.state.active = False
            self.state.exercise_name = None
            self.state.rep_start_time = None
            self._transition_to(ExercisePhase.IDLE)
            return

        self.state.active = True
        self.state.exercise_name = exercise.name

        if angle <= start_threshold:
            if self.state.phase == ExercisePhase.LOWERING:
                if self.state.rep_start_time is not None:
                    duration = time.monotonic() - self.state.rep_start_time
                    if duration > 0:
                        metrics.rep_duration = duration
                        self.state.repetitions += 1
                        self.state.rep_completed = True
                self.state.rep_start_time = None
            self._transition_to(ExercisePhase.LOWERED)
            return

        if angle >= end_threshold:
            self._transition_to(ExercisePhase.TOP)
            return

        if self.state.phase == ExercisePhase.LOWERED:
            self.state.rep_started = True
            self.state.rep_start_time = time.monotonic()
            self._transition_to(ExercisePhase.LIFTING)
            return

        if self.state.phase == ExercisePhase.TOP:
            self._transition_to(ExercisePhase.LOWERING)
            return
