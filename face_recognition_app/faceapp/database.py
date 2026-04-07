"""Persistent storage of known people and their face encodings.

The database is a single pickle file containing a dict:
    {
        "people": {
            "<person_id>": {
                "name": str,
                "encodings": list[np.ndarray],   # one 128-d vector per training photo
                "image_paths": list[str],         # original training photo paths
                "created_at": str,
                "updated_at": str,
            },
            ...
        },
        "version": 1,
    }

Pickle is fine here because the file is local and only this app reads it.
"""

from __future__ import annotations

import datetime as _dt
import pickle
import threading
import uuid
from pathlib import Path
from typing import Iterable

import numpy as np


_VERSION = 1
_DEFAULT_DB_PATH = Path("data") / "faces.pkl"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class FaceDatabase:
    """Thread-safe store of known people and their face encodings."""

    def __init__(self, path: str | Path = _DEFAULT_DB_PATH):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._data: dict = {"people": {}, "version": _VERSION}
        self._load()

    # ---------- persistence ----------

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("rb") as f:
            self._data = pickle.load(f)
        if "people" not in self._data:
            self._data["people"] = {}

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            with tmp.open("wb") as f:
                pickle.dump(self._data, f)
            tmp.replace(self.path)

    # ---------- queries ----------

    def list_people(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "id": pid,
                    "name": p["name"],
                    "num_encodings": len(p["encodings"]),
                    "created_at": p.get("created_at"),
                    "updated_at": p.get("updated_at"),
                }
                for pid, p in self._data["people"].items()
            ]

    def find_by_name(self, name: str) -> str | None:
        name_l = name.strip().lower()
        with self._lock:
            for pid, p in self._data["people"].items():
                if p["name"].strip().lower() == name_l:
                    return pid
        return None

    def all_encodings(self) -> tuple[list[np.ndarray], list[str], list[str]]:
        """Return (encodings, person_ids, names) flattened across all people."""
        encodings: list[np.ndarray] = []
        person_ids: list[str] = []
        names: list[str] = []
        with self._lock:
            for pid, p in self._data["people"].items():
                for enc in p["encodings"]:
                    encodings.append(enc)
                    person_ids.append(pid)
                    names.append(p["name"])
        return encodings, person_ids, names

    # ---------- mutations ----------

    def add_person(self, name: str) -> str:
        """Create a new person record. Returns the person_id."""
        with self._lock:
            existing = self.find_by_name(name)
            if existing:
                return existing
            pid = uuid.uuid4().hex[:12]
            self._data["people"][pid] = {
                "name": name.strip(),
                "encodings": [],
                "image_paths": [],
                "created_at": _now(),
                "updated_at": _now(),
            }
            self.save()
            return pid

    def add_encodings(
        self,
        person_id: str,
        encodings: Iterable[np.ndarray],
        image_paths: Iterable[str] = (),
    ) -> int:
        """Append face encodings to an existing person. Returns new total count."""
        with self._lock:
            if person_id not in self._data["people"]:
                raise KeyError(f"Unknown person_id: {person_id}")
            p = self._data["people"][person_id]
            new_encs = list(encodings)
            p["encodings"].extend(new_encs)
            p["image_paths"].extend(list(image_paths))
            p["updated_at"] = _now()
            self.save()
            return len(p["encodings"])

    def remove_person(self, person_id: str) -> bool:
        with self._lock:
            if person_id in self._data["people"]:
                del self._data["people"][person_id]
                self.save()
                return True
        return False

    def rename_person(self, person_id: str, new_name: str) -> bool:
        with self._lock:
            if person_id not in self._data["people"]:
                return False
            self._data["people"][person_id]["name"] = new_name.strip()
            self._data["people"][person_id]["updated_at"] = _now()
            self.save()
            return True
