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

    def __init__(self, camera_index: int = 1):
        self.camera_index = camera_index
        self.camera = None

    def start(self):
        """Initializes the webcam."""

        self.camera = cv2.VideoCapture(self.camera_index)
        
        self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.camera.set(cv2.CAP_PROP_FPS, 30)

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