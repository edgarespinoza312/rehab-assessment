"""Backend-independent exercise readiness and identity policy."""

from dataclasses import dataclass, field
import math
from numbers import Integral, Real
import time
from typing import Any

from core.models import JointType, Skeleton
from core.perception.base import PerceptionResult, PoseStatus, ReadinessState
from core.perception.identity import IdentityState
from core.perception.quality import IDENTITY_JOINTS, validate_landmarks


SEMANTIC_JOINTS = {
    "nose": JointType.NOSE,
    "left_shoulder": JointType.LEFT_SHOULDER,
    "right_shoulder": JointType.RIGHT_SHOULDER,
    "left_elbow": JointType.LEFT_ELBOW,
    "right_elbow": JointType.RIGHT_ELBOW,
    "left_wrist": JointType.LEFT_WRIST,
    "right_wrist": JointType.RIGHT_WRIST,
    "left_hip": JointType.LEFT_HIP,
    "right_hip": JointType.RIGHT_HIP,
    "left_knee": JointType.LEFT_KNEE,
    "right_knee": JointType.RIGHT_KNEE,
    "left_ankle": JointType.LEFT_ANKLE,
    "right_ankle": JointType.RIGHT_ANKLE,
}


@dataclass
class AdaptedPose:
    """Canonical pixel-space candidate with native scores kept for diagnostics."""

    skeleton: Skeleton
    keypoints: dict[str, tuple[float, float, float]]
    person_confidence: float | None = None
    native_confidence: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_skeleton(
        cls,
        skeleton: Skeleton | None,
        width: int,
        height: int,
        person_confidence: float | None = None,
        native_source: str = "joint_visibility",
    ) -> "AdaptedPose | None":
        if skeleton is None or skeleton.joint_count() == 0:
            return None

        keypoints = {}
        native_confidence = {"source": native_source, "joints": {}}
        for name, joint_type in SEMANTIC_JOINTS.items():
            joint = skeleton.get_joint(joint_type)
            if joint is None:
                continue
            score = float(joint.visibility)
            keypoints[name] = (joint.x * width, joint.y * height, score)
            native_confidence["joints"][name] = {
                "visibility": joint.visibility,
                "confidence": joint.confidence,
            }

        # Revaliv consumers use visibility. Populate confidence consistently while
        # retaining both original MediaPipe fields in native_confidence above.
        for joint in skeleton.joints.values():
            joint.confidence = joint.visibility

        return cls(
            skeleton=skeleton,
            keypoints=keypoints,
            person_confidence=person_confidence,
            native_confidence=native_confidence,
        )


