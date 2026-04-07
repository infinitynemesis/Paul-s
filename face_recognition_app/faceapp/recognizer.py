"""Face detection, encoding, and matching against the database.

Uses the `face_recognition` library (dlib under the hood). It produces
128-dimensional face embeddings; matching is done by Euclidean distance.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import face_recognition
import numpy as np
from PIL import Image, ImageOps

from .database import FaceDatabase


# Distance below which we accept a match. The face_recognition default is 0.6;
# 0.5 is stricter and reduces false positives noticeably.
DEFAULT_MATCH_THRESHOLD = 0.5


@dataclass
class RecognitionResult:
    box: tuple[int, int, int, int]  # (top, right, bottom, left) in pixel coords
    name: str                        # "Unknown" if no match
    person_id: str | None
    distance: float                  # best distance found (lower = better)
    confidence: float                # rough 0..1 confidence (1 = perfect match)

    def to_dict(self) -> dict:
        return {
            "box": list(self.box),
            "name": self.name,
            "person_id": self.person_id,
            "distance": float(self.distance),
            "confidence": float(self.confidence),
        }


def _load_image(path: str | Path) -> np.ndarray:
    """Load an image and apply EXIF rotation so phone photos come out upright."""
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    return np.array(img)


def _distance_to_confidence(distance: float, threshold: float) -> float:
    """Map a face distance to a rough 0..1 confidence score."""
    if distance >= 1.0:
        return 0.0
    if distance <= threshold / 2:
        return 1.0
    # Linear from threshold->0.0 confidence to threshold/2->1.0 confidence.
    return max(0.0, min(1.0, 1.0 - (distance - threshold / 2) / (threshold / 2)))


class Recognizer:
    """Wraps a FaceDatabase and provides detect/encode/match operations."""

    def __init__(
        self,
        db: FaceDatabase,
        match_threshold: float = DEFAULT_MATCH_THRESHOLD,
        detection_model: str = "hog",  # "hog" (CPU, fast) or "cnn" (GPU, accurate)
    ):
        self.db = db
        self.match_threshold = match_threshold
        self.detection_model = detection_model

    # ---------- enrollment ----------

    def encode_faces_in_image(
        self, image: np.ndarray, max_faces: int | None = 1
    ) -> list[np.ndarray]:
        """Detect faces in an image and return their 128-d encodings.

        For enrollment we usually expect a single face per photo, so the
        default cap is 1 (the largest detected face). Set ``max_faces=None``
        to encode every face found.
        """
        boxes = face_recognition.face_locations(image, model=self.detection_model)
        if not boxes:
            return []
        if max_faces is not None and len(boxes) > max_faces:
            # Keep the biggest faces (largest bounding-box area).
            boxes.sort(
                key=lambda b: (b[2] - b[0]) * (b[1] - b[3]),
                reverse=True,
            )
            boxes = boxes[:max_faces]
        return face_recognition.face_encodings(image, known_face_locations=boxes)

    def enroll_from_paths(
        self, name: str, image_paths: Iterable[str | Path]
    ) -> tuple[str, int, list[str]]:
        """Train (or extend training of) a person using images on disk.

        Returns ``(person_id, num_added, skipped_paths)``.
        """
        person_id = self.db.add_person(name)
        added_encodings: list[np.ndarray] = []
        added_paths: list[str] = []
        skipped: list[str] = []

        for path in image_paths:
            path = Path(path)
            try:
                img = _load_image(path)
            except Exception:
                skipped.append(str(path))
                continue
            encs = self.encode_faces_in_image(img, max_faces=1)
            if not encs:
                skipped.append(str(path))
                continue
            added_encodings.append(encs[0])
            added_paths.append(str(path))

        if added_encodings:
            self.db.add_encodings(person_id, added_encodings, added_paths)
        return person_id, len(added_encodings), skipped

    def enroll_from_image_array(
        self, name: str, image: np.ndarray
    ) -> tuple[str, int]:
        """Train using an in-memory image (e.g. a webcam frame)."""
        person_id = self.db.add_person(name)
        encs = self.encode_faces_in_image(image, max_faces=1)
        if encs:
            self.db.add_encodings(person_id, encs)
        return person_id, len(encs)

    # ---------- recognition ----------

    def recognize_image(self, image: np.ndarray) -> list[RecognitionResult]:
        """Find every face in an image and identify each one."""
        boxes = face_recognition.face_locations(image, model=self.detection_model)
        if not boxes:
            return []
        encodings = face_recognition.face_encodings(image, known_face_locations=boxes)
        return [self._match(box, enc) for box, enc in zip(boxes, encodings)]

    def recognize_image_path(self, path: str | Path) -> list[RecognitionResult]:
        return self.recognize_image(_load_image(path))

    def _match(
        self, box: tuple[int, int, int, int], encoding: np.ndarray
    ) -> RecognitionResult:
        known_encs, known_ids, known_names = self.db.all_encodings()
        if not known_encs:
            return RecognitionResult(
                box=box, name="Unknown", person_id=None, distance=1.0, confidence=0.0
            )
        distances = face_recognition.face_distance(known_encs, encoding)
        best_idx = int(np.argmin(distances))
        best_distance = float(distances[best_idx])
        if best_distance <= self.match_threshold:
            return RecognitionResult(
                box=box,
                name=known_names[best_idx],
                person_id=known_ids[best_idx],
                distance=best_distance,
                confidence=_distance_to_confidence(best_distance, self.match_threshold),
            )
        return RecognitionResult(
            box=box,
            name="Unknown",
            person_id=None,
            distance=best_distance,
            confidence=0.0,
        )
