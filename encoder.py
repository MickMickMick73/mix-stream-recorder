"""Lean ffmpeg encoder — prefers hardware H.264 to keep files small without CPU melt."""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def find_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if path:
        return path
    # Common WinGet shim location
    winget = Path.home() / "AppData/Local/Microsoft/WinGet/Links/ffmpeg.exe"
    if winget.is_file():
        return str(winget)
    raise FileNotFoundError("ffmpeg not found on PATH. Install with: winget install Gyan.FFmpeg")


def find_ffplay() -> Optional[str]:
    path = shutil.which("ffplay")
    if path:
        return path
    winget = Path.home() / "AppData/Local/Microsoft/WinGet/Links/ffplay.exe"
    if winget.is_file():
        return str(winget)
    return None


def _probe_encoder(name: str) -> bool:
    try:
        r = subprocess.run(
            [find_ffmpeg(), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        return name in (r.stdout or "")
    except Exception:
        return False


def pick_video_encoder(prefer: str = "auto") -> str:
    order = {
        "auto": ["h264_nvenc", "h264_amf", "h264_qsv", "h264_mf", "libx264"],
        "nvenc": ["h264_nvenc", "libx264"],
        "amf": ["h264_amf", "libx264"],
        "qsv": ["h264_qsv", "libx264"],
        "cpu": ["libx264"],
    }
    for enc in order.get(prefer, order["auto"]):
        if _probe_encoder(enc):
            return enc
    return "libx264"


# Quality presets: name -> (crf-like quality, bitrate hint for hw, note)
# Lower CRF / lower CQ = larger. Lean defaults fight bloat.
QUALITY_PRESETS = {
    "Lean (smallest)": {"cq": 30, "crf": 28, "preset_cpu": "veryfast", "preset_nv": "p4", "bitrate": "2500k"},
    "Balanced": {"cq": 26, "crf": 23, "preset_cpu": "fast", "preset_nv": "p5", "bitrate": "4500k"},
    "High": {"cq": 22, "crf": 20, "preset_cpu": "medium", "preset_nv": "p6", "bitrate": "8000k"},
    "Archive (large)": {"cq": 18, "crf": 18, "preset_cpu": "slow", "preset_nv": "p7", "bitrate": "12000k"},
}


@dataclass
class EncodeSettings:
    width: int
    height: int
    fps: int
    quality: str = "Balanced"
    encoder_prefer: str = "auto"
    audio: bool = True
    audio_device: Optional[str] = None  # Windows dshow name; None = system default if any


class FFmpegPipeWriter:
    """Write raw BGR24 frames into ffmpeg stdin → efficient MP4."""

    def __init__(self, out_path: Path, settings: EncodeSettings):
        self.out_path = Path(out_path)
        self.settings = settings
        self.encoder = pick_video_encoder(settings.encoder_prefer)
        self.proc: Optional[subprocess.Popen] = None
        self.frames_written = 0
        self._cmd: list[str] = []

    def start(self) -> None:
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        q = QUALITY_PRESETS.get(self.settings.quality, QUALITY_PRESETS["Balanced"])
        w, h, fps = self.settings.width, self.settings.height, self.settings.fps
        ffmpeg = find_ffmpeg()

        cmd = [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            # raw video from stdin
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{w}x{h}",
            "-r",
            str(fps),
            "-i",
            "-",
        ]

        # Optional mic via dshow (Windows) — separate audio thread not required if we skip
        # Audio is recorded separately and remuxed if enabled at stop; keep pure video pipe for reliability.

        vcodec_args: list[str] = []
        if self.encoder == "h264_nvenc":
            vcodec_args = [
                "-c:v",
                "h264_nvenc",
                "-preset",
                q["preset_nv"],
                "-rc",
                "vbr",
                "-cq",
                str(q["cq"]),
                "-b:v",
                q["bitrate"],
                "-maxrate",
                _bump_bitrate(q["bitrate"], 1.5),
                "-bufsize",
                _bump_bitrate(q["bitrate"], 2),
                "-profile:v",
                "high",
                "-pix_fmt",
                "yuv420p",
            ]
        elif self.encoder == "h264_amf":
            vcodec_args = [
                "-c:v",
                "h264_amf",
                "-quality",
                "balanced",
                "-rc",
                "vbr_latency",
                "-qp_i",
                str(q["cq"]),
                "-qp_p",
                str(q["cq"] + 2),
                "-b:v",
                q["bitrate"],
                "-pix_fmt",
                "yuv420p",
            ]
        elif self.encoder == "h264_qsv":
            vcodec_args = [
                "-c:v",
                "h264_qsv",
                "-global_quality",
                str(q["cq"]),
                "-look_ahead",
                "1",
                "-b:v",
                q["bitrate"],
                "-pix_fmt",
                "nv12",
            ]
        elif self.encoder == "h264_mf":
            vcodec_args = [
                "-c:v",
                "h264_mf",
                "-b:v",
                q["bitrate"],
                "-pix_fmt",
                "yuv420p",
            ]
        else:
            vcodec_args = [
                "-c:v",
                "libx264",
                "-preset",
                q["preset_cpu"],
                "-crf",
                str(q["crf"]),
                "-pix_fmt",
                "yuv420p",
            ]

        cmd += vcodec_args
        cmd += [
            "-movflags",
            "+faststart",
            "-an",  # video-only; audio muxed after if needed
            str(self.out_path),
        ]
        self._cmd = cmd
        creation = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            creationflags=creation,
        )
        self.frames_written = 0

    def write_frame(self, frame_bgr) -> None:
        if not self.proc or not self.proc.stdin:
            raise RuntimeError("Encoder not started")
        # frame must be contiguous uint8 HxWx3 BGR
        self.proc.stdin.write(frame_bgr.tobytes())
        self.frames_written += 1

    def stop(self) -> tuple[bool, str]:
        if not self.proc:
            return False, "not started"
        err = ""
        try:
            if self.proc.stdin:
                self.proc.stdin.close()
            try:
                _, stderr = self.proc.communicate(timeout=30)
                if stderr:
                    err = stderr.decode("utf-8", errors="replace").strip()
            except subprocess.TimeoutExpired:
                self.proc.kill()
                return False, "ffmpeg timed out on close"
            code = self.proc.returncode
            ok = code == 0 and self.out_path.is_file() and self.out_path.stat().st_size > 0
            if not ok:
                return False, err or f"ffmpeg exit {code}"
            return True, f"{self.encoder} · {self.frames_written} frames"
        finally:
            self.proc = None

    @property
    def command_preview(self) -> str:
        return " ".join(self._cmd) if self._cmd else ""


def _bump_bitrate(br: str, mult: float) -> str:
    br = br.strip().lower()
    if br.endswith("k"):
        return f"{int(int(br[:-1]) * mult)}k"
    if br.endswith("m"):
        return f"{int(float(br[:-1]) * mult * 1000)}k"
    return br


def estimate_mb_per_minute(quality: str, width: int, height: int, fps: int) -> float:
    """Rough size estimate so the UI can warn about bloat."""
    q = QUALITY_PRESETS.get(quality, QUALITY_PRESETS["Balanced"])
    # base bitrate from preset, scale by pixel count vs 1080p30
    base_kbps = int(q["bitrate"].rstrip("kKmM") or "4500")
    if q["bitrate"].lower().endswith("m"):
        base_kbps *= 1000
    scale = (width * height * fps) / (1920 * 1080 * 30)
    scale = max(0.35, min(scale, 2.5))
    kbps = base_kbps * scale
    return (kbps * 60) / 8 / 1024  # MB/min


def list_recordings(folder: Path) -> list[Path]:
    folder = Path(folder)
    if not folder.is_dir():
        return []
    files = list(folder.glob("*.mp4")) + list(folder.glob("*.mkv"))
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


def play_file(path: Path) -> tuple[bool, str]:
    path = Path(path)
    if not path.is_file():
        return False, "file missing"
    ffplay = find_ffplay()
    if ffplay:
        creation = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        # ffplay needs a window — do not use CREATE_NO_WINDOW for the player
        subprocess.Popen(
            [ffplay, "-autoexit", "-window_title", f"MiX Playback — {path.name}", str(path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True, "ffplay"
    # Fallback: OS default
    try:
        if sys.platform == "win32":
            import os

            os.startfile(str(path))  # type: ignore[attr-defined]
            return True, "system player"
        subprocess.Popen(["xdg-open", str(path)])
        return True, "system player"
    except Exception as e:
        return False, str(e)
