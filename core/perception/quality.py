"""Named, conservative pose quality gates shared by perception backends.

These gates deliberately fail closed: malformed dimensions or landmarks are
rejected as invalid input, while low-confidence observations are rejected
without allowing them into assessment scoring.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
import math
from numbers import Integral, Real


PERSON_CONFIDENCE_THRESHOLD = 0.25
KEYPOINT_CONFIDENCE_THRESHOLD = 0.50
REQUIRED_ACTIVE_ARM_CONFIDENCE_THRESHOLD = 0.65
REQUIRED_RIGHT_ARM_CONFIDENCE_THRESHOLD = REQUIRED_ACTIVE_ARM_CONFIDENCE_THRESHOLD
MINIMUM_LIMB_LENGTH_PIXELS = 8.0
MAXIMUM_LIMB_LENGTH_IMAGE_DIAGONAL_FRACTION = 0.65

IDENTITY_JOINTS = (
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
)


@dataclass
class QualityDecision:
    accepted: bool
    invalid: bool = False
    reasons: list[str] = field(default_factory=list)
    required_joint_confidence: dict[str, float | None] = field(default_factory=dict)
    category: str | None = None


def _finite_real(value) -> bool:
    """Whether a value is a finite real number; booleans are not measurements."""
    return (
        isinstance(value, Real)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _reject(reason: str, category: str, *, invalid: bool = True) -> QualityDecision:
    return QualityDecision(
        accepted=False, invalid=invalid, reasons=[reason], category=category
    )


def validate_landmarks(
    keypoints: dict[str, tuple[float, float, float]],
    person_confidence: float | None,
    width: int,
    height: int,
    exercise_side: str | None = None,
) -> QualityDecision:
    """Validate a candidate pose before any biomechanical scoring.

    invalid=True means the input is malformed or impossible. A low-confidence
    but structurally valid candidate is rejected with invalid=False so callers
    can expose uncertainty rather than interpreting the result as a zero.
    """
    if (
        isinstance(width, bool)
        or not isinstance(width, Integral)
        or isinstance(height, bool)
        or not isinstance(height, Integral)
        or width <= 0
        or height <= 0
    ):
        return _reject("invalid_image_dimensions", "invalid_input")

    if not isinstance(keypoints, Mapping):
        return _reject("invalid_keypoints_container", "invalid_input")
    if not keypoints:
        return _reject(
            "missing_identity_joints:" + ",".join(IDENTITY_JOINTS),
            "insufficient_landmarks",
        )

    if person_confidence is not None:
        if not _finite_real(person_confidence):
            return _reject("non_finite_person_confidence", "low_confidence")
        if float(person_confidence) < PERSON_CONFIDENCE_THRESHOLD:
            return _reject("person_confidence_below_threshold", "low_confidence")

    if exercise_side is not None:
        if not isinstance(exercise_side, str):
            raise ValueError("exercise_side must be 'left', 'right', or None")
        exercise_side = exercise_side.strip().lower()
        if exercise_side not in {"left", "right"}:
            raise ValueError("exercise_side must be 'left', 'right', or None")

    normalized: dict[str, tuple[float, float, float]] = {}
    for name, point in keypoints.items():
        if not isinstance(name, str) or not name:
            return _reject("invalid_landmark_name", "invalid_input")
        if not isinstance(point, (tuple, list)) or len(point) != 3:
            return _reject(f"malformed_landmark:{name}", "invalid_input")
        if not all(_finite_real(value) for value in point):
            return _reject(
                f"non_finite_or_non_numeric_landmark:{name}",
                "insufficient_landmarks",
            )
        x, y, confidence = (float(value) for value in point)
        if name in IDENTITY_JOINTS and (
            not 0.0 <= x < width or not 0.0 <= y < height
        ):
            return _reject(
                f"landmark_out_of_bounds:{name}", "anatomical_implausibility"
            )
        if not 0.0 <= confidence <= 1.0:
            return _reject(
                f"invalid_landmark_confidence:{name}", "low_confidence"
            )
        normalized[name] = (x, y, confidence)

    missing = [name for name in IDENTITY_JOINTS if name not in normalized]
    if missing:
        return _reject(
            "missing_identity_joints:" + ",".join(missing),
            "insufficient_landmarks",
        )

    required_sides = (exercise_side,) if exercise_side else ("left", "right")
    required_joints = tuple(
        f"{side}_{joint}"
        for side in required_sides
        for joint in ("shoulder", "elbow", "wrist")
    )
    required_confidence = {
        name: normalized[name][2] for name in required_joints
    }
    weak = [
        name for name, confidence in required_confidence.items()
        if confidence < REQUIRED_ACTIVE_ARM_CONFIDENCE_THRESHOLD
    ]
    low_identity = [
        name for name in IDENTITY_JOINTS
        if normalized[name][2] < KEYPOINT_CONFIDENCE_THRESHOLD
    ]
    if weak or low_identity:
        return QualityDecision(
            False,
            False,
            ["required_joint_confidence_below_threshold:" +
             ",".join(sorted(set(weak + low_identity)))],
            required_confidence,
            "low_confidence",
        )

    diagonal = math.hypot(width, height)
    max_limb_length = diagonal * MAXIMUM_LIMB_LENGTH_IMAGE_DIAGONAL_FRACTION
    geometry_reasons = []
    for side in required_sides:
        for first, second, label in (
            (f"{side}_shoulder", f"{side}_elbow", f"{side}_upper_arm"),
            (f"{side}_elbow", f"{side}_wrist", f"{side}_forearm"),
        ):
            a, b = normalized[first], normalized[second]
            length = math.hypot(a[0] - b[0], a[1] - b[1])
            if length < MINIMUM_LIMB_LENGTH_PIXELS or length > max_limb_length:
                geometry_reasons.append(f"implausible_{label}_length")
    if geometry_reasons:
        return QualityDecision(
            False,
            False,
            geometry_reasons,
            required_confidence,
            "anatomical_implausibility",
        )

    return QualityDecision(True, required_joint_confidence=required_confidence)
