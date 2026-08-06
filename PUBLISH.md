# Publish to GitHub (one-time)

`gh` CLI is optional. Easiest path for a **standalone** public repo:

## 1. Create empty repo on GitHub

In the browser: **New repository**

- Name: `mix-stream-recorder` (or whatever you like)
- Public
- **Do not** add README / license / gitignore on GitHub (this folder already has them)

## 2. Push from this folder

```powershell
cd E:\Projects\mix-apps\MiX-Apps-Website\mix-stream-recorder

# if not already a git repo:
git init
git add .
git status
git commit -m "Initial release: MiX Stream Recorder"

git branch -M main
git remote add origin https://github.com/MickMickMick73/mix-stream-recorder.git
git push -u origin main
```

**Live repo:** https://github.com/MickMickMick73/mix-stream-recorder  

Auth: PAT from monorepo `secrets/github-token.txt` (never commit).

## 3. Optional X / site blurb

> Free local screen + webcam recorder. Lean MP4s, no account, no watermark.  
> https://github.com/MickMickMick73/mix-stream-recorder

## Notes

- User recordings under `recordings/` are **gitignored** — don’t force-add them.
- This folder is self-contained; it does not need the rest of MiX-Apps-Website to run.
