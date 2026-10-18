import os
import sys

sys.path.append(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)

import cv2

from core.vision import VisionEngine


def main():
    print("Creating VisionEngine...")
    vision = VisionEngine()

    try:
        vision.start()
        frame = vision.get_frame()
        cv2.imwrite("test_frame.jpg", frame)
    finally:
        vision.stop()

    print("Saved test_frame.jpg")


if __name__ == "__main__":
    main()