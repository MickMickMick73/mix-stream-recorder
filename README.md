# MiX Stream Recorder

### Record your screen (and webcam) into **one small video file**.

Free · Windows · No account · No watermark · No cloud nonsense

---

## 👉 Do this (normal humans)

### 1. Download the app

**[⬇ Download MiX Stream Recorder (ZIP)](https://github.com/MickMickMick73/mix-stream-recorder/releases/latest/download/MiX-Stream-Recorder-Windows.zip)**

*(If that fails, open [Releases](https://github.com/MickMickMick73/mix-stream-recorder/releases/latest) and click the `.zip` file.)*

### 2. One-time free setup (only the first time on a PC)

You need two free tools Windows does not include:

| Install | What to do |
|--------|------------|
| **Python** | [Download Python](https://www.python.org/downloads/) → run installer → **tick “Add python.exe to PATH”** → Install |
| **ffmpeg** | Open **PowerShell** and run: `winget install Gyan.FFmpeg` then **close and reopen** any windows |

### 3. Run it

1. Unzip the download anywhere (Desktop is fine)
2. Double-click **`run.bat`**
3. Click **Start preview** → **Record** → **Stop** when done

Your videos appear in the **`recordings`** folder next to the app.

**That’s the whole product.** You can close this GitHub page and never come back unless you want an update.

---

## What it does (in plain English)

| Feature | Meaning |
|--------|---------|
| Screen capture | Records a monitor (or both) |
| Webcam / plug-in cam | Optional face cam on top (picture-in-picture) or side-by-side |
| One file out | Saves a normal **MP4** you can play anywhere |
| Small files | “Lean” quality keeps size down (example: ~5 min ≈ ~23 MB) |
| Settings | FPS, resolution, quality — optional knobs, sensible defaults |
| Playback | Built-in list + play of what you just made |

**Not** a Twitch streamer suite. **Not** OBS. Just “hit record, get a video.”

---

## You do **not** need

- Git  
- A GitHub account  
- To understand any of the files listed below on this page  
- To “clone” anything  

GitHub is only the **download shelf**. The app runs on **your PC**.

---

## Troubleshooting (short)

| Problem | Fix |
|--------|-----|
| `python` not found | Reinstall Python and tick **Add to PATH** |
| Recording fails / encoder error | Install ffmpeg (`winget install Gyan.FFmpeg`), then open a **new** window and run `run.bat` again |
| No camera | Fine — pick **Screen only**, or plug cam in and hit **Rescan devices** |
| Black preview | Click **Start preview**; allow camera if Windows asks |

---

## Privacy

- Runs **offline**
- No login
- Videos stay in your `recordings` folder
- We don’t get a copy of your screen

---

## For developers only (ignore if you just want the app)

```text
git clone https://github.com/MickMickMick73/mix-stream-recorder.git
cd mix-stream-recorder
python -m pip install -r requirements.txt
python app.py
python smoke_test.py
```

Source layout: `app.py` (UI), `capture.py`, `encoder.py`, `run.bat`.  
License: [MIT](LICENSE).

Related: [OBS Studio](https://obsproject.com/) (full studio) · [ShareX](https://getsharex.com/) (Windows utility belt).

---

**MiX Apps** — useful tools, not engagement bait.  
Friendly landing page: **https://mickmickmick73.github.io/mix-stream-recorder/**
