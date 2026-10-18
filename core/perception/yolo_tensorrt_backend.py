"""Experimental YOLOv8-pose TensorRT backend; never falls back to MediaPipe."""

from __future__ import annotations

import ctypes
import ctypes.util
from collections import Counter, deque
from dataclasses import dataclass
import logging
import math
import os
from pathlib import Path
import time

import cv2
import numpy as np

from core.models import Joint, JointType, Skeleton
from core.perception.base import PerceptionResult, PoseStatus, ReadinessState
from core.perception.identity import IdentityState
from core.perception.quality import KEYPOINT_CONFIDENCE_THRESHOLD, PERSON_CONFIDENCE_THRESHOLD
from core.perception.readiness import AdaptedPose, ExerciseReadiness


logger = logging.getLogger(__name__)

DEFAULT_ENGINE_PATH = "/tmp/revaliv-yolov8-export/yolov8n-pose_fp16.engine"
INPUT_SHAPE = (1, 3, 640, 640)
OUTPUT_SHAPE = (1, 56, 8400)
LETTERBOX_COLOR = (114, 114, 114)
PERCEPTION_NAME = "gpu"

COCO_KEYPOINTS = (
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
)
JOINT_MAP = {
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


@dataclass(frozen=True)
class LetterboxInfo:
    original_width: int
    original_height: int
    resized_width: int
    resized_height: int
    scale: float
    padding_left: int
    padding_top: int
    padding_right: int
    padding_bottom: int


def letterbox(
    image: np.ndarray,
    target_width=640,
    target_height=640,
    output_buffer: np.ndarray | None = None,
):
    if not isinstance(image, np.ndarray) or image.ndim != 3 or image.shape[2] != 3:
        raise ValueError("Expected a BGR image with shape (height, width, 3)")
    height, width = image.shape[:2]
    if height <= 0 or width <= 0:
        raise ValueError("Image dimensions must be positive")
    scale = min(target_width / width, target_height / height)
    resized_width = int(round(width * scale))
    resized_height = int(round(height * scale))
    pad_width = target_width - resized_width
    pad_height = target_height - resized_height
    left = int(round(pad_width / 2 - 0.1))
    right = int(round(pad_width / 2 + 0.1))
    top = int(round(pad_height / 2 - 0.1))
    bottom = int(round(pad_height / 2 + 0.1))
    resized = cv2.resize(
        image, (resized_width, resized_height), interpolation=cv2.INTER_LINEAR
    )
    canvas = cv2.copyMakeBorder(
        resized,
        top,
        bottom,
        left,
        right,
        cv2.BORDER_CONSTANT,
        value=LETTERBOX_COLOR,
    )
    if canvas.shape[:2] != (target_height, target_width):
        raise RuntimeError(f"Unexpected letterbox dimensions: {canvas.shape}")
    rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
    tensor_shape = (1, 3, target_height, target_width)
    if output_buffer is None:
        tensor = np.empty(tensor_shape, dtype=np.float32)
    elif output_buffer.shape == tensor_shape and output_buffer.dtype == np.float32:
        tensor = output_buffer
    else:
        raise ValueError(
            f"Unexpected input buffer {output_buffer.shape}/{output_buffer.dtype}"
        )
    np.divide(rgb.transpose(2, 0, 1)[None], 255.0, out=tensor)
    info = LetterboxInfo(
        width,
        height,
        resized_width,
        resized_height,
        scale,
        left,
        top,
        right,
        bottom,
    )
    return tensor, info


def decode_output(output: np.ndarray, info: LetterboxInfo):
    if not isinstance(output, np.ndarray) or output.shape != OUTPUT_SHAPE:
        shape = getattr(output, "shape", None)
        raise ValueError(f"Malformed TensorRT output {shape}; expected {OUTPUT_SHAPE}")
    if output.dtype != np.float32:
        raise ValueError(f"Malformed TensorRT output dtype {output.dtype}; expected float32")
    if not np.isfinite(output).all():
        raise ValueError("TensorRT output contains NaN or infinity")
    scores = output[0, 4, :]
    eligible = np.flatnonzero(scores >= PERSON_CONFIDENCE_THRESHOLD)
    if eligible.size == 0:
        return None
    candidate_index = int(eligible[np.argmax(scores[eligible])])
    person_confidence = float(scores[candidate_index])
    raw_keypoints = output[0, 5:, candidate_index].reshape(17, 3).astype(np.float64)
    raw_keypoints[:, 0] = (raw_keypoints[:, 0] - info.padding_left) / info.scale
    raw_keypoints[:, 1] = (raw_keypoints[:, 1] - info.padding_top) / info.scale
    keypoints = {
        name: tuple(float(value) for value in raw_keypoints[index])
        for index, name in enumerate(COCO_KEYPOINTS)
    }
    bbox = output[0, :4, candidate_index].astype(np.float64)
    center_x, center_y, box_width, box_height = map(float, bbox)
    box = (
        (center_x - box_width / 2 - info.padding_left) / info.scale,
        (center_y - box_height / 2 - info.padding_top) / info.scale,
        (center_x + box_width / 2 - info.padding_left) / info.scale,
        (center_y + box_height / 2 - info.padding_top) / info.scale,
    )
    if not np.isfinite(np.asarray(box)).all():
        raise ValueError("Decoded bounding box contains NaN or infinity")
    return {
        "candidate_index": candidate_index,
        "person_confidence": person_confidence,
        "bbox": tuple(float(value) for value in box),
        "keypoints": keypoints,
    }


def _check_cuda(status, operation):
    if status:
        raise RuntimeError(f"{operation} failed with CUDA status {status}")


class CudaRuntime:
    """Minimal CUDA runtime binding following the validated Phase 2Q adapter."""

    def __init__(self):
        library = ctypes.util.find_library("cudart")
        if not library:
            raise RuntimeError("CUDA runtime library libcudart was not found")
        self.lib = ctypes.CDLL(library)
        self.lib.cudaMalloc.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_size_t]
        self.lib.cudaMalloc.restype = ctypes.c_int
        self.lib.cudaFree.argtypes = [ctypes.c_void_p]
        self.lib.cudaFree.restype = ctypes.c_int
        self.lib.cudaMemcpy.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
        self.lib.cudaMemcpy.restype = ctypes.c_int
        self.lib.cudaDeviceSynchronize.argtypes = []
        self.lib.cudaDeviceSynchronize.restype = ctypes.c_int
        self.lib.cudaGetDeviceCount.argtypes = [ctypes.POINTER(ctypes.c_int)]
        self.lib.cudaGetDeviceCount.restype = ctypes.c_int
        self.lib.cudaGetDevice.argtypes = [ctypes.POINTER(ctypes.c_int)]
        self.lib.cudaGetDevice.restype = ctypes.c_int
        self.lib.cudaRuntimeGetVersion.argtypes = [ctypes.POINTER(ctypes.c_int)]
        self.lib.cudaRuntimeGetVersion.restype = ctypes.c_int
        self.device_count = ctypes.c_int()
        _check_cuda(
            self.lib.cudaGetDeviceCount(ctypes.byref(self.device_count)),
            "cudaGetDeviceCount",
        )
        if self.device_count.value < 1:
            raise RuntimeError("CUDA reports no available GPU devices")
        self.device_index = ctypes.c_int()
        _check_cuda(
            self.lib.cudaGetDevice(ctypes.byref(self.device_index)),
            "cudaGetDevice",
        )
        self.runtime_version = ctypes.c_int()
        _check_cuda(
            self.lib.cudaRuntimeGetVersion(ctypes.byref(self.runtime_version)),
            "cudaRuntimeGetVersion",
        )

    def malloc(self, size):
        pointer = ctypes.c_void_p()
        _check_cuda(self.lib.cudaMalloc(ctypes.byref(pointer), size), "cudaMalloc")
        return pointer

    def copy_to_device(self, destination, source, size):
        started = time.perf_counter()
        _check_cuda(
            self.lib.cudaMemcpy(
                destination, ctypes.c_void_p(source.ctypes.data), size, 1
            ),
            "cudaMemcpy H2D",
        )
        return (time.perf_counter() - started) * 1000

    def copy_to_host(self, destination, source, size):
        started = time.perf_counter()
        _check_cuda(
            self.lib.cudaMemcpy(
                ctypes.c_void_p(destination.ctypes.data), source, size, 2
            ),
            "cudaMemcpy D2H",
        )
        return (time.perf_counter() - started) * 1000

    def free(self, pointer):
        if pointer:
            _check_cuda(self.lib.cudaFree(pointer), "cudaFree")


