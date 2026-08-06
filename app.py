"""
MiX Stream Recorder — screen + plug-in camera → one lean MP4.

Run:
  python app.py
  or double-click run.bat
"""
from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Allow running as script from any cwd
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image

from capture import (
    FPS_CHOICES,
    LAYOUTS,
    RESOLUTIONS,
    CompositeCapture,
    list_cameras,
    list_monitors,
)
from encoder import (
    QUALITY_PRESETS,
    EncodeSettings,
    FFmpegPipeWriter,
    estimate_mb_per_minute,
    find_ffmpeg,
    list_recordings,
    pick_video_encoder,
    play_file,
)

OUTPUT_DIR = ROOT / "recordings"
PREVIEW_MAX_W = 960
PREVIEW_MAX_H = 540


class MixStreamRecorder(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("MiX Stream Recorder")
        self.geometry("1180x780")
        self.minsize(980, 680)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        self._capture: Optional[CompositeCapture] = None
        self._encoder: Optional[FFmpegPipeWriter] = None
        self._preview_on = False
        self._recording = False
        self._stop_event = threading.Event()
        self._worker: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._frame_count = 0
        self._rec_started = 0.0
        self._last_preview_imgtk = None
        self._status_var = ctk.StringVar(value="Ready")
        self._size_hint = ctk.StringVar(value="")
        self._timer_var = ctk.StringVar(value="00:00")
        self._encoder_name = "…"

        self._build_ui()
        self.after(100, self._bootstrap)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI ──────────────────────────────────────────────────────────
    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_rowconfigure(0, weight=1)

        # Left: preview
        left = ctk.CTkFrame(self, corner_radius=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(14, 8), pady=14)
        left.grid_rowconfigure(1, weight=1)
        left.grid_columnconfigure(0, weight=1)

        header = ctk.CTkLabel(
            left,
            text="MiX Stream Recorder",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        header.grid(row=0, column=0, sticky="w", padx=16, pady=(14, 6))

        self.preview_label = ctk.CTkLabel(left, text="Preview off", fg_color="#12141a", corner_radius=8)
        self.preview_label.grid(row=1, column=0, sticky="nsew", padx=16, pady=8)

        bar = ctk.CTkFrame(left, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 14))
        bar.grid_columnconfigure(4, weight=1)

        self.btn_preview = ctk.CTkButton(bar, text="Start preview", width=130, command=self.toggle_preview)
        self.btn_preview.grid(row=0, column=0, padx=(0, 8))

        self.btn_rec = ctk.CTkButton(
            bar,
            text="● Record",
            width=120,
            fg_color="#a11f2c",
            hover_color="#c42b3a",
            command=self.toggle_record,
        )
        self.btn_rec.grid(row=0, column=1, padx=4)

        self.timer_lbl = ctk.CTkLabel(bar, textvariable=self._timer_var, font=ctk.CTkFont(size=16, weight="bold"))
        self.timer_lbl.grid(row=0, column=2, padx=12)

        self.status_lbl = ctk.CTkLabel(bar, textvariable=self._status_var, text_color="#9aa3b2")
        self.status_lbl.grid(row=0, column=3, sticky="w")

        # Right: settings + library
        right = ctk.CTkScrollableFrame(self, corner_radius=12, width=380)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 14), pady=14)

        def section(title: str) -> ctk.CTkLabel:
            lbl = ctk.CTkLabel(right, text=title, font=ctk.CTkFont(size=14, weight="bold"), anchor="w")
            lbl.pack(fill="x", padx=8, pady=(14, 4))
            return lbl

        section("Sources")
        self.mon_menu = ctk.CTkOptionMenu(right, values=["Detecting…"], command=lambda _: self._refresh_size_hint())
        self.mon_menu.pack(fill="x", padx=8, pady=4)

        self.cam_menu = ctk.CTkOptionMenu(right, values=["Detecting…"])
        self.cam_menu.pack(fill="x", padx=8, pady=4)

        self.layout_menu = ctk.CTkOptionMenu(right, values=list(LAYOUTS), command=lambda _: self._refresh_size_hint())
        self.layout_menu.set(LAYOUTS[0])
        self.layout_menu.pack(fill="x", padx=8, pady=4)

        ctk.CTkButton(right, text="Rescan devices", command=self._rescan_devices, height=28).pack(
            fill="x", padx=8, pady=4
        )

        section("Output quality (anti-bloat)")
        self.res_menu = ctk.CTkOptionMenu(
            right, values=list(RESOLUTIONS.keys()), command=lambda _: self._refresh_size_hint()
        )
        self.res_menu.set("1920×1080 (Full HD)")
        self.res_menu.pack(fill="x", padx=8, pady=4)

        fps_row = ctk.CTkFrame(right, fg_color="transparent")
        fps_row.pack(fill="x", padx=8, pady=4)
        ctk.CTkLabel(fps_row, text="FPS").pack(side="left")
        self.fps_menu = ctk.CTkOptionMenu(
            fps_row, values=[str(f) for f in FPS_CHOICES], width=100, command=lambda _: self._refresh_size_hint()
        )
        self.fps_menu.set("30")
        self.fps_menu.pack(side="right")

        self.quality_menu = ctk.CTkOptionMenu(
            right, values=list(QUALITY_PRESETS.keys()), command=lambda _: self._refresh_size_hint()
        )
        self.quality_menu.set("Lean (smallest)")
        self.quality_menu.pack(fill="x", padx=8, pady=4)

        self.enc_menu = ctk.CTkOptionMenu(
            right, values=["auto", "nvenc", "amf", "qsv", "cpu"], command=lambda _: self._update_encoder_label()
        )
        self.enc_menu.set("auto")
        self.enc_menu.pack(fill="x", padx=8, pady=4)

        self.enc_info = ctk.CTkLabel(right, text="Encoder: …", text_color="#7dd3a7", anchor="w")
        self.enc_info.pack(fill="x", padx=8, pady=2)

        self.size_lbl = ctk.CTkLabel(right, textvariable=self._size_hint, text_color="#c9b27a", anchor="w", justify="left")
        self.size_lbl.pack(fill="x", padx=8, pady=6)

        tip = (
            "Tip: Lean + 30fps + 1080p keeps files small.\n"
            "Hardware encode (NVENC/AMF/QSV) is preferred.\n"
            "Avoid 60fps + Archive unless you need it."
        )
        ctk.CTkLabel(right, text=tip, text_color="#6b7280", anchor="w", justify="left", font=ctk.CTkFont(size=12)).pack(
            fill="x", padx=8, pady=4
        )

        section("Recordings")
        self.lib_box = ctk.CTkTextbox(right, height=160, font=ctk.CTkFont(family="Consolas", size=12))
        self.lib_box.pack(fill="x", padx=8, pady=4)
        self.lib_box.configure(state="disabled")

        lib_btns = ctk.CTkFrame(right, fg_color="transparent")
        lib_btns.pack(fill="x", padx=8, pady=6)
        ctk.CTkButton(lib_btns, text="Play selected", command=self._play_selected, width=120).pack(side="left", padx=(0, 6))
        ctk.CTkButton(lib_btns, text="Open folder", command=self._open_folder, width=110).pack(side="left", padx=4)
        ctk.CTkButton(lib_btns, text="Refresh", command=self._refresh_library, width=90).pack(side="left", padx=4)

        section("Folder")
        ctk.CTkLabel(right, text=str(OUTPUT_DIR), text_color="#6b7280", anchor="w", wraplength=320).pack(
            fill="x", padx=8, pady=(0, 16)
        )

    def _bootstrap(self) -> None:
        try:
            find_ffmpeg()
        except FileNotFoundError as e:
            self._status_var.set(str(e))
            self.btn_rec.configure(state="disabled")
        self._rescan_devices()
        self._update_encoder_label()
        self._refresh_size_hint()
        self._refresh_library()

    def _rescan_devices(self) -> None:
        try:
            mons = list_monitors()
            self._monitors = mons
            self.mon_menu.configure(values=[m.name for m in mons])
            # Prefer first physical monitor
            pick = mons[1].name if len(mons) > 1 else mons[0].name
            self.mon_menu.set(pick)
        except Exception as e:
            self._monitors = []
            self.mon_menu.configure(values=[f"Error: {e}"])
            self.mon_menu.set(f"Error: {e}")

        try:
            cams = list_cameras()
            self._cameras = cams
            labels = [c[1] for c in cams]
            self.cam_menu.configure(values=labels)
            self.cam_menu.set(labels[0])
            no_cam = labels and "No camera" in labels[0]
        except Exception as e:
            self._cameras = [(0, "No camera detected (screen-only OK)")]
            self.cam_menu.configure(values=[self._cameras[0][1]])
            self.cam_menu.set(self._cameras[0][1])
            no_cam = True
            self._status_var.set(f"Camera scan issue: {e}")
            return

        if no_cam:
            # Screen capture still works; avoid PiP layouts looking "broken"
            self._status_var.set("Devices scanned · no plug-in camera (screen-only is fine)")
        else:
            self._status_var.set(f"Devices scanned · {len(self._cameras)} camera(s)")

    def _update_encoder_label(self) -> None:
        prefer = self.enc_menu.get()
        try:
            name = pick_video_encoder(prefer)
        except Exception:
            name = "unknown"
        self._encoder_name = name
        self.enc_info.configure(text=f"Encoder: {name}")

    def _selected_monitor_index(self) -> int:
        name = self.mon_menu.get()
        for m in getattr(self, "_monitors", []):
            if m.name == name:
                return m.index
        return 1

    def _selected_camera_index(self) -> int:
        name = self.cam_menu.get()
        for idx, label in getattr(self, "_cameras", []):
            if label == name:
                return idx
        return 0

    def _resolve_out_size(self) -> tuple[int, int]:
        key = self.res_menu.get()
        w, h = RESOLUTIONS.get(key, (1920, 1080))
        if w == 0:
            # Match source, cap 1080p long edge
            mon_i = self._selected_monitor_index()
            mon = next((m for m in self._monitors if m.index == mon_i), None)
            if mon:
                sw, sh = mon.width, mon.height
            else:
                sw, sh = 1920, 1080
            scale = min(1.0, 1920 / max(sw, 1), 1080 / max(sh, 1))
            w = max(2, int(sw * scale) // 2 * 2)
            h = max(2, int(sh * scale) // 2 * 2)
        # even dims for yuv420
        return w - (w % 2), h - (h % 2)

    def _refresh_size_hint(self) -> None:
        w, h = self._resolve_out_size()
        fps = int(self.fps_menu.get())
        q = self.quality_menu.get()
        mb = estimate_mb_per_minute(q, w, h, fps)
        self._size_hint.set(
            f"Output {w}×{h} @ {fps} fps · ~{mb:.0f} MB/min\n"
            f"10 min ≈ {mb * 10:.0f} MB  ·  30 min ≈ {mb * 30:.0f} MB"
        )

    # ── Preview / record loop ───────────────────────────────────────
    def toggle_preview(self) -> None:
        if self._preview_on and not self._recording:
            self._stop_loop()
            self.btn_preview.configure(text="Start preview")
            self._status_var.set("Preview stopped")
            return
        if not self._preview_on:
            self._start_loop(record=False)
            self.btn_preview.configure(text="Stop preview")

    def toggle_record(self) -> None:
        if self._recording:
            self._stop_loop()
            self.btn_rec.configure(text="● Record", fg_color="#a11f2c")
            self.btn_preview.configure(text="Start preview" if not self._preview_on else "Stop preview")
            return
        self._start_loop(record=True)
        self.btn_rec.configure(text="■ Stop", fg_color="#555")
        self.btn_preview.configure(text="Preview on")

    def _start_loop(self, record: bool) -> None:
        if self._worker and self._worker.is_alive():
            # Upgrade preview → record
            if record and not self._recording:
                self._begin_encoder()
                self._recording = True
                self._rec_started = time.time()
                self._frame_count = 0
                self._status_var.set("Recording…")
            return

        self._stop_event.clear()
        try:
            w, h = self._resolve_out_size()
            layout = self.layout_menu.get()
            include_cam = layout != "Screen only"
            self._capture = CompositeCapture(
                monitor_index=self._selected_monitor_index(),
                camera_index=self._selected_camera_index(),
                layout=layout,
                out_size=(w, h),
                include_camera=include_cam,
            )
            self._capture.open()
        except Exception as e:
            self._status_var.set(f"Capture failed: {e}")
            return

        self._preview_on = True
        self._recording = record
        cam_note = ""
        if include_cam and self._capture and not self._capture.camera_ok:
            cam_note = " · camera offline (screen only)"
        if record:
            if not self._begin_encoder():
                self._capture.close()
                self._capture = None
                self._preview_on = False
                return
            self._rec_started = time.time()
            self._frame_count = 0
            self._status_var.set(f"Recording…{cam_note}")
        else:
            self._status_var.set(f"Previewing…{cam_note}")

        fps = int(self.fps_menu.get())
        self._worker = threading.Thread(target=self._loop, args=(fps,), daemon=True)
        self._worker.start()
        self._tick_ui()

    def _begin_encoder(self) -> bool:
        w, h = self._resolve_out_size()
        fps = int(self.fps_menu.get())
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out = OUTPUT_DIR / f"mix-rec-{stamp}.mp4"
        settings = EncodeSettings(
            width=w,
            height=h,
            fps=fps,
            quality=self.quality_menu.get(),
            encoder_prefer=self.enc_menu.get(),
        )
        self._encoder = FFmpegPipeWriter(out, settings)
        try:
            self._encoder.start()
            self._current_out = out
            self._update_encoder_label()
            return True
        except Exception as e:
            self._status_var.set(f"Encoder failed: {e}")
            self._encoder = None
            return False

    def _loop(self, fps: int) -> None:
        interval = 1.0 / max(1, fps)
        next_t = time.perf_counter()
        while not self._stop_event.is_set():
            try:
                assert self._capture is not None
                frame = self._capture.grab()
                # Ensure exact encoder size
                if self._encoder and self._recording:
                    eh, ew = self._encoder.settings.height, self._encoder.settings.width
                    if frame.shape[0] != eh or frame.shape[1] != ew:
                        frame = cv2.resize(frame, (ew, eh), interpolation=cv2.INTER_AREA)
                    try:
                        self._encoder.write_frame(np.ascontiguousarray(frame))
                        self._frame_count += 1
                    except BrokenPipeError:
                        self._status_var.set("Encoder pipe broken")
                        break

                # Preview downsample
                prev = self._make_preview(frame)
                with self._lock:
                    self._pending_preview = prev

            except Exception as e:
                self._status_var.set(f"Loop error: {e}")
                break

            next_t += interval
            sleep = next_t - time.perf_counter()
            if sleep > 0:
                time.sleep(sleep)
            else:
                next_t = time.perf_counter()

        # Cleanup capture in thread
        if self._capture:
            self._capture.close()
            self._capture = None

    def _make_preview(self, frame_bgr: np.ndarray) -> Image.Image:
        h, w = frame_bgr.shape[:2]
        scale = min(PREVIEW_MAX_W / w, PREVIEW_MAX_H / h, 1.0)
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        small = cv2.resize(frame_bgr, (nw, nh), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)

    def _tick_ui(self) -> None:
        if not self._preview_on and not self._recording:
            return
        with self._lock:
            img = getattr(self, "_pending_preview", None)
            self._pending_preview = None
        if img is not None:
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            self._last_preview_imgtk = ctk_img  # prevent GC
            self.preview_label.configure(image=ctk_img, text="")

        if self._recording:
            elapsed = int(time.time() - self._rec_started)
            self._timer_var.set(f"{elapsed // 60:02d}:{elapsed % 60:02d}")
            self._status_var.set(f"Recording · {self._frame_count} frames · {self._encoder_name}")

        if self._worker and self._worker.is_alive():
            self.after(33, self._tick_ui)
        else:
            # worker ended unexpectedly
            if self._recording:
                self._finalize_encoder()
            self._preview_on = False
            self._recording = False
            self.btn_preview.configure(text="Start preview")
            self.btn_rec.configure(text="● Record", fg_color="#a11f2c")

    def _stop_loop(self) -> None:
        self._stop_event.set()
        if self._worker:
            self._worker.join(timeout=5)
            self._worker = None
        was_rec = self._recording
        self._recording = False
        self._preview_on = False
        if was_rec:
            self._finalize_encoder()
        else:
            self._status_var.set("Stopped")
        self._timer_var.set("00:00")

    def _finalize_encoder(self) -> None:
        enc = self._encoder
        self._encoder = None
        if not enc:
            return
        ok, msg = enc.stop()
        path = getattr(self, "_current_out", None)
        if ok and path and path.is_file():
            mb = path.stat().st_size / (1024 * 1024)
            self._status_var.set(f"Saved {path.name} ({mb:.1f} MB) · {msg}")
        else:
            self._status_var.set(f"Encode issue: {msg}")
        self._refresh_library()

    # ── Library / playback ──────────────────────────────────────────
    def _refresh_library(self) -> None:
        files = list_recordings(OUTPUT_DIR)
        self._lib_files = files
        self.lib_box.configure(state="normal")
        self.lib_box.delete("1.0", "end")
        if not files:
            self.lib_box.insert("end", "(no recordings yet)\n")
        else:
            for p in files[:40]:
                mb = p.stat().st_size / (1024 * 1024)
                self.lib_box.insert("end", f"{p.name}  ({mb:.1f} MB)\n")
        self.lib_box.configure(state="disabled")

    def _play_selected(self) -> None:
        files = getattr(self, "_lib_files", [])
        if not files:
            self._status_var.set("Nothing to play")
            return
        # Use first line selection if any
        try:
            # CTkTextbox selection
            sel = self.lib_box.get("sel.first", "sel.last").strip()
        except Exception:
            sel = ""
        path = None
        if sel:
            name = sel.split()[0]
            for p in files:
                if p.name == name:
                    path = p
                    break
        if path is None:
            path = files[0]
        ok, how = play_file(path)
        self._status_var.set(f"Playing {path.name} via {how}" if ok else f"Play failed: {how}")

    def _open_folder(self) -> None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(OUTPUT_DIR))  # type: ignore[attr-defined]
        else:
            import subprocess

            subprocess.Popen(["xdg-open", str(OUTPUT_DIR)])

    def _on_close(self) -> None:
        try:
            self._stop_event.set()
            if self._worker:
                self._worker.join(timeout=3)
            if self._encoder:
                self._encoder.stop()
            if self._capture:
                self._capture.close()
        except Exception:
            pass
        self.destroy()


def main() -> None:
    app = MixStreamRecorder()
    app.mainloop()


if __name__ == "__main__":
    main()
