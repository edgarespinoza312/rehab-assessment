"""Selectable pose backends; MediaPipe remains the safe default."""

import logging
import os

from core.perception.base import PerceptionResult, PoseStatus, ReadinessState
from core.perception.readiness import AdaptedPose, ExerciseReadiness
from core.perception.mediapipe_backend import MediaPipeBackend
from core.perception.yolo_tensorrt_backend import YoloTensorRTBackend


logger = logging.getLogger(__name__)

VALID_BACKENDS = {"mediapipe", "gpu", "yolo"}


def selected_backend_name(environ=None):
    environment = os.environ if environ is None else environ
    requested = environment.get("REVALIV_PERCEPTION_BACKEND", "mediapipe")
    normalized = requested.strip().lower()
    if normalized not in VALID_BACKENDS:
        logger.warning(
            "Unknown REVALIV_PERCEPTION_BACKEND=%r; using MediaPipe",
            requested,
        )
        return "mediapipe"
    return normalized


def create_perception_backend(
    backend_name=None,
    environ=None,
    mediapipe_factory=MediaPipeBackend,
    yolo_factory=YoloTensorRTBackend,
):
    selected = backend_name or selected_backend_name(environ)
    if selected == "yolo":
        return yolo_factory()
    if selected == "gpu":
        return yolo_factory(backend_name="gpu")
    return mediapipe_factory()


__all__ = [
    "AdaptedPose",
    "ExerciseReadiness",
    "MediaPipeBackend",
    "PerceptionResult",
    "PoseStatus",
    "ReadinessState",
    "YoloTensorRTBackend",
    "create_perception_backend",
    "selected_backend_name",
]