class ExerciseReadiness:
    """Applies common quality, calibration, and temporal identity decisions."""

    def __init__(self, identity_state: IdentityState | None = None):
        self.identity_state = identity_state or IdentityState()

    @property
    def calibration_status(self) -> dict[str, Any]:
        return self.identity_state.calibration_status

    def begin_calibration(self, side: str) -> None:
        self.identity_state.begin_calibration(side)

    def reset_calibration(self) -> None:
        """Clear identity/calibration history using the existing state reset."""
        self.identity_state.reset()

    def side_mismatch(self, exercise_side: str | None) -> bool:
        return (
            exercise_side is not None
            and self.identity_state.calibration_side
            != exercise_side.strip().lower()
        )

    def reject_side_mismatch(
        self, *, backend: str, timestamp: float, frame_number: int,
        exercise_side: str | None, diagnostics: dict[str, Any] | None = None,
    ) -> PerceptionResult:
        common = dict(diagnostics or {})
        common.update({
            "reason": "calibration_side_mismatch",
            "rejection_category": "identity_ambiguity",
            "calibration_side": self.identity_state.calibration_side,
            "exercise_side": exercise_side,
        })
        return self._result(
            None, ReadinessState.IDENTITY_AMBIGUOUS, PoseStatus.INVALID,
            backend, timestamp, frame_number,
            {"accepted": False, "rejection_category": "identity_ambiguity",
             "reasons": ["calibration_side_mismatch"]},
            common,
        )

    def evaluate(
        self,
        candidate: AdaptedPose | None,
        *,
        backend: str,
        timestamp: float,
        frame_number: int,
        width: int,
        height: int,
        exercise_side: str | None,
        diagnostics: dict[str, Any] | None = None,
        performance=None,
    ) -> PerceptionResult:
        common = dict(diagnostics or {})
        timestamp_valid = (
            isinstance(timestamp, Real)
            and not isinstance(timestamp, bool)
            and math.isfinite(float(timestamp))
        )
        frame_valid = (
            isinstance(frame_number, Integral)
            and not isinstance(frame_number, bool)
            and frame_number >= 0
        )
        dimensions_valid = (
            isinstance(width, Integral) and not isinstance(width, bool)
            and isinstance(height, Integral) and not isinstance(height, bool)
            and width > 0 and height > 0
        )
        if not timestamp_valid or not frame_valid or not dimensions_valid:
            reasons = []
            if not timestamp_valid:
                reasons.append("invalid_frame_timestamp")
            if not frame_valid:
                reasons.append("invalid_frame_number")
            if not dimensions_valid:
                reasons.append("invalid_image_dimensions")
            self.identity_state.mark_invalid()
            common.update({
                "reason": ",".join(reasons),
                "rejection_category": "invalid_frame_metadata",
            })
            safe_timestamp = float(timestamp) if timestamp_valid else 0.0
            safe_frame_number = int(frame_number) if frame_valid else 0
            return self._result(
                None, ReadinessState.POOR_QUALITY, PoseStatus.INVALID,
                backend, safe_timestamp, safe_frame_number,
                {
                    "accepted": False,
                    "invalid": True,
                    "rejection_category": "invalid_frame_metadata",
                    "reasons": reasons,
                },
                common,
            )
        if self.side_mismatch(exercise_side):
            return self.reject_side_mismatch(
                backend=backend, timestamp=timestamp, frame_number=frame_number,
                exercise_side=exercise_side, diagnostics=common,
            )
        if candidate is None:
            self.identity_state.mark_invalid()
            common.update({
                "reason": "no_person_candidate",
                "rejection_category": "no_person",
            })
            return self._result(
                None, ReadinessState.NO_PERSON, PoseStatus.INVALID,
                backend, timestamp, frame_number,
                {"accepted": False, "reasons": ["no_person_candidate"]},
                common,
            )

        common["native_confidence"] = candidate.native_confidence
        if candidate.person_confidence is not None:
            common["person_confidence"] = candidate.person_confidence
        quality_started = time.perf_counter()
        quality = validate_landmarks(
            candidate.keypoints,
            candidate.person_confidence,
            width,
            height,
            exercise_side=exercise_side,
        )
        common["raw_semantic_landmarks"] = {
            name: {"x": point[0], "y": point[1], "confidence": point[2]}
            for name, point in candidate.keypoints.items()
        }
        common["required_joint_confidence"] = quality.required_joint_confidence

        if not quality.accepted:
            if quality.invalid:
                self.identity_state.mark_invalid()
            else:
                self.identity_state.reject(reason="quality_gate_ambiguous")
            common.update({
                "reason": ",".join(quality.reasons),
                "rejection_category": quality.category,
                "readiness_quality_ms": (time.perf_counter() - quality_started) * 1000,
            })
            state = (
                ReadinessState.LOW_CONFIDENCE
                if quality.category == "low_confidence"
                else ReadinessState.POOR_QUALITY
            )
            status = PoseStatus.INVALID if quality.invalid else PoseStatus.AMBIGUOUS
            if performance is not None:
                performance.record_stage(
                    "exercise_readiness_quality",
                    common["readiness_quality_ms"] / 1000,
                )
            return self._result(
                None, state, status, backend, timestamp, frame_number,
                {
                    "accepted": False,
                    "invalid": quality.invalid,
                    "rejection_category": quality.category,
                    "reasons": quality.reasons,
                    "required_joint_confidence": quality.required_joint_confidence,
                },
                common,
            )

        if not self.identity_state.is_calibrated:
            calibration_started = time.perf_counter()
            decision = self.identity_state.observe_calibration(
                {name: candidate.keypoints[name][:2] for name in IDENTITY_JOINTS}
            )
            elapsed_ms = (time.perf_counter() - calibration_started) * 1000
            common.update({
                "reason": ",".join(decision.reasons),
                "rejection_category": "identity_calibration_pending",
                "identity_calibration": self.identity_state.calibration_status,
                "readiness_identity_ms": elapsed_ms,
            })
            if performance is not None:
                performance.record_stage("exercise_readiness_identity", elapsed_ms / 1000)
            return self._result(
                None, ReadinessState.CALIBRATION_REQUIRED, PoseStatus.AMBIGUOUS,
                backend, timestamp, frame_number,
                {
                    "accepted": False,
                    "rejection_category": "identity_calibration_pending",
                    "reasons": decision.reasons,
                },
                common,
            )

        quality_elapsed_ms = (time.perf_counter() - quality_started) * 1000
        identity_started = time.perf_counter()
        identity = self.identity_state.assess(
            {name: candidate.keypoints[name][:2] for name in IDENTITY_JOINTS},
            frame_number,
            timestamp,
            width,
            height,
        )
        elapsed_ms = (time.perf_counter() - identity_started) * 1000
        temporal_instability = any(
            "displacement" in reason or "switch" in reason
            for reason in identity.reasons
        )
        identity_category = "temporal_instability" if temporal_instability else "identity_ambiguity"
        common.update({
            "identity_confidence": identity.confidence,
            "identity_assignment": identity.assignment,
            "identity_ambiguous": identity.ambiguous,
            "identity_reasons": identity.reasons,
            "readiness_identity_ms": elapsed_ms,
        })
        if performance is not None:
            performance.record_stage("exercise_readiness_identity", elapsed_ms / 1000)
        if not identity.accepted:
            common.update({
                "reason": ",".join(identity.reasons),
                "rejection_category": identity_category,
            })
            return self._result(
                None, ReadinessState.IDENTITY_AMBIGUOUS, PoseStatus.AMBIGUOUS,
                backend, timestamp, frame_number,
                {
                    "accepted": False,
                    "rejection_category": identity_category,
                    "reasons": identity.reasons,
                    "required_joint_confidence": quality.required_joint_confidence,
                },
                common,
            )

        common.update({
            "reason": "",
            "readiness_quality_ms": quality_elapsed_ms,
            "identity_calibration": self.identity_state.calibration_status,
        })
        for joint in candidate.skeleton.joints.values():
            joint.confidence = joint.visibility
        candidate.skeleton.timestamp = timestamp
        candidate.skeleton.frame_number = frame_number
        if performance is not None:
            performance.record_stage("exercise_readiness_quality", quality_elapsed_ms / 1000)
        return self._result(
            candidate.skeleton, ReadinessState.READY, PoseStatus.VALID,
            backend, timestamp, frame_number,
            {
                "accepted": True,
                "reasons": [],
                "required_joint_confidence": quality.required_joint_confidence,
            },
            common,
            tracking=True,
        )

    @staticmethod
    def _result(
        skeleton,
        state,
        status,
        backend,
        timestamp,
        frame_number,
        quality,
        diagnostics,
        tracking=False,
    ):
        return PerceptionResult(
            skeleton=skeleton,
            status=status,
            backend=backend,
            timestamp=timestamp,
            frame_number=frame_number,
            quality=quality,
            tracking=tracking,
            diagnostics=diagnostics,
            state=state,
        )
