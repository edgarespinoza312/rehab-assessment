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

### Password reset email configuration

The forgot-password flow uses a one-hour, single-use reset token. When developing locally without SMTP settings, the reset URL is written to the Flask terminal; this fallback is disabled in production.

For deployment, set these environment variables before starting Flask:

- `REVALIV_ENV=production`
- `REVALIV_PUBLIC_BASE_URL=https://your-public-host.example` (the HTTPS origin serving Revaliv)
- `REVALIV_SMTP_HOST` and `REVALIV_SMTP_PORT` (usually port `587` with STARTTLS)
- `REVALIV_SMTP_USERNAME` and `REVALIV_SMTP_PASSWORD` if your mail provider requires authentication
- `REVALIV_SMTP_FROM` (the verified sender address)
- `REVALIV_SMTP_STARTTLS=1` for STARTTLS, or `REVALIV_SMTP_USE_SSL=1` for implicit TLS (commonly port `465`)

Production must use a stable `REVALIV_SECRET_KEY` as already required by the application. Do not put SMTP credentials in source control.

For automated tests, install the development dependencies (including pytest) and use an isolated SQLite database:

```bash
python -m pip install -r requirements-dev.txt
```

**Linux / Jetson**
```bash
REVALIV_DATABASE_URI=sqlite:// python -m pytest -q
```

**PowerShell**
```powershell
$env:REVALIV_DATABASE_URI = "sqlite://"
python -m pytest -q
Remove-Item Env:REVALIV_DATABASE_URI
```

The tests use an isolated in-memory SQLite database and do not require a camera. Keep the development and runtime virtual environments activated when running these commands.

---


### Initial administrator setup

A fresh installation has no administrator account by default. Create the first administrator from a trusted local terminal after installing the project dependencies and activating the intended virtual environment:

```bash
python -m flask --app dashboard.app bootstrap-admin
```

The command prompts for a display name, email address, and password (with hidden password input and confirmation). It uses the application's configured database and existing password hashing/account-provisioning logic. It refuses to create another administrator if an account with the `ADMIN` role already exists. Do not expose this command through a public web route or run it against an unintended database. Once the first administrator exists, sign in through Revaliv and create clinician accounts from **Account management**.

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
