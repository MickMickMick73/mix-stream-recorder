# MiX Stream Recorder

**Simple local screen + webcam recorder.** One lean MP4. No account. No watermark. No cloud.

Built for the days you want OBS’s *result* without OBS’s *cockpit*.

| | |
|---|---|
| **Platform** | Windows 10/11 (Python) |
| **License** | MIT |
| **Cost** | Free |
| **Telemetry** | None — runs fully offline |

---

## What it does

- Record **monitor** + **plug-in camera** into **one file**
- Layouts: PiP (corners), side-by-side, screen only, camera only
- Controls: **FPS**, **resolution**, **quality** (Lean by default)
- Prefer **hardware encode** (NVENC / AMF / QSV) when available → small files, low CPU
- Live preview, timer, size estimate (MB/min)
- Built-in list + **playback** of recordings

**Real-world example:** ~5 minutes of usable quality ≈ **~23 MB** on Lean + NVENC (your mileage varies by motion/resolution).

---

## Requirements

1. **Python 3.10+**  
2. **ffmpeg** on PATH  
   ```powershell
   winget install Gyan.FFmpeg
   ```
   Then open a **new** terminal so PATH updates.

---

## Install & run

```powershell
git clone https://github.com/MickMickMick73/mix-stream-recorder.git
cd mix-stream-recorder
python -m pip install -r requirements.txt
python app.py
```

Or double-click **`run.bat`** (installs deps if needed, then launches).

Recordings land in `recordings/`.

---

## Quality tips (anti-bloat)

| Setting | Suggestion |
|---------|------------|
| Quality | **Lean** for everyday; Balanced if you need sharper text |
| FPS | **30** is enough for desktop/tutorials |
| Resolution | **1080p** sweet spot |
| Encoder | **auto** (uses NVENC etc. when present) |

Avoid **Archive + 60fps + 1440p** unless you need a master archive.

---

## Project layout

```
mix-stream-recorder/
  app.py           # UI
  capture.py       # Screen + camera composite
  encoder.py       # ffmpeg lean H.264 pipe
  smoke_test.py    # Non-GUI smoke
  run.bat          # Windows launcher
  requirements.txt
  recordings/      # Output folder (gitignored)
```

```powershell
python smoke_test.py
```

---

## Privacy

- No analytics, accounts, or network calls from the app itself  
- Files stay on your machine under `recordings/`  
- Camera probe is local only  

---

## Related free tools

If you need full streaming scenes and plugins, use **[OBS Studio](https://obsproject.com/)**.  
If you want a small Windows utility belt (screenshots + capture), try **[ShareX](https://getsharex.com/)**.  

This project is the middle ground: **focused recorder, sensible defaults.**

---

## License

MIT — see [LICENSE](LICENSE).

---

## Credits

**MiX Apps** — built for practical day-to-day capture, not engagement metrics.
