"""Dashboard adapter from live pipeline events to the domain SessionEngine."""

from collections.abc import Callable

from core.models import AssessmentResult, ExerciseState
from core.perception.base import PerceptionResult, is_rejected_result
from core.workout import SessionEngine, SessionStatus, WorkoutPreset


class WorkoutRuntimeAdapter:
    """Translate authoritative live pipeline values into workout transitions.

    The caller must hold the existing dashboard assessment-state lock for every
    mutation. `reset_pipeline` is supplied by the dashboard and runs on workout
    start, exercise transition, and cancellation.
    """

    def __init__(
        self,
        engine: SessionEngine | None = None,
        *,
        reset_pipeline: Callable[[str | None], None],
        workout_plan_id: int | None = None,
    ):
        self.engine = engine or SessionEngine()
        self._reset_pipeline = reset_pipeline
        self.workout_plan_id = workout_plan_id

    @property
    def status(self) -> SessionStatus:
        return self.engine.status

    @property
    def current_profile(self):
        return self.engine.current_profile

    @property
    def calibration_side(self) -> str | None:
        return self.engine.calibration_side

    @property
    def active(self) -> bool:
        return self.status in {
            SessionStatus.CALIBRATING,
            SessionStatus.READY,
            SessionStatus.EXERCISING,
            SessionStatus.EXERCISE_COMPLETE,
            SessionStatus.TRANSITIONING,
        }

    def start(
        self,
        preset: WorkoutPreset,
        patient_id: int | None = None,
        *,
        workout_plan_id: int | None = None,
    ):
        self.workout_plan_id = workout_plan_id
        snapshot = self.engine.start(preset, patient_id=patient_id)
        self._reset_pipeline(self.calibration_side)
        return snapshot

    def begin_frame(self, perception_result: PerceptionResult | None) -> bool:
        """Return whether this accepted frame may enter exercise analysis."""
        if is_rejected_result(perception_result):
            return False
        if self.status is SessionStatus.CALIBRATING:
            self.engine.calibration_succeeded()
            return False
        if self.status is SessionStatus.READY:
            self.engine.begin_exercise()
            return True
        return self.status is SessionStatus.EXERCISING

    def record_repetition(
        self,
        perception_result: PerceptionResult | None,
        exercise_state: ExerciseState | None,
        result: AssessmentResult | None,
    ) -> bool:
        """Forward one accepted completed rep, advancing when its target is met."""
        if is_rejected_result(perception_result):
            return False
        if self.status is not SessionStatus.EXERCISING:
            return False
        if not self.engine.record_repetition(exercise_state, result):
            return False
        if self.status is SessionStatus.EXERCISE_COMPLETE:
            transition = self.engine.advance()
            if transition.status is SessionStatus.TRANSITIONING:
                self.engine.begin_next_calibration()
                self._reset_pipeline(self.calibration_side)
            elif transition.status is SessionStatus.SESSION_COMPLETE:
                self._reset_pipeline(None)
            return True
        return True

    def cancel(self):
        snapshot = self.engine.cancel()
        self._reset_pipeline(None)
        return snapshot

    def snapshot(self):
        return self.engine.snapshot()
