# Face Scanner

A face recognition app you can train on yourself, your family, and your friends.
Works on **PC** (CLI + GUI + webcam) and on **Android** (via the bundled HTTP server).

## What it does

- Enroll any number of people from photos or directly from your webcam
- Recognize faces in:
  - a still image
  - a live webcam feed
  - a photo taken or picked on your Android phone
- Add more training photos for the same person at any time — accuracy improves
  the more samples you give it
- Local-only: your face data lives in `data/faces.pkl` on your machine. Nothing
  is uploaded anywhere.

## Project layout

```
face_recognition_app/
├── faceapp/            # Core Python package (database + recognizer + webcam)
├── cli.py              # Command-line entry point
├── gui.py              # Tkinter desktop GUI
├── server.py           # FastAPI server (used by the Android client)
├── requirements.txt
└── android/            # Android (Kotlin) client app
```

## 1. PC setup

The recognizer uses [`face_recognition`](https://github.com/ageitgey/face_recognition),
which depends on `dlib`. On most systems you'll need a C++ toolchain and CMake
installed first.

```bash
# Linux (Debian/Ubuntu)
sudo apt install build-essential cmake libopenblas-dev liblapack-dev libx11-dev

# macOS
brew install cmake

# Windows
# Install "Visual Studio Build Tools" (C++) and CMake, then run the pip step.
```

Then create a virtualenv and install the Python deps:

```bash
cd face_recognition_app
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Train it on yourself (and others)

### Option A — from photos you already have

```bash
python cli.py enroll "Paul" --images ~/Pictures/me/*.jpg
python cli.py enroll "Mum"  --images ~/Pictures/mum/*.jpg
```

You can re-run `enroll` for the same name later to add more photos. The more
varied the angles/lighting, the better.

### Option B — from your webcam

```bash
python cli.py enroll-webcam "Paul" --frames 25
```

A webcam window opens. Press **SPACE** to grab a frame, **q** to stop.

## 3. Recognize faces

```bash
# A picture file
python cli.py recognize ~/Pictures/group_photo.jpg

# Live webcam feed (press q in the OpenCV window to quit)
python cli.py live

# List / rename / delete enrolled people
python cli.py list
python cli.py rename <person_id> "New Name"
python cli.py delete <person_id>
```

## 4. Desktop GUI

If you'd rather click than type:

```bash
python gui.py
```

Tabs:
- **Recognize** — open an image or run live webcam recognition
- **Enroll / Train** — add a person from disk photos or webcam captures
- **People** — list, rename, delete enrolled people

## 5. Android app

The Android app is a thin client that talks to the Python server running on
your PC over your local network.

### Run the server on your PC

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

Find your PC's LAN IP (e.g. `192.168.1.42`).

### Open the project in Android Studio

```
android/    # open this folder in Android Studio
```

It's a normal Gradle project (`com.paul.facescan`). Build and install on your
phone over USB or WiFi debugging.

### Use it

1. Open the app
2. Type your server URL into the field, e.g. `http://192.168.1.42:8000`, tap **Save URL**
3. **Recognize a face** — tap *Gallery* or *Camera*, pick/take a photo, results
   appear below
4. **Train a new face** — type a person name, tap *From gallery* or *From camera*,
   the photo is uploaded as a training sample. Repeat to add more samples.
5. **List enrolled people** — see who's been trained

The Android app and the desktop CLI/GUI all share the same `data/faces.pkl`
database, so anything trained on the PC is recognized by the phone and vice
versa.

## API endpoints (if you want to call the server yourself)

| Method | Path                          | Body                              | Description                          |
|--------|-------------------------------|-----------------------------------|--------------------------------------|
| GET    | `/health`                     | —                                 | Status + person count                |
| GET    | `/people`                     | —                                 | List enrolled people                 |
| POST   | `/people`                     | `name`                            | Create a person                      |
| PATCH  | `/people/{id}`                | `name`                            | Rename                               |
| DELETE | `/people/{id}`                | —                                 | Delete                               |
| POST   | `/people/{id}/enroll`         | `files[]` (multipart)             | Add training photos                  |
| POST   | `/enroll`                     | `name`, `files[]`                 | Create person + add photos in one go |
| POST   | `/recognize`                  | `file` (multipart)                | Identify faces in an image           |

## Notes & limits

- The default match threshold is `0.5` (Euclidean distance on 128-d face
  embeddings). Tighten with `--threshold 0.45` for fewer false positives,
  loosen with `--threshold 0.55` if it fails to recognize you.
- The CPU detector (`hog`) is fast and works well on a webcam. If you have an
  NVIDIA GPU + CUDA-built dlib you can switch to `--model cnn` for noticeably
  better detection on hard images.
- Doing on-device face recognition inside the Android app would require a
  TensorFlow Lite face-embedding model and a totally different code path. The
  server-based approach used here is simpler, more accurate, and lets the
  phone and PC share one trained database.
- The face database (`data/faces.pkl`) is in `.gitignore` — your face data
  never gets committed.
