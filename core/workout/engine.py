"""Workflow orchestration for ordered workout prescriptions."""

from dataclasses import replace
from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from core.models import AssessmentResult, ExerciseState

from .definitions import ExerciseDefinitionRegistry
from .models import (
    ExerciseCompletionStatus,
    ExerciseResult,
    SessionSnapshot,
    SessionStatus,
    WorkoutPreset,
    WorkoutSession,
)
from .registry import BUILTIN_EXERCISES


class InvalidSessionTransition(RuntimeError):
    """Raised when a workflow operation is invalid for the current state."""


class SessionEngine:
    """Coordinates workflow while delegating all movement analysis downstream.

    Callers serialize access using Revaliv's existing assessment-state lock.
    The engine consumes authoritative readiness, ExerciseState, and
    AssessmentResult values; it does not estimate poses or calculate scores.
    """

    def __init__(
        self,
        registry: ExerciseDefinitionRegistry | None = None,
        *,
        now: Callable[[], datetime] | None = None,
        create_session_id: Callable[[], str] | None = None,
    ):
        self.registry = registry or BUILTIN_EXERCISES
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._create_session_id = create_session_id or (lambda: str(uuid4()))
        self._session: WorkoutSession | None = None

    @property
    def current_prescription(self):
        if self._session is None or self._session.status is SessionStatus.SESSION_COMPLETE:
            return None
        return self._session.preset.exercises[self._session.current_exercise_index]

    @property
    def status(self) -> SessionStatus:
        return self._session.status if self._session is not None else SessionStatus.NOT_STARTED

    @property
    def current_profile(self):
        prescription = self.current_prescription
        if prescription is None:
            return None
        return self.registry.get(prescription.exercise_id).profile_for_side(prescription.side)

    @property
    def calibration_side(self) -> str | None:
        """Side for the existing backend's begin_calibration(side) call."""
        profile = self.current_profile
        return profile.target_side if profile is not None else None

    def start(self, preset: WorkoutPreset, patient_id: int | None = None) -> SessionSnapshot:
        if self._session is not None and self._session.status not in {
            SessionStatus.SESSION_COMPLETE, SessionStatus.CANCELLED,
        }:
            raise InvalidSessionTransition("a workout session is already active")
        preset.validate(self.registry)
        started_at = self._now()
        self._session = WorkoutSession(
            preset=preset,
            patient_id=patient_id,
            session_id=self._create_session_id(),
            status=SessionStatus.CALIBRATING,
            started_at=started_at,
            current_exercise_started_at=started_at,
        )
        return self.snapshot()

    def calibration_succeeded(self) -> SessionSnapshot:
        """Record the readiness decision already made by ExerciseReadiness."""
        session = self._require_status(SessionStatus.CALIBRATING)
        session.status = SessionStatus.READY
        return self.snapshot()

    def begin_exercise(self) -> SessionSnapshot:
        session = self._require_status(SessionStatus.READY)
        session.status = SessionStatus.EXERCISING
        return self.snapshot()

    def record_repetition(
        self,
        exercise_state: ExerciseState | None,
        result: AssessmentResult | None,
    ) -> bool:
        """Record an authoritative completed-repetition event and its score."""
        if exercise_state is None or not exercise_state.rep_completed or result is None:
            return False
        session = self._require_status(SessionStatus.EXERCISING)
        prescription = self.current_prescription
        definition = self.registry.get(prescription.exercise_id)
        profile = definition.profile_for_side(prescription.side)
        if exercise_state.exercise_name not in (None, profile.exercise.name):
            return False
        session.current_repetition_results.append(replace(result, feedback=list(result.feedback)))
        if len(session.current_repetition_results) >= prescription.target_repetitions:
            now = self._now()
            session.completed_exercises.append(ExerciseResult(
                exercise_id=definition.id,
                display_name=definition.display_name,
                side=prescription.side,
                target_repetitions=prescription.target_repetitions,
                repetition_results=tuple(session.current_repetition_results[:prescription.target_repetitions]),
                status=ExerciseCompletionStatus.COMPLETE,
                started_at=session.current_exercise_started_at or now,
                completed_at=now,
                resistance_value=prescription.resistance_value,
                resistance_unit=prescription.resistance_unit,
                resistance_type=prescription.resistance_type,
            ))
            session.current_repetition_results.clear()
            session.status = SessionStatus.EXERCISE_COMPLETE
        return True

    def advance(self) -> SessionSnapshot:
        session = self._require_status(SessionStatus.EXERCISE_COMPLETE)
        next_index = session.current_exercise_index + 1
        if next_index >= len(session.preset.exercises):
            session.status = SessionStatus.SESSION_COMPLETE
            session.ended_at = self._now()
            return self.snapshot()
        session.current_exercise_index = next_index
        session.current_repetition_results.clear()
        session.status = SessionStatus.TRANSITIONING
        return self.snapshot()

    def begin_next_calibration(self) -> SessionSnapshot:
        session = self._require_status(SessionStatus.TRANSITIONING)
        session.status = SessionStatus.CALIBRATING
        session.current_exercise_started_at = self._now()
        return self.snapshot()

    def cancel(self) -> SessionSnapshot:
        session = self._session
        if session is None:
            raise InvalidSessionTransition("no workout session has been started")
        if session.status in {SessionStatus.SESSION_COMPLETE, SessionStatus.CANCELLED}:
            raise InvalidSessionTransition(f"cannot cancel a {session.status.value} session")
        session.status = SessionStatus.CANCELLED
        session.ended_at = self._now()
        return self.snapshot()

    def snapshot(self) -> SessionSnapshot:
        session = self._session
        if session is None:
            raise InvalidSessionTransition("no workout session has been started")
        prescription = self.current_prescription
        if prescription is None:
            current = (None, None, None, 0, 0, None, None, None)
        else:
            definition = self.registry.get(prescription.exercise_id)
            current = (
                definition.id,
                definition.display_name,
                prescription.side,
                prescription.target_repetitions,
                len(session.current_repetition_results),
                prescription.resistance_value,
                prescription.resistance_unit,
                prescription.resistance_type,
            )
        return SessionSnapshot(
            session_id=session.session_id,
            patient_id=session.patient_id,
            preset_id=session.preset.id,
            preset_name=session.preset.name,
            status=session.status,
            current_exercise_index=session.current_exercise_index,
            total_exercises=len(session.preset.exercises),
            current_exercise_id=current[0],
            current_exercise_name=current[1],
            current_side=current[2],
            target_repetitions=current[3],
            completed_repetitions=current[4],
            resistance_value=current[5],
            resistance_unit=current[6],
            resistance_type=current[7],
            completed_exercises=tuple(result.to_dict() for result in session.completed_exercises),
            started_at=session.started_at,
            ended_at=session.ended_at,
        )

    def _require_status(self, expected: SessionStatus) -> WorkoutSession:
        if self._session is None:
            raise InvalidSessionTransition("no workout session has been started")
        if self._session.status is not expected:
            raise InvalidSessionTransition(
                f"expected {expected.value}, got {self._session.status.value}"
            )
        return self._session
