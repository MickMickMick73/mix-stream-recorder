"""Screen + plug-in camera capture and layout composite."""
from __future__ import annotations

import contextlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterator, Optional

import cv2
import numpy as np

try:
    import mss
except ImportError:  # pragma: no cover
    mss = None  # type: ignore


LAYOUTS = (
    "Screen + PiP (bottom-right)",
    "Screen + PiP (top-right)",
    "Side by side",
    "Screen only",
    "Camera only",
)


@dataclass
class MonitorInfo:
    index: int  # mss index (1 = first real monitor; 0 = virtual all)
    name: str
    width: int
    height: int
    left: int
    top: int


def _make_mss():
    """mss 10+ prefers MSS(); older used mss()."""
    if mss is None:
        raise RuntimeError("mss not installed — pip install mss")
    if hasattr(mss, "MSS"):
        return mss.MSS()
    return mss.mss()


@contextlib.contextmanager
def _quiet_native_logs() -> Iterator[None]:
    """Mute OpenCV C++ WARN/ERROR spam during camera probe (writes to stderr)."""
    prev_level = None
    try:
        from cv2.utils import logging as cvlog  # type: ignore

        prev_level = cvlog.getLogLevel()
        cvlog.setLogLevel(cvlog.LOG_LEVEL_SILENT)
    except Exception:
        pass

    # Also redirect OS-level stderr fd (OpenCV often bypasses Python sys.stderr)
    devnull_fd = None
    saved_fd = None
    try:
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        saved_fd = os.dup(2)
        os.dup2(devnull_fd, 2)
        yield
    finally:
        try:
            if saved_fd is not None:
                os.dup2(saved_fd, 2)
                os.close(saved_fd)
            if devnull_fd is not None:
                os.close(devnull_fd)
        except Exception:
            pass
        if prev_level is not None:
            try:
                from cv2.utils import logging as cvlog  # type: ignore

                cvlog.setLogLevel(prev_level)
            except Exception:
                pass


def list_monitors() -> list[MonitorInfo]:
    out: list[MonitorInfo] = []
    with _make_mss() as sct:
        for i, mon in enumerate(sct.monitors):
            w, h = mon["width"], mon["height"]
            if i == 0:
                name = f"All displays ({w}×{h})"
            else:
                name = f"Monitor {i} ({w}×{h})"
            out.append(
                MonitorInfo(
                    index=i,
                    name=name,
                    width=w,
                    height=h,
                    left=mon["left"],
                    top=mon["top"],
                )
            )
    return out


def _find_ffmpeg_bin() -> Optional[str]:
    import shutil
    from pathlib import Path

    path = shutil.which("ffmpeg")
    if path:
        return path
    winget = Path.home() / "AppData/Local/Microsoft/WinGet/Links/ffmpeg.exe"
    if winget.is_file():
        return str(winget)
    return None


