import unittest
from unittest.mock import patch

from dashboard.app import _ensure_camera_started, vision


class CameraStartupTests(unittest.TestCase):
    def test_camera_is_initialized_on_demand_when_missing(self):
        with patch.object(vision, "camera", None), patch.object(
            vision, "start"
        ) as start:
            _ensure_camera_started()
            start.assert_called_once_with()

    def test_camera_is_not_reinitialized_when_already_open(self):
        camera = object()
        with patch.object(vision, "camera", camera), patch.object(
            vision, "start"
        ) as start:
            _ensure_camera_started()
            start.assert_not_called()

    def test_camera_start_failure_propagates_to_stream_handler(self):
        with patch.object(vision, "camera", None), patch.object(
            vision, "start", side_effect=RuntimeError("camera unavailable")
        ):
            with self.assertRaisesRegex(RuntimeError, "camera unavailable"):
                _ensure_camera_started()


if __name__ == "__main__":
    unittest.main()
