"""Named, conservative YOLO pose quality gates."""

from dataclasses import dataclass, field
import math


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


def validate_landmarks(
    keypoints: dict[str, tuple[float, float, float]],
    person_confidence: float | None,
    width: int,
    height: int,
    exercise_side: str | None = None,
) -> QualityDecision:
    if person_confidence is not None:
        if not math.isfinite(person_confidence):
            return QualityDecision(
                False, True, ["non_finite_person_confidence"], category="low_confidence"
            )
        if person_confidence < PERSON_CONFIDENCE_THRESHOLD:
            return QualityDecision(
                False, True, ["person_confidence_below_threshold"], category="low_confidence"
            )

    if exercise_side is not None:
        exercise_side = exercise_side.strip().lower()
        if exercise_side not in {"left", "right"}:
            raise ValueError("exercise_side must be 'left', 'right', or None")

    for name, point in keypoints.items():
        if len(point) != 3 or not all(math.isfinite(float(v)) for v in point):
            return QualityDecision(
                False,
                True,
                [f"non_finite_landmark:{name}"],
                category="insufficient_landmarks",
            )
        x, y, confidence = map(float, point)
        if name in IDENTITY_JOINTS and (
            not 0.0 <= x < width or not 0.0 <= y < height
        ):
            return QualityDecision(
                False,
                True,
                [f"landmark_out_of_bounds:{name}"],
                category="anatomical_implausibility",
            )
        if not 0.0 <= confidence <= 1.0:
            return QualityDecision(
                False, True, [f"invalid_landmark_confidence:{name}"],
                category="low_confidence",
            )

    missing = [name for name in IDENTITY_JOINTS if name not in keypoints]
    if missing:
        return QualityDecision(
            False,
            True,
            ["missing_identity_joints:" + ",".join(missing)],
            category="insufficient_landmarks",
        )

    required_sides = (exercise_side,) if exercise_side else ("left", "right")
    required_joints = tuple(
        f"{side}_{joint}"
        for side in required_sides
        for joint in ("shoulder", "elbow", "wrist")
    )
    required_confidence = {
        name: float(keypoints[name][2])
        for name in required_joints
    }
    weak = [
        name
        for name, confidence in required_confidence.items()
        if confidence < REQUIRED_ACTIVE_ARM_CONFIDENCE_THRESHOLD
    ]
    low_identity = [
        name
        for name in IDENTITY_JOINTS
        if float(keypoints[name][2]) < KEYPOINT_CONFIDENCE_THRESHOLD
    ]
    if weak or low_identity:
        return QualityDecision(
            False,
            False,
            ["required_joint_confidence_below_threshold:" + ",".join(sorted(set(weak + low_identity)))],
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
            a, b = keypoints[first], keypoints[second]
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
