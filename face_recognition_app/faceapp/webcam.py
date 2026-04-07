"""Webcam helpers: live recognition loop and single-frame capture."""

from __future__ import annotations

from typing import Callable

import cv2
import numpy as np

from .recognizer import RecognitionResult, Recognizer


def _draw_results(frame_bgr: np.ndarray, results: list[RecognitionResult]) -> None:
    for r in results:
        top, right, bottom, left = r.box
        color = (0, 200, 0) if r.name != "Unknown" else (0, 0, 220)
        cv2.rectangle(frame_bgr, (left, top), (right, bottom), color, 2)
        label = r.name if r.name == "Unknown" else f"{r.name} ({int(r.confidence * 100)}%)"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        cv2.rectangle(
            frame_bgr,
            (left, bottom),
            (left + tw + 8, bottom + th + 10),
            color,
            cv2.FILLED,
        )
        cv2.putText(
            frame_bgr,
            label,
            (left + 4, bottom + th + 4),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )


def run_live_recognition(
    recognizer: Recognizer,
    camera_index: int = 0,
    process_every_n: int = 2,
    window_name: str = "Face Scanner — press q to quit",
) -> None:
    """Open the webcam and run recognition until the user presses 'q'.

    ``process_every_n`` skips frames to keep the UI smooth on slower machines.
    """
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera index {camera_index}")

    frame_idx = 0
    last_results: list[RecognitionResult] = []
    try:
        while True:
            ok, frame_bgr = cap.read()
            if not ok:
                break
            if frame_idx % process_every_n == 0:
                rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                # Downscale for speed; results are scaled back below.
                small = cv2.resize(rgb, (0, 0), fx=0.5, fy=0.5)
                small_results = recognizer.recognize_image(small)
                last_results = []
                for r in small_results:
                    t, ri, b, le = r.box
                    last_results.append(
                        RecognitionResult(
                            box=(t * 2, ri * 2, b * 2, le * 2),
                            name=r.name,
                            person_id=r.person_id,
                            distance=r.distance,
                            confidence=r.confidence,
                        )
                    )
            _draw_results(frame_bgr, last_results)
            cv2.imshow(window_name, frame_bgr)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
            frame_idx += 1
    finally:
        cap.release()
        cv2.destroyAllWindows()


def capture_frames(
    camera_index: int = 0,
    num_frames: int = 20,
    on_frame: Callable[[int, np.ndarray], None] | None = None,
    window_name: str = "Capturing — press SPACE to grab, q to stop",
) -> list[np.ndarray]:
    """Interactively capture frames from the webcam (used during enrollment).

    Press SPACE to save the current frame, 'q' to stop early. Stops automatically
    after ``num_frames`` saves.
    """
    cap = cv2.VideoCapture(camera_index)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open camera index {camera_index}")

    saved: list[np.ndarray] = []
    try:
        while len(saved) < num_frames:
            ok, frame_bgr = cap.read()
            if not ok:
                break
            display = frame_bgr.copy()
            cv2.putText(
                display,
                f"Saved {len(saved)}/{num_frames} — SPACE to capture, q to quit",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
            cv2.imshow(window_name, display)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            if key == ord(" "):
                rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                saved.append(rgb)
                if on_frame is not None:
                    on_frame(len(saved), rgb)
    finally:
        cap.release()
        cv2.destroyAllWindows()
    return saved
