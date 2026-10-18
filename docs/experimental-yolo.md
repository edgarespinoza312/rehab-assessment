# Experimental TensorRT GPU perception backend

The legacy MediaPipe `mp.solutions.pose.Pose` path remains Revaliv's
production/default backend and CPU reference. Set
`REVALIV_PERCEPTION_BACKEND=gpu` to opt into the Revaliv GPU backend.
`REVALIV_PERCEPTION_BACKEND=yolo` remains a compatible alias. Neither setting
falls back to MediaPipe if the TensorRT runtime or engine is unavailable.

The GPU backend loads one TensorRT engine and reuses its CUDA device input and
output allocations and host input/output arrays. The current 640x480 letterbox,
color conversion, identity/quality checks, Skeleton construction, biomechanics,
exercise analysis, scoring, overlay, and JPEG/MJPEG stages run on the CPU.
Preprocessing has deliberately not been moved to CUDA: no measurement here
justifies adding that complexity.

## Runtime and engine

On the Jetson installation used for validation, the system interpreter is
`/usr/bin/python3` (Python 3.10), with system TensorRT Python bindings 8.6.2
and CUDA 12.2. The shell's `/home/edgar/.venv/bin/python` does not include
TensorRT; use the system interpreter explicitly for the GPU backend:

```bash
cd /home/edgar/rehab-assessment
REVALIV_PERCEPTION_BACKEND=gpu \
  /usr/bin/python3 -m dashboard.app
```

The engine must be compatible with this Jetson's TensorRT/CUDA runtime and have
one float32 input `[1,3,640,640]` and one float32 raw YOLOv8-Pose output
`[1,56,8400]`, representing COCO-17 landmarks. FP16 refers to engine
computation; the binding contract remains float32. The default engine path is:

```text
/tmp/revaliv-yolov8-export/yolov8n-pose_fp16.engine
```

Override it with `REVALIV_YOLO_ENGINE=/path/to/engine`. Engine files are
external artifacts and must not be committed. The historical engine-generation
tool version and source-checkpoint hash were not recorded, and the engine is
not present at the default path in the current checkout. Do not treat a newly
exported engine as equivalent until its bindings and landmark semantics have
been validated. The expected starting weights are the official
`yolov8n-pose.pt`; exports must be batch 1, 640 input, FP16, raw (no NMS output
plugin), and pass the exact binding checks above.

An export command template for the official checkpoint is:

```bash
yolo export model=yolov8n-pose.pt format=engine imgsz=640 batch=1 \
  half=True device=0 nms=False
```

This template has not been run as part of this phase. Pin the Ultralytics
exporter and checkpoint revision/hash for a reproducible build; those exact
historical provenance details were not recorded. Confirm the generated
bindings match `[1,3,640,640]` and `[1,56,8400]` before using the engine.

## Pose acceptance and downstream behavior

Raw COCO semantic left/right labels are preserved; Revaliv never reassigns
anatomical sides based solely on screen position. A CPU gate requires valid
person confidence, all six shoulder/elbow/wrist identity landmarks, confidence
and bounds checks, and plausible active-arm geometry. Each GPU assessment then
blocks analysis until the patient holds still for a baseline, performs a small
comfortable elbow bend with only the named target side, holds that movement
for 10 matching frames, and returns to the baseline position. The opposite
arm must remain still. This motion calibration, not screen-space ordering,
establishes which semantic side corresponds to the named exercise side. Stable
spatial ordering is used only afterwards as a temporal consistency check,
along with frame-to-frame jump rejection.

Calibration frames and all other rejected frames return no Skeleton and are
excluded from biomechanics, exercise state, repetitions, and scoring. Temporal
state is reset while the completed repetition count is preserved. If the
subject cannot complete or the model cannot unambiguously observe the named
side movement, the GPU path remains blocked rather than guessing. This
calibration is an engineering identity safeguard, not clinically validated
side verification.

## Diagnostics and validation

With `REVALIV_PERF=1`, startup and periodic performance logs report the selected
backend, `TensorRT/CUDA` delegate, GPU initialization state, successful
inference count, TensorRT/CUDA versions and device index, engine path, inference
timing/rate, accepted frames, rejected frames by reason, and pipeline stage
timings/FPS. Initialization failure is logged and frames are rejected without
CPU fallback.

To correlate activity with live inference, use separate terminals:

```bash
tegrastats --interval 1000
```

```bash
REVALIV_PERCEPTION_BACKEND=gpu REVALIV_PERF=1 \
  /usr/bin/python3 -m dashboard.app
```

Only a successful inference run plus concurrent nonzero `GR3D_FREQ` provides
runtime evidence of GPU execution. A backend/API selection or an initialized
TensorRT engine by itself is not evidence that inference occurred.
