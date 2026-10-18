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
├── core/                  # Vision, perception, biomechanics, exercises, workouts
├── dashboard/
│   ├── app.py              # Flask application and routes
│   ├── config.py           # Session and database configuration
│   ├── models/             # SQLAlchemy models
│   ├── services/           # Authentication, authorization, persistence
│   ├── templates/          # HTML templates
│   └── static/             # Front-end assets
├── migrations/             # Database migrations
├── tests/                  # Automated tests
├── requirements.txt
└── README.md
```

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

From the repository root, start the Flask application with:

```bash
python -m flask --app dashboard.app run --host 127.0.0.1 --port 5000
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000).

The web server does not need to open the camera during startup. The camera is initialized when an authorized assessment requests the video stream. If no camera is available, the rest of the web interface can still load; the video-stream request returns a service-unavailable response.

For automated tests, use an isolated SQLite database:

```bash
REVALIV_DATABASE_URI=sqlite:// python -m pytest -q
```

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