def _ffmpeg_dshow_video_devices() -> list[str]:
    """Friendly device names from ffmpeg DirectShow (Windows)."""
    if sys.platform != "win32":
        return []
    ff = _find_ffmpeg_bin()
    if not ff:
        return []
    try:
        r = subprocess.run(
            [ff, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
            capture_output=True,
            text=True,
            timeout=12,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        text = (r.stderr or "") + "\n" + (r.stdout or "")
    except Exception:
        return []

    names: list[str] = []
    in_video = False
    for line in text.splitlines():
        low = line.lower()
        if "directshow video devices" in low:
            in_video = True
            continue
        if "directshow audio devices" in low:
            break
        if not in_video:
            continue
        # e.g. [dshow @ ...]  "HD Webcam"
        m = re.search(r'"([^"]+)"', line)
        if m:
            name = m.group(1).strip()
            if name and name not in names and "alternative name" not in low:
                names.append(name)
    return names


def list_cameras(max_probe: int = 4) -> list[tuple[int, str]]:
    """
    List plug-in cameras without flooding the console.

    Strategy:
    1) Prefer ffmpeg dshow names mapped to indices 0..n-1
    2) Quietly verify index 0 only when dshow list is empty
    3) Never walk MSMF/CAP_ANY/obsensor backends (those print the errors you saw)
    """
    dshow_names = _ffmpeg_dshow_video_devices()
    found: list[tuple[int, str]] = []

    if dshow_names:
        # Map listed devices to sequential OpenCV DSHOW indices (usual Windows mapping)
        for i, name in enumerate(dshow_names[:max_probe]):
            # Optional quiet open-check; if fail, still list name (device may be busy)
            with _quiet_native_logs():
                cap = _open_camera_quiet(i)
                ok = False
                if cap is not None:
                    ok, _ = cap.read()
                    cap.release()
            label = f"{name}" if ok or i == 0 else f"{name}"
            found.append((i, label if ok else f"{name}"))
        # De-dupe keep order
        if found:
            return found

    # Fallback: probe only a few indices, DSHOW-only, stderr muted, stop after first miss
    with _quiet_native_logs():
        misses = 0
        for i in range(max_probe):
            cap = _open_camera_quiet(i)
            if cap is None:
                misses += 1
                if misses >= 1 and i >= 1:
                    break
                continue
            ok, _ = cap.read()
            cap.release()
            if ok:
                found.append((i, f"Camera {i}"))
                misses = 0
            else:
                misses += 1
                if misses >= 1 and i >= 1:
                    break

    if not found:
        found.append((0, "No camera detected (screen-only OK)"))
    return found


def _preferred_backends() -> list[int]:
    """Windows: DirectShow only. Avoid MSMF + CAP_ANY (obsensor ERROR spam)."""
    if sys.platform == "win32" and hasattr(cv2, "CAP_DSHOW"):
        return [cv2.CAP_DSHOW]
    backends: list[int] = []
    if hasattr(cv2, "CAP_MSMF"):
        backends.append(cv2.CAP_MSMF)
    if hasattr(cv2, "CAP_V4L2"):
        backends.append(cv2.CAP_V4L2)
    backends.append(cv2.CAP_ANY)
    return backends


def _open_camera_quiet(index: int) -> Optional[cv2.VideoCapture]:
    for be in _preferred_backends():
        cap = cv2.VideoCapture(index, be)
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
            return cap
        cap.release()
    return None


def _open_camera(index: int) -> Optional[cv2.VideoCapture]:
    """Open camera with native log suppression (used at preview/record start)."""
    with _quiet_native_logs():
        return _open_camera_quiet(index)


class CompositeCapture:
    def __init__(
        self,
        monitor_index: int = 1,
        camera_index: int = 0,
        layout: str = LAYOUTS[0],
        out_size: tuple[int, int] = (1920, 1080),
        include_camera: bool = True,
    ):
        self.monitor_index = monitor_index
        self.camera_index = camera_index
        self.layout = layout
        self.out_w, self.out_h = out_size
        self.include_camera = include_camera
        self._sct = None
        self._cap: Optional[cv2.VideoCapture] = None
        self._monitor_dict = None
        self._last_cam: Optional[np.ndarray] = None
        self.camera_ok = False

    def open(self) -> None:
        self._sct = _make_mss()
        mons = self._sct.monitors
        if self.monitor_index < 0 or self.monitor_index >= len(mons):
            self.monitor_index = 1 if len(mons) > 1 else 0
        self._monitor_dict = mons[self.monitor_index]
        if self.include_camera and self.layout != "Screen only":
            self._cap = _open_camera(self.camera_index)
            self.camera_ok = self._cap is not None
        else:
            self._cap = None
            self.camera_ok = False

    def close(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
        if self._sct is not None:
            try:
                self._sct.close()
            except Exception:
                pass
            self._sct = None

    def grab(self) -> np.ndarray:
        """Return BGR uint8 frame at out size."""
        screen = self._grab_screen()
        cam = self._grab_cam() if self.include_camera else None
        return compose(screen, cam, self.layout, self.out_w, self.out_h)

    def _grab_screen(self) -> np.ndarray:
        assert self._sct is not None and self._monitor_dict is not None
        shot = self._sct.grab(self._monitor_dict)
        img = np.asarray(shot, dtype=np.uint8)
        return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def _grab_cam(self) -> Optional[np.ndarray]:
        if self._cap is None:
            return self._last_cam
        ok, frame = self._cap.read()
        if ok and frame is not None:
            self._last_cam = frame
            return frame
        return self._last_cam


def compose(
    screen_bgr: np.ndarray,
    cam_bgr: Optional[np.ndarray],
    layout: str,
    out_w: int,
    out_h: int,
) -> np.ndarray:
    if layout == "Camera only":
        if cam_bgr is None:
            blank = np.zeros((out_h, out_w, 3), dtype=np.uint8)
            cv2.putText(
                blank,
                "No camera",
                (out_w // 2 - 80, out_h // 2),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (180, 180, 180),
                2,
                cv2.LINE_AA,
            )
            return blank
        return _fit(cam_bgr, out_w, out_h)

    if layout == "Screen only" or cam_bgr is None:
        return _fit(screen_bgr, out_w, out_h)

    if layout == "Side by side":
        half = out_w // 2
        left = _fit(screen_bgr, half, out_h)
        right = _fit(cam_bgr, out_w - half, out_h)
        canvas = np.zeros((out_h, out_w, 3), dtype=np.uint8)
        canvas[:, :half] = left
        canvas[:, half:] = right
        return canvas

    # PiP layouts
    base = _fit(screen_bgr, out_w, out_h)
    pip_w = max(160, out_w // 5)
    pip_h = max(90, out_h // 5)
    pip = _fit(cam_bgr, pip_w, pip_h)
    bordered = cv2.copyMakeBorder(pip, 2, 2, 2, 2, cv2.BORDER_CONSTANT, value=(40, 200, 255))
    ph, pw = bordered.shape[:2]
    margin = max(12, out_w // 80)
    if "top-right" in layout:
        y0, x0 = margin, out_w - pw - margin
    else:
        y0, x0 = out_h - ph - margin, out_w - pw - margin
    y1, x1 = y0 + ph, x0 + pw
    base[y0:y1, x0:x1] = bordered
    return base


def _fit(img: np.ndarray, tw: int, th: int) -> np.ndarray:
    """Letterbox scale to target size (no stretch distortion)."""
    h, w = img.shape[:2]
    if w == 0 or h == 0:
        return np.zeros((th, tw, 3), dtype=np.uint8)
    scale = min(tw / w, th / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((th, tw, 3), dtype=np.uint8)
    x0 = (tw - nw) // 2
    y0 = (th - nh) // 2
    canvas[y0 : y0 + nh, x0 : x0 + nw] = resized
    return canvas


# Output resolution presets (name -> w,h). "Match monitor" handled in UI.
RESOLUTIONS = {
    "1280×720 (HD)": (1280, 720),
    "1600×900": (1600, 900),
    "1920×1080 (Full HD)": (1920, 1080),
    "2560×1440 (QHD)": (2560, 1440),
    "Match source (capped 1080p)": (0, 0),  # special
}

FPS_CHOICES = (15, 24, 30, 45, 60)