class TensorRTSession:
    def __init__(self, engine_path: str):
        try:
            import tensorrt as trt
        except ImportError as error:
            raise RuntimeError("TensorRT Python bindings are unavailable") from error

        self.trt = trt
        self.cuda = None
        self.device_input = None
        self.device_output = None
        self.host_input = np.empty(INPUT_SHAPE, dtype=np.float32)
        self.host_output = np.empty(OUTPUT_SHAPE, dtype=np.float32)
        self.runtime = trt.Runtime(trt.Logger(trt.Logger.WARNING))
        engine_bytes = Path(engine_path).read_bytes()
        self.engine = self.runtime.deserialize_cuda_engine(engine_bytes)
        if self.engine is None:
            raise RuntimeError(f"TensorRT failed to deserialize engine {engine_path}")
        self.context = self.engine.create_execution_context()
        if self.context is None:
            raise RuntimeError("TensorRT failed to create an execution context")
        self.bindings = [0] * self.engine.num_bindings
        self.input_index = self.output_index = None
        self.input_nbytes = self.output_nbytes = 0
        for index in range(self.engine.num_bindings):
            shape = tuple(self.engine.get_binding_shape(index))
            dtype = np.dtype(trt.nptype(self.engine.get_binding_dtype(index)))
            if self.engine.binding_is_input(index):
                self.input_index = index
                self.input_nbytes = math.prod(shape) * dtype.itemsize
                if shape != INPUT_SHAPE or dtype != np.dtype(np.float32):
                    raise RuntimeError(
                        f"Unexpected TensorRT input binding: shape={shape}, dtype={dtype}"
                    )
            else:
                self.output_index = index
                self.output_nbytes = math.prod(shape) * dtype.itemsize
                if shape != OUTPUT_SHAPE or dtype != np.dtype(np.float32):
                    raise RuntimeError(
                        f"Unexpected TensorRT output binding: shape={shape}, dtype={dtype}"
                    )
        if (
            self.engine.num_bindings != 2
            or self.input_index is None
            or self.output_index is None
        ):
            raise RuntimeError("Expected exactly one TensorRT input and one output")
        try:
            self.cuda = CudaRuntime()
            self.device_input = self.cuda.malloc(self.input_nbytes)
            self.device_output = self.cuda.malloc(self.output_nbytes)
            self.bindings[self.input_index] = self.device_input.value
            self.bindings[self.output_index] = self.device_output.value
        except Exception:
            self.close()
            raise

    def infer(self, tensor):
        if tensor is not self.host_input:
            np.copyto(self.host_input, tensor)
        h2d_ms = self.cuda.copy_to_device(
            self.device_input, self.host_input, self.input_nbytes
        )
        inference_started = time.perf_counter()
        succeeded = self.context.execute_v2(self.bindings)
        _check_cuda(self.cuda.lib.cudaDeviceSynchronize(), "cudaDeviceSynchronize")
        inference_ms = (time.perf_counter() - inference_started) * 1000
        if not succeeded:
            raise RuntimeError("TensorRT execute_v2 returned false")
        d2h_ms = self.cuda.copy_to_host(
            self.host_output, self.device_output, self.output_nbytes
        )
        return self.host_output, {
            "h2d_ms": h2d_ms,
            "inference_ms": inference_ms,
            "d2h_ms": d2h_ms,
        }

    def close(self):
        if self.cuda is not None:
            for pointer in (self.device_input, self.device_output):
                if pointer:
                    try:
                        self.cuda.free(pointer)
                    finally:
                        if pointer == self.device_input:
                            self.device_input = None
                        else:
                            self.device_output = None


