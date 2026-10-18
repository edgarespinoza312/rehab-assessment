"""User-facing readiness messages derived from authoritative perception results."""

from core.perception.base import ReadinessState
from core.perception.quality import (
    IDENTITY_JOINTS,
    KEYPOINT_CONFIDENCE_THRESHOLD,
    REQUIRED_ACTIVE_ARM_CONFIDENCE_THRESHOLD,
)


STATE_LABELS = {
    ReadinessState.NO_PERSON.value: "No person detected",
    ReadinessState.LOW_CONFIDENCE.value: "Pose confidence is low",
    ReadinessState.POOR_QUALITY.value: "Pose needs adjustment",
    ReadinessState.CALIBRATION_REQUIRED.value: "Calibration in progress",
    ReadinessState.IDENTITY_AMBIGUOUS.value: "Checking arm identity",
    ReadinessState.READY.value: "Ready",
}


def _calibration_message(calibration, side):
    stage = calibration.get("stage") if calibration else "required"
    side_name = f"{side} " if side else ""
    messages = {
        "required": "Start an assessment to begin side calibration.",
        "baseline": f"Hold still while we establish the {side_name}side baseline.",
        "movement": f"Bend only your {side_name}arm to confirm its side.",
        "confirming": (
            f"Hold the {side_name}arm bend steady "
            f"({calibration.get('matching_frames', 0)}/"
            f"{calibration.get('required_frames', 10)})."
        ),
        "return": f"Return your {side_name}arm to its starting position.",
        "ready": f"Calibration complete for the {side_name}side. Ready.",
    }
    return messages.get(stage, "Hold still while we check your pose.")


def _low_confidence_message(result, active_side):
    landmarks = result.diagnostics.get("raw_semantic_landmarks", {})
    weak = []
    for name in IDENTITY_JOINTS:
        point = landmarks.get(name)
        if not point:
            continue
        confidence = point.get("confidence")
        if confidence is None:
            continue
        threshold = (
            REQUIRED_ACTIVE_ARM_CONFIDENCE_THRESHOLD
            if active_side and name.startswith(f"{active_side}_")
            else KEYPOINT_CONFIDENCE_THRESHOLD
        )
        if confidence < threshold:
            weak.append(name.replace("_", " "))

    if weak:
        if len(weak) == 1:
            joints = weak[0]
        elif len(weak) == 2:
            joints = " and ".join(weak)
        else:
            joints = ", ".join(weak[:-1]) + f", and {weak[-1]}"
        return f"Keep your {joints} visible to the camera."
    return "Face the camera and hold still while the pose is detected."


def readiness_presentation(
    result,
    *,
    calibration=None,
    active_side=None,
    assessment_active=True,
):
    """Return a small, backend-neutral status object for UI and frame overlay."""
    side = active_side.lower() if isinstance(active_side, str) else None
    display_label = None
    if side not in {"left", "right"}:
        side = None

    if not assessment_active:
        state = ReadinessState.CALIBRATION_REQUIRED.value
        message = "Start an assessment to begin pose and side calibration."
        display_label = "Assessment not started"
        valid = tracking = False
    elif result is None:
        state = ReadinessState.CALIBRATION_REQUIRED.value
        message = _calibration_message(calibration, side)
        valid = tracking = False
    else:
        state = getattr(result.state, "value", result.state)
        state = state or ReadinessState.POOR_QUALITY.value
        calibration_pending = bool(
            calibration
            and calibration.get("calibrated") is False
            and calibration.get("stage") not in {None, "required"}
        )
        if state == ReadinessState.READY.value and calibration_pending:
            # A previous accepted result can remain cached between assessment start
            # and the first new frame. Never present it as ready during calibration.
            state = ReadinessState.CALIBRATION_REQUIRED.value
        valid = bool(result.pose_valid) and state == ReadinessState.READY.value
        tracking = bool(result.tracking and valid)

        if state == ReadinessState.READY.value:
            message = f"Ready for the {side} arm." if side else "Pose is ready for exercise."
        elif state == ReadinessState.NO_PERSON.value:
            message = "Stand where your upper body and arms are visible."
        elif state == ReadinessState.LOW_CONFIDENCE.value:
            message = _low_confidence_message(result, side)
        elif state == ReadinessState.POOR_QUALITY.value:
            reasons = result.quality.get("reasons", ())
            if any("out_of_bounds" in reason or "missing_identity" in reason for reason in reasons):
                message = "Keep both shoulders and your active arm fully in view."
            elif any("implausible_" in reason for reason in reasons):
                message = "Keep your active arm unobstructed and fully in view."
            else:
                message = "Face the camera and keep your shoulders and active arm visible."
        elif state == ReadinessState.CALIBRATION_REQUIRED.value:
            message = _calibration_message(calibration, side)
        elif state == ReadinessState.IDENTITY_AMBIGUOUS.value:
            reasons = result.diagnostics.get("identity_reasons", ())
            if "calibration_side_mismatch" in reasons or result.diagnostics.get("reason") == "calibration_side_mismatch":
                message = "The exercise side changed. Restart the assessment to calibrate it."
            else:
                message = "Hold still while we confirm left and right arm identity."
        else:
            state = ReadinessState.POOR_QUALITY.value
            message = "Hold still while we check your pose."
            valid = tracking = False

    return {
        "state": state,
        "label": display_label or STATE_LABELS.get(state, "Pose status"),
        "message": message,
        "active_side": side,
        "valid": valid,
        "tracking": tracking,
        "calibration_progress": (
            {
                "stage": calibration.get("stage"),
                "matching_frames": calibration.get("matching_frames", 0),
                "required_frames": calibration.get("required_frames", 10),
            }
            if calibration else None
        ),
    }
