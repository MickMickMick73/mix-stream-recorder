"""Non-GUI smoke: imports, ffmpeg, synthetic encode, monitors."""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    errors: list[str] = []
    print("== MiX Stream Recorder smoke ==")

    try:
        import customtkinter  # noqa: F401
        import cv2  # noqa: F401
        import mss  # noqa: F401

        print("OK imports: customtkinter, cv2, mss")
    except Exception as e:
        errors.append(f"imports: {e}")
        print("FAIL imports", e)

    from encoder import (
        EncodeSettings,
        FFmpegPipeWriter,
        estimate_mb_per_minute,
        find_ffmpeg,
        find_ffplay,
        pick_video_encoder,
    )

    try:
        ff = find_ffmpeg()
        print("OK ffmpeg:", ff)
    except Exception as e:
        errors.append(f"ffmpeg: {e}")
        print("FAIL ffmpeg", e)
        return 1

    enc = pick_video_encoder("auto")
    print("OK encoder pick:", enc)
    print("OK ffplay:", find_ffplay())
    print("OK size est Lean 1080p30:", f"{estimate_mb_per_minute('Lean (smallest)', 1920, 1080, 30):.1f} MB/min")

    try:
        from capture import list_monitors

        mons = list_monitors()
        print(f"OK monitors: {len(mons)} -> {[m.name for m in mons]}")
    except Exception as e:
        errors.append(f"monitors: {e}")
        print("FAIL monitors", e)

    # Synthetic 1-second encode
    out = ROOT / "recordings" / "_smoke_test.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    w, h, fps, n = 640, 360, 15, 15
    writer = FFmpegPipeWriter(
        out,
        EncodeSettings(width=w, height=h, fps=fps, quality="Lean (smallest)", encoder_prefer="auto"),
    )
    try:
        writer.start()
        for i in range(n):
            # Moving gradient so encoder has content
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            frame[:, :, 0] = (i * 17) % 255
            frame[:, :, 1] = 80
            frame[:, :, 2] = 40
            x = int((i / n) * (w - 40))
            frame[40:120, x : x + 40] = (0, 220, 255)
            writer.write_frame(frame)
        ok, msg = writer.stop()
        if not ok or not out.is_file():
            errors.append(f"encode: {msg}")
            print("FAIL encode", msg)
        else:
            mb = out.stat().st_size / 1024
            print(f"OK encode: {out.name} {mb:.1f} KB · {msg}")
            # keep smoke file small evidence
    except Exception as e:
        errors.append(f"encode exception: {e}")
        print("FAIL encode exception", e)

    if errors:
        print("SMOKE FAIL:", "; ".join(errors))
        return 1
    print("SMOKE PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