def _midpoint(skeleton, joint_a, joint_b, new_joint):
    first = skeleton.get_joint(joint_a)
    second = skeleton.get_joint(joint_b)
    if first is None or second is None:
        return
    skeleton.add_joint(
        Joint(
            name=new_joint,
            x=(first.x + second.x) / 2,
            y=(first.y + second.y) / 2,
            z=(first.z + second.z) / 2,
            visibility=min(first.visibility, second.visibility),
            confidence=min(first.confidence, second.confidence),
        )
    )


def _copy_joint(skeleton, source, destination):
    joint = skeleton.get_joint(source)
    if joint is None:
        return
    skeleton.add_joint(
        Joint(
            name=destination,
            x=joint.x,
            y=joint.y,
            z=joint.z,
            visibility=joint.visibility,
            confidence=joint.confidence,
        )
    )


def build_skeleton(keypoints, timestamp, frame_number, width, height):
    skeleton = Skeleton(timestamp=timestamp, frame_number=frame_number)
    for name, (x, y, confidence) in keypoints.items():
        joint_type = JOINT_MAP.get(name)
        if (
            joint_type is None
            or confidence < KEYPOINT_CONFIDENCE_THRESHOLD
            or not 0 <= x < width
            or not 0 <= y < height
        ):
            continue
        skeleton.add_joint(
            Joint(
                name=joint_type,
                x=x / width,
                y=y / height,
                confidence=confidence,
                visibility=confidence,
            )
        )
    derived = (
        ("left_shoulder", "left_elbow", "LEFT_UPPER_ARM"),
        ("left_elbow", "left_wrist", "LEFT_FOREARM"),
        ("right_shoulder", "right_elbow", "RIGHT_UPPER_ARM"),
        ("right_elbow", "right_wrist", "RIGHT_FOREARM"),
        ("left_hip", "left_knee", "LEFT_THIGH"),
        ("left_knee", "left_ankle", "LEFT_SHANK"),
        ("right_hip", "right_knee", "RIGHT_THIGH"),
        ("right_knee", "right_ankle", "RIGHT_SHANK"),
    )
    for first_name, second_name, derived_name in derived:
        _midpoint(
            skeleton,
            JOINT_MAP[first_name],
            JOINT_MAP[second_name],
            getattr(JointType, derived_name),
        )
    for source, destination in (
        ("left_wrist", "LEFT_HAND"),
        ("right_wrist", "RIGHT_HAND"),
    ):
        _copy_joint(
            skeleton,
            JOINT_MAP[source],
            getattr(JointType, destination),
        )
    _midpoint(
        skeleton,
        JointType.LEFT_SHOULDER,
        JointType.RIGHT_SHOULDER,
        JointType.SHOULDER_CENTER,
    )
    _midpoint(
        skeleton,
        JointType.LEFT_HIP,
        JointType.RIGHT_HIP,
        JointType.PELVIS_CENTER,
    )
    _midpoint(
        skeleton,
        JointType.SHOULDER_CENTER,
        JointType.PELVIS_CENTER,
        JointType.BODY_CENTER,
    )
    return skeleton


