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

import cv2


class VisionEngine:
    """
    Provides access to the system webcam.
    """

    # CHANGED: use camera 0 instead of 1
    def __init__(self, camera_index: int = 0):
        self.camera_index = camera_index
        self.camera = None

    def start(self):
        """Initializes the webcam."""

        # CHANGED: force the V4L2 backend
        self.camera = cv2.VideoCapture(
            self.camera_index,
            cv2.CAP_V4L2,
        )

        # CHANGED: request a 1-frame buffer
        self.camera.set(cv2.CAP_PROP_BUFFERSIZE, 1)

        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.camera.set(cv2.CAP_PROP_FPS, 30)

        # CHANGED: print diagnostics
        print("Camera index:", self.camera_index)
        print("Buffer size:", self.camera.get(cv2.CAP_PROP_BUFFERSIZE))

        if not self.camera.isOpened():
            raise RuntimeError("Unable to open webcam.")

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

        if not success:
            raise RuntimeError("Failed to capture frame.")

        return frame

    def stop(self):
        """Releases the webcam."""

        if self.camera is not None:
            self.camera.release()

        cv2.destroyAllWindows()