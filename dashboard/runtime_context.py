"""Explicit per-application-session assessment/workout runtime state."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import threading
import uuid

from core.assessment import AssessmentEngine
from core.biomechanics import BiomechanicsEngine
from core.exercise import ExerciseEngine
from core.perception import create_perception_backend
from core.session_manager import SessionManager
from core.models import AssessmentSession
from dashboard.workout_runtime import WorkoutRuntimeAdapter
from ui.overlay import PoseDisplayContinuity


class RuntimeLifecycle(str, Enum):
    CREATED = "CREATED"
    ACTIVE = "ACTIVE"
    COMPLETING = "COMPLETING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


@dataclass
class RuntimeContext:
    """All mutable assessment/workout state owned by one application session."""

    runtime_id: str
    user_id: int
    patient_id: int | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    runtime_mode: str = "legacy_assessment"
    lifecycle: RuntimeLifecycle = RuntimeLifecycle.CREATED
    session: AssessmentSession | None = None
    completed_session: dict | None = None
    workout_runtime: WorkoutRuntimeAdapter | None = None
    pose: object = field(default_factory=create_perception_backend)
    biomechanics: BiomechanicsEngine = field(default_factory=BiomechanicsEngine)
    exercise: ExerciseEngine = field(default_factory=ExerciseEngine)
    assessment: AssessmentEngine = field(default_factory=AssessmentEngine)
    session_manager: SessionManager = field(default_factory=SessionManager)
    display_pose_continuity: PoseDisplayContinuity = field(
        default_factory=lambda: PoseDisplayContinuity(max_age_seconds=0.2)
    )
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    def touch(self) -> None:
        self.updated_at = datetime.utcnow()

    def transition(self, target: RuntimeLifecycle) -> None:
        if target is self.lifecycle:
            return
        allowed = {
            RuntimeLifecycle.CREATED: {RuntimeLifecycle.ACTIVE, RuntimeLifecycle.CANCELLED},
            RuntimeLifecycle.ACTIVE: {
                RuntimeLifecycle.COMPLETING,
                RuntimeLifecycle.CANCELLED,
                RuntimeLifecycle.EXPIRED,
            },
            RuntimeLifecycle.COMPLETING: {
                RuntimeLifecycle.COMPLETED,
                RuntimeLifecycle.CANCELLED,
            },
            RuntimeLifecycle.COMPLETED: set(),
            RuntimeLifecycle.CANCELLED: set(),
            RuntimeLifecycle.EXPIRED: set(),
        }
        if target not in allowed[self.lifecycle]:
            raise ValueError(
                f"invalid runtime transition: {self.lifecycle.value} -> {target.value}"
            )
        self.lifecycle = target
        self.touch()


class RuntimeRegistry:
    """Thread-safe registry for explicit application-session runtimes."""

    def __init__(self):
        self._contexts: dict[str, RuntimeContext] = {}
        self._lock = threading.RLock()

    def create(self, user_id: int, patient_id: int | None = None) -> RuntimeContext:
        context = RuntimeContext(
            runtime_id=uuid.uuid4().hex,
            user_id=user_id,
            patient_id=patient_id,
        )
        with self._lock:
            self._contexts[context.runtime_id] = context
        return context

    def get(self, runtime_id: str | None) -> RuntimeContext | None:
        if not isinstance(runtime_id, str):
            return None
        with self._lock:
            return self._contexts.get(runtime_id)

    def get_or_create(
        self,
        runtime_id: str | None,
        user_id: int,
        patient_id: int | None = None,
    ) -> RuntimeContext:
        context = self.get(runtime_id)
        if context is not None and context.user_id == user_id:
            return context
        return self.create(user_id, patient_id)

    def remove(self, runtime_id: str | None) -> None:
        if not isinstance(runtime_id, str):
            return
        with self._lock:
            self._contexts.pop(runtime_id, None)

    def snapshot(self) -> tuple[RuntimeContext, ...]:
        with self._lock:
            return tuple(self._contexts.values())
