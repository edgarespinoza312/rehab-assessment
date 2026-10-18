"""Shared perception result types and backend contract."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol

from core.models import Skeleton


class PoseStatus(str, Enum):
    VALID = "valid"
    AMBIGUOUS = "ambiguous"
    INVALID = "invalid"


class ReadinessState(str, Enum):
    NO_PERSON = "no_person"
    LOW_CONFIDENCE = "low_confidence"
    POOR_QUALITY = "poor_quality"
    CALIBRATION_REQUIRED = "calibration_required"
    IDENTITY_AMBIGUOUS = "identity_ambiguous"
    READY = "ready"


@dataclass
class PerceptionResult:
    skeleton: Skeleton | None
    status: PoseStatus
    backend: str
    timestamp: float
    frame_number: int
    quality: dict[str, Any] = field(default_factory=dict)
    tracking: bool = False
    diagnostics: dict[str, Any] = field(default_factory=dict)
    state: ReadinessState | None = None

    def __post_init__(self):
        if self.state is None:
            if self.status is PoseStatus.VALID and self.skeleton is not None:
                self.state = ReadinessState.READY
            elif self.status is PoseStatus.AMBIGUOUS:
                self.state = ReadinessState.IDENTITY_AMBIGUOUS
            else:
                self.state = ReadinessState.POOR_QUALITY

    @property
    def pose_valid(self) -> bool:
        return (
            self.state is ReadinessState.READY
            and self.status is PoseStatus.VALID
            and self.skeleton is not None
        )


def is_rejected_result(result: PerceptionResult | None) -> bool:
    """Fail closed unless a backend explicitly supplies a valid pose."""
    return result is None or not result.pose_valid


def is_rejected_experimental_result(result: PerceptionResult | None) -> bool:
    """Backward-compatible name for the shared result validity check."""
    return is_rejected_result(result)


class PerceptionBackend(Protocol):
    name: str
    last_result: PerceptionResult | None

    @property
    def calibration_status(self) -> dict[str, Any]: ...

    def begin_calibration(self, side: str) -> None: ...

    def reset_calibration(self) -> None: ...

    def process(
        self,
        frame,
        timestamp: float = 0.0,
        frame_number: int = 0,
        performance=None,
        exercise_side: str | None = None,
    ) -> tuple[Any, Skeleton | None]: ...

    def close(self) -> None: ...
