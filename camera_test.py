import cv2

for i in [0, 1]:
    print(f"\nTesting camera {i}")

    cap = cv2.VideoCapture(i)

    print("Opened:", cap.isOpened())

    if cap.isOpened():
        ret, frame = cap.read()

        print("Read:", ret)

        if ret:
            print("Shape:", frame.shape)

    cap.release()