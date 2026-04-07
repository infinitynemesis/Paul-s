"""HTTP server exposing the face recognition app to remote clients (e.g. Android).

Run with:
    uvicorn server:app --host 0.0.0.0 --port 8000

Endpoints
---------
GET  /health
GET  /people                              -> list enrolled people
POST /people                              -> create a person {name}
DELETE /people/{person_id}
PATCH  /people/{person_id}                -> rename {name}
POST /people/{person_id}/enroll            -> upload one or more images (multipart)
POST /recognize                           -> upload an image, returns face matches
"""

from __future__ import annotations

import io
import os
from typing import Any

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageOps

from faceapp.database import FaceDatabase
from faceapp.recognizer import Recognizer


DB_PATH = os.environ.get("FACEAPP_DB", "data/faces.pkl")
THRESHOLD = float(os.environ.get("FACEAPP_THRESHOLD", "0.5"))
MODEL = os.environ.get("FACEAPP_MODEL", "hog")

db = FaceDatabase(path=DB_PATH)
recognizer = Recognizer(db, match_threshold=THRESHOLD, detection_model=MODEL)

app = FastAPI(title="Face Scanner API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _decode_upload(upload: UploadFile) -> np.ndarray:
    raw = upload.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail=f"Empty upload: {upload.filename}")
    try:
        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img).convert("RGB")
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Could not read image {upload.filename}: {e}"
        )
    return np.array(img)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "people": len(db.list_people()),
        "threshold": THRESHOLD,
        "model": MODEL,
    }


@app.get("/people")
def list_people() -> list[dict]:
    return db.list_people()


@app.post("/people")
def create_person(name: str = Form(...)) -> dict:
    if not name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    pid = db.add_person(name)
    return {"id": pid, "name": name}


@app.delete("/people/{person_id}")
def delete_person(person_id: str) -> dict:
    if not db.remove_person(person_id):
        raise HTTPException(status_code=404, detail="person not found")
    return {"deleted": person_id}


@app.patch("/people/{person_id}")
def rename_person(person_id: str, name: str = Form(...)) -> dict:
    if not db.rename_person(person_id, name):
        raise HTTPException(status_code=404, detail="person not found")
    return {"id": person_id, "name": name}


@app.post("/people/{person_id}/enroll")
def enroll(
    person_id: str, files: list[UploadFile] = File(...)
) -> dict:
    if person_id not in {p["id"] for p in db.list_people()}:
        raise HTTPException(status_code=404, detail="person not found")
    added = 0
    skipped: list[str] = []
    for upload in files:
        img = _decode_upload(upload)
        encs = recognizer.encode_faces_in_image(img, max_faces=1)
        if encs:
            db.add_encodings(person_id, encs)
            added += 1
        else:
            skipped.append(upload.filename or "<unnamed>")
    return {"person_id": person_id, "added": added, "skipped": skipped}


@app.post("/enroll")
def enroll_new(
    name: str = Form(...), files: list[UploadFile] = File(...)
) -> dict:
    """Convenience: create the person if needed, then enroll the uploaded images."""
    pid = db.add_person(name)
    return enroll(pid, files)


@app.post("/recognize")
def recognize(file: UploadFile = File(...)) -> dict:
    img = _decode_upload(file)
    results = recognizer.recognize_image(img)
    return {
        "count": len(results),
        "faces": [r.to_dict() for r in results],
    }
