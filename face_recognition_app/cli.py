"""Command-line interface for the face recognition app.

Examples:

    # Enroll a person from a folder of photos
    python cli.py enroll "Paul" --images ~/Pictures/me/*.jpg

    # Enroll using your webcam (interactively grab 20 frames)
    python cli.py enroll-webcam "Paul" --frames 20

    # Recognize faces in an image
    python cli.py recognize photo.jpg

    # Live recognition from the webcam
    python cli.py live

    # Manage people
    python cli.py list
    python cli.py rename <person_id> "New Name"
    python cli.py delete <person_id>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from faceapp.database import FaceDatabase
from faceapp.recognizer import Recognizer


def _build_recognizer(args: argparse.Namespace) -> Recognizer:
    db = FaceDatabase(path=args.db)
    return Recognizer(db, match_threshold=args.threshold, detection_model=args.model)


def cmd_enroll(args: argparse.Namespace) -> int:
    rec = _build_recognizer(args)
    paths = [Path(p) for p in args.images]
    if not paths:
        print("error: no image paths provided", file=sys.stderr)
        return 2
    pid, added, skipped = rec.enroll_from_paths(args.name, paths)
    print(f"Enrolled '{args.name}' (id={pid}): {added} faces added.")
    if skipped:
        print(f"  Skipped {len(skipped)} file(s) with no detectable face:")
        for s in skipped:
            print(f"    - {s}")
    return 0


def cmd_enroll_webcam(args: argparse.Namespace) -> int:
    from faceapp.webcam import capture_frames

    rec = _build_recognizer(args)
    print(
        f"Capturing up to {args.frames} frames. "
        "Press SPACE to grab a frame, q to stop early."
    )
    frames = capture_frames(camera_index=args.camera, num_frames=args.frames)
    if not frames:
        print("No frames captured.")
        return 1
    pid = rec.db.add_person(args.name)
    total_added = 0
    for f in frames:
        encs = rec.encode_faces_in_image(f, max_faces=1)
        if encs:
            rec.db.add_encodings(pid, encs)
            total_added += 1
    print(
        f"Enrolled '{args.name}' (id={pid}): {total_added} usable face(s) "
        f"out of {len(frames)} captured frame(s)."
    )
    return 0


def cmd_recognize(args: argparse.Namespace) -> int:
    rec = _build_recognizer(args)
    results = rec.recognize_image_path(args.image)
    if args.json:
        print(json.dumps([r.to_dict() for r in results], indent=2))
        return 0
    if not results:
        print("No faces detected.")
        return 0
    print(f"Found {len(results)} face(s):")
    for i, r in enumerate(results, 1):
        if r.name == "Unknown":
            print(f"  {i}. Unknown  (closest distance {r.distance:.3f})")
        else:
            print(
                f"  {i}. {r.name}  "
                f"(confidence {int(r.confidence * 100)}%, distance {r.distance:.3f})"
            )
    return 0


def cmd_live(args: argparse.Namespace) -> int:
    from faceapp.webcam import run_live_recognition

    rec = _build_recognizer(args)
    print("Starting live recognition. Press 'q' in the window to quit.")
    run_live_recognition(rec, camera_index=args.camera)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    db = FaceDatabase(path=args.db)
    people = db.list_people()
    if args.json:
        print(json.dumps(people, indent=2))
        return 0
    if not people:
        print("(no people enrolled yet)")
        return 0
    print(f"{'ID':14}  {'Name':24}  {'#Faces':>7}")
    print("-" * 50)
    for p in people:
        print(f"{p['id']:14}  {p['name']:24}  {p['num_encodings']:>7}")
    return 0


def cmd_rename(args: argparse.Namespace) -> int:
    db = FaceDatabase(path=args.db)
    if db.rename_person(args.person_id, args.new_name):
        print(f"Renamed {args.person_id} -> '{args.new_name}'")
        return 0
    print(f"error: no person with id {args.person_id}", file=sys.stderr)
    return 1


def cmd_delete(args: argparse.Namespace) -> int:
    db = FaceDatabase(path=args.db)
    if db.remove_person(args.person_id):
        print(f"Deleted {args.person_id}")
        return 0
    print(f"error: no person with id {args.person_id}", file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="faceapp", description="Face recognition CLI")
    p.add_argument(
        "--db",
        default="data/faces.pkl",
        help="Path to the face database file (default: data/faces.pkl)",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Match threshold (lower = stricter; default 0.5)",
    )
    p.add_argument(
        "--model",
        choices=["hog", "cnn"],
        default="hog",
        help="Face detector model: 'hog' (CPU, fast) or 'cnn' (GPU, accurate)",
    )

    sub = p.add_subparsers(dest="command", required=True)

    pe = sub.add_parser("enroll", help="Enroll a person from image files")
    pe.add_argument("name")
    pe.add_argument("--images", nargs="+", required=True, help="Image files")
    pe.set_defaults(func=cmd_enroll)

    pew = sub.add_parser("enroll-webcam", help="Enroll a person using the webcam")
    pew.add_argument("name")
    pew.add_argument("--frames", type=int, default=20)
    pew.add_argument("--camera", type=int, default=0)
    pew.set_defaults(func=cmd_enroll_webcam)

    pr = sub.add_parser("recognize", help="Recognize faces in an image file")
    pr.add_argument("image")
    pr.add_argument("--json", action="store_true")
    pr.set_defaults(func=cmd_recognize)

    pl = sub.add_parser("live", help="Live webcam recognition")
    pl.add_argument("--camera", type=int, default=0)
    pl.set_defaults(func=cmd_live)

    pls = sub.add_parser("list", help="List enrolled people")
    pls.add_argument("--json", action="store_true")
    pls.set_defaults(func=cmd_list)

    prn = sub.add_parser("rename", help="Rename an enrolled person")
    prn.add_argument("person_id")
    prn.add_argument("new_name")
    prn.set_defaults(func=cmd_rename)

    pd = sub.add_parser("delete", help="Delete an enrolled person")
    pd.add_argument("person_id")
    pd.set_defaults(func=cmd_delete)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
