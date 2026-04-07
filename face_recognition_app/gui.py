"""Simple Tkinter GUI for the face recognition app.

Lets you:
  - Enroll a person from picture files (file picker)
  - Enroll a person from the webcam
  - Recognize faces in a picture file
  - Run live webcam recognition
  - View / delete enrolled people
"""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageDraw, ImageFont, ImageTk

from faceapp.database import FaceDatabase
from faceapp.recognizer import Recognizer, _load_image  # noqa: PLC2701


PREVIEW_MAX = 480


class FaceApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Face Scanner")
        self.geometry("780x620")

        self.db = FaceDatabase()
        self.recognizer = Recognizer(self.db)

        self._build_ui()
        self._refresh_people()

    # ---------- UI ----------

    def _build_ui(self) -> None:
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_recognize_tab(nb)
        self._build_enroll_tab(nb)
        self._build_people_tab(nb)

        self.status = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status, anchor="w").pack(
            fill="x", padx=8, pady=(0, 6)
        )

    def _build_recognize_tab(self, nb: ttk.Notebook) -> None:
        frame = ttk.Frame(nb)
        nb.add(frame, text="Recognize")

        btns = ttk.Frame(frame)
        btns.pack(fill="x", pady=6)
        ttk.Button(btns, text="Open image…", command=self._recognize_image).pack(
            side="left", padx=4
        )
        ttk.Button(btns, text="Live webcam", command=self._recognize_live).pack(
            side="left", padx=4
        )

        self.preview_label = ttk.Label(frame)
        self.preview_label.pack(pady=8)
        self.recognize_results = tk.Text(frame, height=8, wrap="word")
        self.recognize_results.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_enroll_tab(self, nb: ttk.Notebook) -> None:
        frame = ttk.Frame(nb)
        nb.add(frame, text="Enroll / Train")

        ttk.Label(frame, text="Person name:").pack(anchor="w", padx=8, pady=(8, 0))
        self.enroll_name = tk.StringVar()
        ttk.Entry(frame, textvariable=self.enroll_name).pack(
            fill="x", padx=8, pady=4
        )

        btns = ttk.Frame(frame)
        btns.pack(fill="x", pady=6)
        ttk.Button(
            btns, text="Add photos from disk…", command=self._enroll_from_files
        ).pack(side="left", padx=4)
        ttk.Button(
            btns, text="Capture from webcam…", command=self._enroll_from_webcam
        ).pack(side="left", padx=4)

        self.enroll_log = tk.Text(frame, height=18, wrap="word")
        self.enroll_log.pack(fill="both", expand=True, padx=8, pady=8)

    def _build_people_tab(self, nb: ttk.Notebook) -> None:
        frame = ttk.Frame(nb)
        nb.add(frame, text="People")

        cols = ("id", "name", "num")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings")
        self.tree.heading("id", text="ID")
        self.tree.heading("name", text="Name")
        self.tree.heading("num", text="# Faces")
        self.tree.column("id", width=120)
        self.tree.column("name", width=240)
        self.tree.column("num", width=80, anchor="center")
        self.tree.pack(fill="both", expand=True, padx=8, pady=8)

        btns = ttk.Frame(frame)
        btns.pack(fill="x", padx=8, pady=4)
        ttk.Button(btns, text="Refresh", command=self._refresh_people).pack(
            side="left", padx=4
        )
        ttk.Button(btns, text="Rename…", command=self._rename_person).pack(
            side="left", padx=4
        )
        ttk.Button(btns, text="Delete", command=self._delete_person).pack(
            side="left", padx=4
        )

    # ---------- Helpers ----------

    def _set_status(self, msg: str) -> None:
        self.status.set(msg)
        self.update_idletasks()

    def _log_enroll(self, msg: str) -> None:
        self.enroll_log.insert("end", msg + "\n")
        self.enroll_log.see("end")

    def _refresh_people(self) -> None:
        for row in self.tree.get_children():
            self.tree.delete(row)
        for p in self.db.list_people():
            self.tree.insert(
                "", "end", values=(p["id"], p["name"], p["num_encodings"])
            )

    def _selected_person_id(self) -> str | None:
        sel = self.tree.selection()
        if not sel:
            return None
        return self.tree.item(sel[0])["values"][0]

    # ---------- Recognize actions ----------

    def _recognize_image(self) -> None:
        path = filedialog.askopenfilename(
            title="Pick an image",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.webp"), ("All", "*.*")],
        )
        if not path:
            return
        self._set_status(f"Recognizing {Path(path).name}…")
        try:
            img = _load_image(path)
            results = self.recognizer.recognize_image(img)
        except Exception as e:
            messagebox.showerror("Error", str(e))
            self._set_status("Ready")
            return

        # Draw boxes onto a preview image.
        pil = Image.fromarray(img)
        draw = ImageDraw.Draw(pil)
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 16)
        except Exception:
            font = ImageFont.load_default()
        for r in results:
            top, right, bottom, left = r.box
            color = (40, 200, 40) if r.name != "Unknown" else (220, 40, 40)
            draw.rectangle([left, top, right, bottom], outline=color, width=3)
            label = (
                r.name
                if r.name == "Unknown"
                else f"{r.name} {int(r.confidence * 100)}%"
            )
            draw.text((left + 4, bottom + 2), label, fill=color, font=font)

        pil.thumbnail((PREVIEW_MAX, PREVIEW_MAX))
        self._preview_image = ImageTk.PhotoImage(pil)
        self.preview_label.configure(image=self._preview_image)

        self.recognize_results.delete("1.0", "end")
        if not results:
            self.recognize_results.insert("end", "No faces detected.\n")
        else:
            for i, r in enumerate(results, 1):
                if r.name == "Unknown":
                    self.recognize_results.insert(
                        "end",
                        f"{i}. Unknown (closest distance {r.distance:.3f})\n",
                    )
                else:
                    self.recognize_results.insert(
                        "end",
                        f"{i}. {r.name} — {int(r.confidence * 100)}% "
                        f"(distance {r.distance:.3f})\n",
                    )
        self._set_status("Ready")

    def _recognize_live(self) -> None:
        from faceapp.webcam import run_live_recognition

        self._set_status("Live recognition running — focus the OpenCV window…")

        def worker():
            try:
                run_live_recognition(self.recognizer)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Webcam error", str(e)))
            finally:
                self.after(0, lambda: self._set_status("Ready"))

        threading.Thread(target=worker, daemon=True).start()

    # ---------- Enroll actions ----------

    def _enroll_from_files(self) -> None:
        name = self.enroll_name.get().strip()
        if not name:
            messagebox.showwarning("Need a name", "Enter a person's name first.")
            return
        paths = filedialog.askopenfilenames(
            title=f"Pick photos of {name}",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.bmp *.webp"), ("All", "*.*")],
        )
        if not paths:
            return
        self._set_status(f"Enrolling {name} from {len(paths)} file(s)…")
        pid, added, skipped = self.recognizer.enroll_from_paths(name, paths)
        self._log_enroll(
            f"[{name}] id={pid}: added {added} face(s), skipped {len(skipped)}."
        )
        for s in skipped:
            self._log_enroll(f"   skipped (no face found): {s}")
        self._refresh_people()
        self._set_status("Ready")

    def _enroll_from_webcam(self) -> None:
        from faceapp.webcam import capture_frames

        name = self.enroll_name.get().strip()
        if not name:
            messagebox.showwarning("Need a name", "Enter a person's name first.")
            return
        num = simpledialog.askinteger(
            "Frame count", "How many frames to capture?", initialvalue=20, minvalue=1
        )
        if not num:
            return
        self._set_status(f"Capturing {num} frames for {name}…")

        def worker():
            try:
                frames = capture_frames(num_frames=num)
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Webcam error", str(e)))
                self.after(0, lambda: self._set_status("Ready"))
                return
            pid = self.db.add_person(name)
            added = 0
            for f in frames:
                encs = self.recognizer.encode_faces_in_image(f, max_faces=1)
                if encs:
                    self.db.add_encodings(pid, encs)
                    added += 1
            self.after(
                0,
                lambda: self._log_enroll(
                    f"[{name}] webcam: added {added} usable face(s) from "
                    f"{len(frames)} captured frame(s)."
                ),
            )
            self.after(0, self._refresh_people)
            self.after(0, lambda: self._set_status("Ready"))

        threading.Thread(target=worker, daemon=True).start()

    # ---------- People actions ----------

    def _rename_person(self) -> None:
        pid = self._selected_person_id()
        if not pid:
            return
        new_name = simpledialog.askstring("Rename", "New name:")
        if not new_name:
            return
        self.db.rename_person(pid, new_name)
        self._refresh_people()

    def _delete_person(self) -> None:
        pid = self._selected_person_id()
        if not pid:
            return
        if not messagebox.askyesno("Delete", f"Delete person {pid}?"):
            return
        self.db.remove_person(pid)
        self._refresh_people()


def main() -> None:
    FaceApp().mainloop()


if __name__ == "__main__":
    main()