class YoloTensorRTBackend:
    name = "yolo"

    def __init__(
        self,
        engine_path=None,
        session_factory=TensorRTSession,
        identity_state=None,
        backend_name="yolo",
    ):
        if backend_name not in {"gpu", "yolo"}:
            raise ValueError("backend_name must be 'gpu' or the 'yolo' alias")
        self.name = backend_name
        self.engine_path = engine_path or os.environ.get(
            "REVALIV_YOLO_ENGINE", DEFAULT_ENGINE_PATH
        )
        self.readiness = ExerciseReadiness(identity_state or IdentityState())
        self.last_result = None
        self._session = None
        self.available = False
        self.initialization_error = None
        self.inference_count = 0
        self.accepted_frames = 0
        self.rejected_frames = 0
        self.rejection_counts = Counter()
        self.inference_time_samples = deque(maxlen=120)
        self.started_at = time.monotonic()
        if not Path(self.engine_path).is_file():
            self.initialization_error = f"TensorRT engine not found: {self.engine_path}"
        else:
            try:
                self._session = session_factory(self.engine_path)
                self.available = True
            except Exception as error:
                self.initialization_error = str(error)
        if not self.available:
            logger.error("YOLO/TensorRT backend unavailable: %s", self.initialization_error)
        logger.info(
            "Perception backend initialization: %s",
            self.runtime_diagnostics,
        )

    @property
    def identity_state(self):
        return self.readiness.identity_state

    @property
    def runtime_diagnostics(self):
        session = self._session
        cuda = getattr(session, "cuda", None)
        trt = getattr(session, "trt", None)
        return {
            "backend": self.name,
            "delegate": "TensorRT/CUDA",
            "gpu_initialized": self.available,
            "gpu_inference_completed": self.inference_count > 0,
            "engine_path": self.engine_path,
            "initialization_error": self.initialization_error,
            "tensorrt_version": getattr(trt, "__version__", None),
            "cuda_runtime_version": getattr(cuda, "runtime_version", None),
            "cuda_device_index": getattr(cuda, "device_index", None),
            "inference_count": self.inference_count,
            "accepted_frames": self.accepted_frames,
            "rejected_frames": self.rejected_frames,
            "rejection_counts": dict(self.rejection_counts),
            "identity_calibration": self.identity_state.calibration_status,
            "mean_inference_ms": (
                sum(self.inference_time_samples) / len(self.inference_time_samples)
                if self.inference_time_samples
                else None
            ),
            "inference_fps": (
                self.inference_count / max(time.monotonic() - self.started_at, 1e-9)
            ),
        }

    @property
    def calibration_status(self):
        return self.readiness.calibration_status

    def begin_calibration(self, side: str):
        self.readiness.begin_calibration(side)
        self.last_result = None
        logger.info(
            "GPU pose anatomical identity calibration started: %s",
            self.identity_state.calibration_status,
        )

    def reset_calibration(self):
        self.readiness.reset_calibration()
        self.last_result = None

    def _result(
        self,
        frame,
        status,
        timestamp,
        frame_number,
        reason,
        diagnostics=None,
        quality=None,
        total_started=None,
        performance=None,
        state=None,
    ):
        diagnostics = dict(diagnostics or {})
        diagnostics["reason"] = reason
        diagnostics["delegate"] = "TensorRT/CUDA"
        diagnostics["gpu_initialized"] = self.available
        diagnostics["gpu_inference_completed"] = self.inference_count > 0
        total_ms = (
            (time.perf_counter() - total_started) * 1000
            if total_started is not None
            else diagnostics.get("total_perception_ms")
        )
        if total_ms is not None:
            diagnostics["total_perception_ms"] = total_ms
        if performance is not None:
            for stage, key in (
                ("yolo_preprocessing", "preprocessing_ms"),
                ("yolo_h2d", "h2d_ms"),
                ("yolo_tensorrt_inference", "inference_ms"),
                ("yolo_d2h", "d2h_ms"),
                ("yolo_decode", "decode_ms"),
            ):
                if key in diagnostics:
                    performance.record_stage(stage, diagnostics[key] / 1000)
            if total_ms is not None:
                performance.record_stage("yolo_total_perception", total_ms / 1000)
        skeleton = None
        if frame is None:
            annotated = frame
        else:
            annotated = frame.copy()
        self.last_result = PerceptionResult(
            skeleton=skeleton,
            status=status,
            backend=self.name,
            timestamp=timestamp,
            frame_number=frame_number,
            quality=quality or {},
            tracking=False,
            diagnostics=diagnostics,
            state=state,
        )
        return annotated, None

    def _record_rejection(self, performance, category):
        self.rejected_frames += 1
        self.rejection_counts[category] += 1
        if performance is None:
            return
        performance.increment("gpu_pose_rejected_frames")
        performance.increment(f"gpu_rejected_{category}")

    def process(
        self,
        frame,
        timestamp: float = 0.0,
        frame_number: int = 0,
        performance=None,
        exercise_side: str | None = None,
    ):
        total_started = time.perf_counter()
        if not self.available:
            self.identity_state.mark_invalid()
            self._record_rejection(performance, "backend_unavailable")
            if performance is not None:
                performance.increment("yolo_invalid_frames")
            return self._result(
                frame, PoseStatus.INVALID, timestamp, frame_number,
                "backend_unavailable",
                {"initialization_error": self.initialization_error,
                 "rejection_category": "backend_unavailable"},
                total_started=total_started, performance=performance,
                state=ReadinessState.POOR_QUALITY,
            )
        if self.readiness.side_mismatch(exercise_side):
            self._record_rejection(performance, "calibration_side_mismatch")
            return self._result(
                frame, PoseStatus.INVALID, timestamp, frame_number,
                "calibration_side_mismatch",
                {"rejection_category": "identity_ambiguity",
                 "calibration_side": self.identity_state.calibration_side,
                 "exercise_side": exercise_side},
                total_started=total_started, performance=performance,
                state=ReadinessState.IDENTITY_AMBIGUOUS,
            )
        try:
            preprocess_started = time.perf_counter()
            input_buffer = getattr(self._session, "host_input", None)
            tensor, letterbox_info = letterbox(frame, output_buffer=input_buffer)
            preprocess_ms = (time.perf_counter() - preprocess_started) * 1000
            if performance is not None:
                performance.record_stage("perception_preprocessing", preprocess_ms / 1000)
            output, timings = self._session.infer(tensor)
            if performance is not None:
                performance.record_stage("model_inference", timings["inference_ms"] / 1000)
            self.inference_count += 1
            self.inference_time_samples.append(timings["inference_ms"])
            if performance is not None:
                performance.record_rate_event("gpu_pose_inference")
            decode_started = time.perf_counter()
            decoded = decode_output(output, letterbox_info)
            decode_ms = (time.perf_counter() - decode_started) * 1000
            if decoded is None:
                if performance is not None:
                    performance.record_stage("perception_decoding_adaptation", decode_ms / 1000)
                self.identity_state.mark_invalid()
                self._record_rejection(performance, "no_person")
                if performance is not None:
                    performance.increment("yolo_invalid_frames")
                return self._result(
                    frame, PoseStatus.INVALID, timestamp, frame_number,
                    "no_person_candidate",
                    {"preprocessing_ms": preprocess_ms, "decode_ms": decode_ms,
                     "rejection_category": "no_person", **timings},
                    total_started=total_started, performance=performance,
                    state=ReadinessState.NO_PERSON,
                )

            height, width = frame.shape[:2]
            keypoints = decoded["keypoints"]
            skeleton_started = performance.start_timer() if performance is not None else None
            candidate_skeleton = build_skeleton(
                keypoints, timestamp, frame_number, width, height
            )
            if performance is not None:
                performance.stop_timer("skeleton_construction", skeleton_started)
            adaptation_started = time.perf_counter()
            candidate = AdaptedPose(
                skeleton=candidate_skeleton,
                keypoints=keypoints,
                person_confidence=decoded["person_confidence"],
                native_confidence={
                    "source": "yolov8_pose_keypoint_confidence",
                    "person_confidence": decoded["person_confidence"],
                    "keypoints": {name: point[2] for name, point in keypoints.items()},
                },
            )
            adaptation_ms = (time.perf_counter() - adaptation_started) * 1000
            if performance is not None:
                performance.record_stage(
                    "perception_decoding_adaptation",
                    (decode_ms + adaptation_ms) / 1000,
                )
            common = {
                "preprocessing_ms": preprocess_ms,
                "decode_ms": decode_ms,
                **timings,
                "candidate_index": decoded["candidate_index"],
                "bbox": decoded["bbox"],
                "spatial_side_order": {
                    joint: (
                        "semantic_left_x_greater"
                        if keypoints[f"left_{joint}"][0] > keypoints[f"right_{joint}"][0]
                        else "semantic_left_x_less"
                        if keypoints[f"left_{joint}"][0] < keypoints[f"right_{joint}"][0]
                        else "overlap"
                    )
                    for joint in ("shoulder", "elbow", "wrist")
                },
            }
            # Retain the established TensorRT diagnostic aggregates while
            # keeping the actual accept/reject decision in ExerciseReadiness.
            if performance is not None:
                performance.increment(
                    "yolo_selected_person_confidence_milli",
                    int(decoded["person_confidence"] * 1000),
                )
            readiness_started = performance.start_timer() if performance is not None else None
            result = self.readiness.evaluate(
                candidate, backend=self.name, timestamp=timestamp,
                frame_number=frame_number, width=width, height=height,
                exercise_side=exercise_side, diagnostics=common,
                performance=performance,
            )
            if performance is not None:
                performance.stop_timer("exercise_readiness", readiness_started)
            self.last_result = result
            if performance is not None:
                required_confidences = [
                    value for value in result.quality.get(
                        "required_joint_confidence", {}
                    ).values() if value is not None
                ]
                performance.increment(
                    "yolo_required_joint_confidence_milli_sum",
                    int(sum(required_confidences) * 1000),
                )
                performance.increment(
                    "yolo_required_joint_confidence_samples",
                    len(required_confidences),
                )
            category = result.diagnostics.get("rejection_category")
            if not result.pose_valid:
                counter_category = (
                    "identity" if category == "identity_ambiguity" else category
                )
                self._record_rejection(
                    performance, counter_category or result.state.value
                )
                if result.state in (ReadinessState.LOW_CONFIDENCE, ReadinessState.POOR_QUALITY):
                    if performance is not None:
                        performance.increment(
                            "yolo_invalid_frames"
                            if result.quality.get("invalid")
                            else "yolo_ambiguous_frames"
                        )
                        performance.increment("yolo_quality_rejections")
                elif result.state is ReadinessState.CALIBRATION_REQUIRED:
                    pass
                elif result.state is ReadinessState.IDENTITY_AMBIGUOUS:
                    if performance is not None:
                        performance.increment("yolo_ambiguous_frames")
                        performance.increment("yolo_identity_rejections")
                if performance is not None and result.state is not ReadinessState.NO_PERSON:
                    elapsed = (
                        result.diagnostics.get("readiness_identity_ms", 0)
                        + result.diagnostics.get("readiness_quality_ms", 0)
                    )
                    performance.record_stage("gpu_identity_quality", elapsed / 1000)
                annotated = frame.copy()
                return annotated, None

            annotated = frame.copy()
            self._draw_skeleton(annotated, result.skeleton, decoded["person_confidence"])
            if performance is not None:
                elapsed = (
                    result.diagnostics.get("readiness_identity_ms", 0)
                    + result.diagnostics.get("readiness_quality_ms", 0)
                )
                performance.record_stage("gpu_identity_quality", elapsed / 1000)
            total_ms = (time.perf_counter() - total_started) * 1000
            result.diagnostics["total_perception_ms"] = total_ms
            self.accepted_frames += 1
            if performance is not None:
                performance.increment("yolo_valid_frames")
                performance.increment("gpu_pose_accepted_frames")
                performance.record_stage("yolo_total_perception", total_ms / 1000)
                for stage, key in (
                    ("yolo_preprocessing", "preprocessing_ms"),
                    ("yolo_h2d", "h2d_ms"),
                    ("yolo_tensorrt_inference", "inference_ms"),
                    ("yolo_d2h", "d2h_ms"),
                    ("yolo_decode", "decode_ms"),
                ):
                    performance.record_stage(stage, result.diagnostics[key] / 1000)
            return annotated, result.skeleton
        except Exception as error:
            self.identity_state.mark_invalid()
            logger.exception("YOLO/TensorRT inference failed")
            if performance is not None:
                performance.increment("yolo_inference_failures")
                performance.increment("yolo_invalid_frames")
                self._record_rejection(performance, "inference_failure")
            return self._result(
                frame, PoseStatus.INVALID, timestamp, frame_number,
                "inference_or_decode_failure",
                {"error": str(error), "rejection_category": "inference_failure"},
                total_started=total_started, performance=performance,
                state=ReadinessState.POOR_QUALITY,
            )

    @staticmethod
    def _draw_skeleton(frame, skeleton, person_confidence):
        height, width = frame.shape[:2]
        edges = (
            (JointType.LEFT_SHOULDER, JointType.LEFT_ELBOW),
            (JointType.LEFT_ELBOW, JointType.LEFT_WRIST),
            (JointType.RIGHT_SHOULDER, JointType.RIGHT_ELBOW),
            (JointType.RIGHT_ELBOW, JointType.RIGHT_WRIST),
        )
        for first, second in edges:
            a, b = skeleton.get_joint(first), skeleton.get_joint(second)
            if a is None or b is None:
                continue
            cv2.line(
                frame,
                (round(a.x * width), round(a.y * height)),
                (round(b.x * width), round(b.y * height)),
                (0, 220, 0),
                2,
                cv2.LINE_AA,
            )
        for joint in skeleton.joints.values():
            cv2.circle(
                frame,
                (round(joint.x * width), round(joint.y * height)),
                4,
                (0, 120, 255),
                -1,
                cv2.LINE_AA,
            )
        cv2.putText(
            frame,
            f"YOLO experimental {person_confidence:.2f}",
            (10, 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 220, 0),
            1,
            cv2.LINE_AA,
        )

    def close(self):
        if self._session is not None:
            self._session.close()
            self._session = None
            self.available = False
