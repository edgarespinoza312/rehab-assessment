# Rehab Assessment

A real-time AI-powered rehabilitation assessment system built on the NVIDIA Jetson Orin Nano.

This project uses computer vision and human pose estimation to analyze rehabilitation exercises in real time. By extracting skeletal keypoints from a live camera feed, the system evaluates movement quality and provides immediate performance feedback without requiring wearable sensors.

---
## Demo

https://drive.google.com/file/d/1iApZj66ajdM0dbQ_WPKHrKvRF8sHPyiU/view?usp=sharing

---

## Overview

Traditional rehabilitation often depends on in-person observation by clinicians, making continuous assessment difficult outside of clinical settings.

This project demonstrates how edge AI and pose estimation can be combined to create an accessible rehabilitation assessment tool capable of:

- Detecting human body landmarks
- Tracking joint movement in real time
- Evaluating exercise execution
- Providing immediate visual feedback
- Running entirely on-device using NVIDIA Jetson hardware

---

## Features

- Real-time webcam processing
- Human pose estimation
- Skeletal visualization
- Exercise movement analysis
- Lightweight edge deployment
- Modular software architecture

---

## Hardware

- NVIDIA Jetson Orin Nano
- USB Camera
- Monitor or HDMI Display

---

## Software Stack

- Python
- OpenCV
- MediaPipe Pose
- NumPy
- NVIDIA Jetson Linux

---

## Project Structure

```
rehab-assessment/
│
├── app.py                 # Main application
├── vision.py              # Camera interface
├── pose.py                # Pose estimation pipeline
├── assessment.py          # Exercise evaluation logic
├── utils.py               # Helper functions
├── requirements.txt
└── README.md
```

*(Directory structure may vary as development continues.)*

---

## Installation

Clone the repository

```bash
git clone https://github.com/edgarespinoza312/rehab-assessment.git
cd rehab-assessment
```

Create a virtual environment

```bash
python -m venv .venv
```

Activate the environment

**Windows**

```bash
.venv\Scripts\activate
```

**Linux**

```bash
source .venv/bin/activate
```

Install dependencies

```bash
pip install -r requirements.txt
```

---

## Running

Start the application with

```bash
python -m dashboard.app
```

The application will:

1. Open the connected camera
2. Detect the user's pose
3. Estimate body landmarks
4. Analyze movement quality
5. Display annotated video in real time

---

## How It Works

```
Camera
   │
   ▼
Video Frame
   │
   ▼
Pose Estimation
   │
   ▼
Skeleton Extraction
   │
   ▼
Movement Analysis
   │
   ▼
Performance Assessment
   │
   ▼
Visual Feedback
```

---

## Applications

This project demonstrates AI-assisted rehabilitation technologies suitable for:

- Physical therapy
- Stroke rehabilitation
- Home exercise monitoring
- Human movement analysis
- Edge AI research
- Computer vision education

---

## Future Improvements

- Multi-exercise recognition
- Repetition counting
- Range-of-motion analysis
- Joint angle measurements
- Performance scoring
- Session history
- Progress tracking
- Machine learning–based assessment models
- Cloud dashboard integration

---

## Disclaimer

This project is intended for educational and research purposes only.

It is **not** a medical device and should not be used to diagnose, monitor, or treat medical conditions without the supervision of qualified healthcare professionals.

---

## Author

**Edgar Espinoza**

GitHub: https://github.com/edgarespinoza312

---

## License

This project is licensed under the MIT License.
