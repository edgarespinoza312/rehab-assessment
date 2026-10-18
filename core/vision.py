"""
vision.py

Implements the Vision Layer of the rehabilitation assessment system.

Responsibilities
----------------
- Initialize the webcam.
- Capture video frames.
- Return the latest frame.
- Release the webcam cleanly.

This module intentionally performs no image processing,
pose estimation, or assessment.
"""

import logging

import cv2


logger = logging.getLogger(__name__)


class VisionEngine:
    """
    Provides access to the system webcam.
    """

    # CHANGED: use camera 0 instead of 1
    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.camera = None

    def start(self):
        """Initialize the webcam and release a partial handle on any failure."""

        if self.camera is not None:
            previous_camera, self.camera = self.camera, None
            try:
                previous_camera.release()
            except Exception:
                logger.exception("Failed to release the previous camera handle")

        camera = None
        try:
            # Force the V4L2 backend and request a one-frame buffer.
            camera = cv2.VideoCapture(
                self.camera_index,
                cv2.CAP_V4L2,
            )
            self.camera = camera
            camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            camera.set(cv2.CAP_PROP_FPS, 30)

            logger.debug(
                "Camera index %s, buffer size %s",
                self.camera_index,
                camera.get(cv2.CAP_PROP_BUFFERSIZE),
            )

            if not camera.isOpened():
                raise RuntimeError("Unable to open webcam.")
        except Exception:
            self.camera = None
            if camera is not None:
                try:
                    camera.release()
                except Exception:
                    logger.exception("Failed to release camera after startup failure")
            raise

    def get_frame(self):
        """
        Returns the newest frame from the webcam.

        Returns
        -------
        frame : numpy.ndarray
            BGR image from OpenCV.
        """

        if self.camera is None:
            raise RuntimeError("Camera has not been started.")

        success, frame = self.camera.read()

        if not success or frame is None:
            raise RuntimeError("Failed to capture frame.")

        return frame

    def stop(self):
        """Releases the webcam and clears the handle, safely more than once."""

        camera, self.camera = self.camera, None
        if camera is not None:
            try:
                camera.release()
            finally:
                cv2.destroyAllWindows()