import unittest
from unittest.mock import Mock, patch

from core.vision import VisionEngine


class VisionStartupTests(unittest.TestCase):
    def test_configuration_failure_releases_partial_camera_handle(self):
        camera = Mock()
        camera.set.side_effect = RuntimeError("camera configuration failed")
        engine = VisionEngine()

        with patch("core.vision.cv2.VideoCapture", return_value=camera):
            with self.assertRaisesRegex(RuntimeError, "camera configuration failed"):
                engine.start()

        self.assertIsNone(engine.camera)
        camera.release.assert_called_once_with()

    def test_unopened_camera_is_released_and_handle_is_cleared(self):
        camera = Mock()
        camera.isOpened.return_value = False
        engine = VisionEngine()

        with patch("core.vision.cv2.VideoCapture", return_value=camera):
            with self.assertRaisesRegex(RuntimeError, "Unable to open webcam"):
                engine.start()

        self.assertIsNone(engine.camera)
        camera.release.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
