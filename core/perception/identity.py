"""Conservative temporal check for YOLO semantic-side discontinuities."""

from dataclasses import dataclass, field
import math


@dataclass
class IdentityDecision:
    accepted: bool
    confidence: float
    ambiguous: bool
    assignment: tuple[int, int, int] | None
    reasons: list[str] = field(default_factory=list)


@dataclass
class IdentityState:
    """Requires a side-specific movement calibration before temporal tracking."""

    bootstrap_frames: int = 3
    max_joint_displacement_fraction: float = 0.15
    calibration_frames: int = 10
    calibration_baseline_frames: int = 3
    calibration_return_frames: int = 3
    calibration_min_angle_change_degrees: float = 20.0
    calibration_still_angle_tolerance_degrees: float = 10.0
    calibration_stable_angle_tolerance_degrees: float = 12.0
    calibration_side: str | None = None
    calibrated_side: str | None = None
    calibration_stage: str = "required"
    calibration_samples: list[tuple[float, float]] = field(default_factory=list)
    calibration_matching_frames: int = 0
    calibration_returning_frames: int = 0
    calibration_baseline: tuple[float, float] | None = None
    calibration_reason: str = "calibration_required"
    ordering_samples: list[tuple[int, int, int]] = field(default_factory=list)
    established_assignment: tuple[int, int, int] | None = None
    previous_accepted: dict[str, tuple[float, float]] = field(default_factory=dict)
    previous_frame_number: int | None = None
    previous_timestamp: float | None = None
    consecutive_ambiguous_frames: int = 0
    consecutive_valid_frames: int = 0

    @property
    def is_calibrated(self) -> bool:
        return (
            self.calibration_stage == "ready"
            and self.calibrated_side is not None
            and self.calibrated_side == self.calibration_side
        )

    @property
    def calibration_status(self) -> dict:
        side = self.calibration_side
        messages = {
            "required": "Start an assessment to calibrate anatomical side identity.",
            "baseline": "Keep both arms still briefly to establish a baseline.",
            "movement": (
                f"Move only your {side} arm through a small, comfortable elbow bend."
                if side
                else "Exercise side is unavailable; identity calibration cannot start."
            ),
            "confirming": (
                f"Hold the {side} arm bend steadily "
                f"({self.calibration_matching_frames}/{self.calibration_frames})."
                if side
                else "Identity calibration is unavailable."
            ),
            "return": (
                f"Side confirmed. Return your {side} arm to its starting position."
                if side
                else "Identity calibration is unavailable."
            ),
            "ready": (
                f"Anatomical identity calibrated for the {side} side."
                if side
                else "Anatomical identity calibrated."
            ),
        }
        return {
            "stage": self.calibration_stage,
            "side": side,
            "calibrated": self.is_calibrated,
            "matching_frames": self.calibration_matching_frames,
            "required_frames": self.calibration_frames,
            "message": messages.get(
                self.calibration_stage,
                "Anatomical identity calibration is required.",
            ),
            "reason": self.calibration_reason,
        }

    @staticmethod
    def _elbow_angle(
        shoulder: tuple[float, float],
        elbow: tuple[float, float],
        wrist: tuple[float, float],
    ) -> float:
        vector_a = (shoulder[0] - elbow[0], shoulder[1] - elbow[1])
        vector_b = (wrist[0] - elbow[0], wrist[1] - elbow[1])
        magnitude_a = math.hypot(*vector_a)
        magnitude_b = math.hypot(*vector_b)
        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0
        cosine = (
            vector_a[0] * vector_b[0] + vector_a[1] * vector_b[1]
        ) / (magnitude_a * magnitude_b)
        return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))

    def begin_calibration(self, side: str):
        normalized = side.strip().lower()
        if normalized not in {"left", "right"}:
            raise ValueError("Calibration side must be 'left' or 'right'")
        self.reset()
        self.calibration_side = normalized
        self.calibration_stage = "baseline"
        self.calibration_reason = "baseline_required"

    @staticmethod
    def _order(left_x: float, right_x: float) -> int:
        if left_x == right_x:
            return 0
        return 1 if left_x > right_x else -1

    def reset(self):
        self.calibration_side = None
        self.calibrated_side = None
        self.calibration_stage = "required"
        self.calibration_samples.clear()
        self.calibration_matching_frames = 0
        self.calibration_returning_frames = 0
        self.calibration_baseline = None
        self.calibration_reason = "calibration_required"
        self.ordering_samples.clear()
        self.established_assignment = None
        self.previous_accepted.clear()
        self.previous_frame_number = None
        self.previous_timestamp = None
        self.consecutive_ambiguous_frames = 0
        self.consecutive_valid_frames = 0

    def reject(self, assignment=None, reason="identity_ambiguous"):
        self.consecutive_ambiguous_frames += 1
        self.consecutive_valid_frames = 0
        if self.calibration_stage == "baseline":
            self.calibration_samples.clear()
        elif self.calibration_stage == "confirming":
            self.calibration_matching_frames = 0
            self.calibration_stage = "movement"
        elif self.calibration_stage == "return":
            self.calibration_returning_frames = 0
        self.calibration_reason = reason
        return IdentityDecision(
            accepted=False,
            confidence=0.0,
            ambiguous=True,
            assignment=assignment,
            reasons=[reason],
        )

    def mark_invalid(self):
        self.consecutive_ambiguous_frames = 0
        self.consecutive_valid_frames = 0
        if self.calibration_stage == "baseline":
            self.calibration_samples.clear()
        elif self.calibration_stage == "confirming":
            self.calibration_matching_frames = 0
            self.calibration_stage = "movement"
        elif self.calibration_stage == "return":
            self.calibration_returning_frames = 0

    def observe_calibration(
        self,
        landmarks: dict[str, tuple[float, float]],
    ) -> IdentityDecision:
        side = self.calibration_side
        if side not in {"left", "right"}:
            self.calibration_reason = "calibration_required"
            return self.reject(reason=self.calibration_reason)

        other_side = "right" if side == "left" else "left"
        try:
            active_angle = self._elbow_angle(
                landmarks[f"{side}_shoulder"],
                landmarks[f"{side}_elbow"],
                landmarks[f"{side}_wrist"],
            )
            other_angle = self._elbow_angle(
                landmarks[f"{other_side}_shoulder"],
                landmarks[f"{other_side}_elbow"],
                landmarks[f"{other_side}_wrist"],
            )
        except (KeyError, TypeError, IndexError):
            self.calibration_reason = "insufficient_calibration_landmarks"
            return self.reject(reason=self.calibration_reason)

        current = (active_angle, other_angle)
        if self.calibration_stage == "baseline":
            if self.calibration_samples and any(
                abs(current[index] - self.calibration_samples[0][index])
                > self.calibration_stable_angle_tolerance_degrees
                for index in (0, 1)
            ):
                self.calibration_samples.clear()
            self.calibration_samples.append(current)
            if len(self.calibration_samples) >= self.calibration_baseline_frames:
                self.calibration_baseline = tuple(
                    sum(sample[index] for sample in self.calibration_samples)
                    / len(self.calibration_samples)
                    for index in (0, 1)
                )
                self.calibration_stage = "movement"
                self.calibration_reason = "named_side_movement_required"
            else:
                self.calibration_reason = "baseline_required"
            return self._calibration_pending()

        if self.calibration_stage in {"movement", "confirming"}:
            if self.calibration_baseline is None:
                self.calibration_stage = "baseline"
                self.calibration_reason = "baseline_required"
                return self._calibration_pending()
            active_change = abs(current[0] - self.calibration_baseline[0])
            other_change = abs(current[1] - self.calibration_baseline[1])
            matches = (
                active_change >= self.calibration_min_angle_change_degrees
                and other_change <= self.calibration_still_angle_tolerance_degrees
            )
            if matches:
                self.calibration_matching_frames += 1
                self.calibration_stage = "confirming"
                self.calibration_reason = "confirming_named_side_movement"
                if self.calibration_matching_frames >= self.calibration_frames:
                    self.calibration_stage = "return"
                    self.calibration_returning_frames = 0
                    self.calibration_reason = "return_to_start_required"
            else:
                self.calibration_matching_frames = 0
                self.calibration_stage = "movement"
                self.calibration_reason = (
                    "opposite_side_moved"
                    if other_change > self.calibration_still_angle_tolerance_degrees
                    else "named_side_movement_required"
                )
            return self._calibration_pending()

        if self.calibration_stage == "return":
            baseline = self.calibration_baseline
            if baseline is not None and all(
                abs(current[index] - baseline[index])
                <= self.calibration_still_angle_tolerance_degrees
                for index in (0, 1)
            ):
                self.calibration_returning_frames += 1
                self.calibration_reason = "confirming_return_to_start"
                if self.calibration_returning_frames >= self.calibration_return_frames:
                    self.calibrated_side = side
                    self.calibration_stage = "ready"
                    self.calibration_reason = "calibrated"
            else:
                self.calibration_returning_frames = 0
                self.calibration_reason = "return_to_start_required"
            return self._calibration_pending()

        if self.is_calibrated:
            return IdentityDecision(
                accepted=True,
                confidence=1.0,
                ambiguous=False,
                assignment=self.established_assignment,
                reasons=[],
            )
        self.calibration_reason = "calibration_required"
        return self._calibration_pending()

    def _calibration_pending(self) -> IdentityDecision:
        self.consecutive_ambiguous_frames += 1
        self.consecutive_valid_frames = 0
        return IdentityDecision(
            accepted=False,
            confidence=0.0,
            ambiguous=True,
            assignment=None,
            reasons=[self.calibration_reason],
        )

    def assess(
        self,
        landmarks: dict[str, tuple[float, float]],
        frame_number: int,
        timestamp: float,
        image_width: int,
        image_height: int,
    ) -> IdentityDecision:
        if not self.is_calibrated:
            return self.reject(reason="calibration_required")

        pairs = (
            ("left_shoulder", "right_shoulder"),
            ("left_elbow", "right_elbow"),
            ("left_wrist", "right_wrist"),
        )
        try:
            assignment = tuple(
                self._order(landmarks[left][0], landmarks[right][0])
                for left, right in pairs
            )
        except (KeyError, TypeError, IndexError):
            return self.reject(reason="missing_identity_landmark")
        if 0 in assignment:
            return self.reject(assignment, "overlapping_side_landmarks")
        if len(set(assignment)) != 1:
            return self.reject(assignment, "joint_side_order_disagreement")

        if self.established_assignment is None:
            if self.ordering_samples and assignment != self.ordering_samples[-1]:
                self.ordering_samples.clear()
            self.ordering_samples.append(assignment)
            self.ordering_samples = self.ordering_samples[-self.bootstrap_frames :]
            if len(self.ordering_samples) < self.bootstrap_frames:
                return self.reject(assignment, "identity_bootstrap")
            if len(set(self.ordering_samples)) != 1:
                self.ordering_samples.clear()
                return self.reject(assignment, "unstable_identity_bootstrap")
            self.established_assignment = assignment
        elif assignment != self.established_assignment:
            return self.reject(assignment, "spatial_identity_switch")

        if (
            self.previous_frame_number is not None
            and frame_number == self.previous_frame_number + 1
        ):
            diagonal = math.hypot(image_width, image_height)
            maximum = diagonal * self.max_joint_displacement_fraction
            for name, point in landmarks.items():
                previous = self.previous_accepted.get(name)
                if previous is None:
                    continue
                displacement = math.hypot(point[0] - previous[0], point[1] - previous[1])
                if displacement > maximum:
                    return self.reject(assignment, "extreme_frame_to_frame_displacement")

        self.previous_accepted = dict(landmarks)
        self.previous_frame_number = frame_number
        self.previous_timestamp = timestamp
        self.consecutive_ambiguous_frames = 0
        self.consecutive_valid_frames += 1
        confidence = len(self.ordering_samples) / self.bootstrap_frames
        return IdentityDecision(
            accepted=True,
            confidence=confidence,
            ambiguous=False,
            assignment=assignment,
        )
