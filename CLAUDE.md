# RotLab: notes for Claude (read this first)

RotLab is a small Windows app two friends use to make things together (VEGAS video, FL Studio music, art, 3D).
**This repo, doolz99/rotlab, is the only home of RotLab.** Both people (doolz99 and normanbatesbmotel-boop, a
collaborator here) push to `main`, and both PCs get their updates from `main` of this repo. Don't point updates
anywhere else, and don't work from a fork.

## What it is
- `app/hub.py`: a Python (standard library only) server on `localhost:8765` that does everything: the project
  library, sync (Syncthing), chat, feeds, uploads, previews, tasks, radio... State shared between the PCs is
  per-user JSONL in the synced `_hub/` folder of the project (`C:\VegasProject`), which Syncthing copies.
- `app/ui.html`: the whole window, one self-contained page (retro dark Windows 95 look). `app/phone.html`: phone uploads.
- `Install RotLab.pyw` / `install.ps1`: setup. The program lives in `%LOCALAPPDATA%\RotLab\app` on each PC.
- Features: projects of any type, files with previews and comments, Board (requests), Outline, Library (Shared)
  with linking, Find online (Openverse, Poly Haven, Pixabay, GIPHY), project-file dependency check, render
  detection, storage modes (previews only / everything), phone upload, live chat (encrypted relay), Tasks,
  Calendar, Inventory, Feedback, RotRadio, cameras and screen sharing, optional AI tag sorting (own API key).

## How to make a change that reaches both PCs
1. `git pull` first, so you start from the newest version and don't overwrite the other person's work.
2. Make the change in `app/`. Python standard library only; keep `ui.html` one self-contained page; keep the look.
3. Raise the version, higher than the current one, in **both** `app/hub.py` (`HUB_VERSION = "x.y"`) and
   `app/manifest.json` (`"version"`). PCs only ever install a higher number, so never lower it, and never reuse one.
4. One plain sentence in `app/manifest.json` → `"notes"` saying what changed. It shows in the
   "Version x.y is available" bar, so write it for the other person, not for a programmer.
5. A new file in `app/` must be added to `"files"` in `app/manifest.json`, or the PCs won't download it.
6. Test before pushing: `python -c "import ast; ast.parse(open('app/hub.py').read())"`, then run a throwaway hub
   (`HUB_ROOT=<temp> APPDATA=<temp> HUB_NO_BROWSER=1 HUB_NO_MIGRATE=1 HUB_PORT=8811 python app/hub.py --background`)
   and try what you changed. Two hubs on one temp folder (different `APPDATA` and `HUB_PORT`) act as two people.
7. Commit with a message that says what it does, push to `main`.
8. Then set `$version` in `install.ps1` to that commit's full hash (new installs get a tested version), commit, push.
9. Undoing something: fix forward with a new, higher version that contains the old code. On a PC, an older
   version can be put back from the copies kept in `%APPDATA%\VegasHub\app-backup`.

## Don't undo these (they keep both PCs safe; they came from a security review)
- The program runs from `%LOCALAPPDATA%\RotLab\app`, never from the synced project folder; `/_hub/app` stays
  ignored by sync. Nothing that arrives through sync may be run as code.
- Updates only download; they install when the person clicks **Install and restart**. Updates come only from
  `main` of this repo (`GITHUB_RAW`).
- The local server only answers `localhost` / `127.0.0.1` (Host and Origin checks), against DNS rebinding.
- Never open programs or scripts from the project folder (`RUNNABLE_EXT`); show them in Explorer instead.
- Invite files carry a one-time secret; only that one device is let in automatically.
- Phone uploads are off until switched on, for 30 minutes, with a new PIN each time.
- Anything from synced data shown in the page goes through `esc()`.
- API keys and other secrets stay in the PC's own config (`%APPDATA%\VegasHub\config.json`), never in `_hub/`.

## Decided / tried (so nobody redoes it)
- A floating "TV" desktop widget (4.0–4.2: separate windows, then a clipped window, then a Tauri app) was tried
  and rolled back: too fiddly on Windows. The ideas (TV with presence figures and channels, stubs for things
  waiting on you, chat bar that unfolds, Library/Projects as drawers) can come back **inside the normal window**.
  Mockups: the "Vegas Hub – retro dark mockup" design artifact (boards L, M, N).
- AVI/WMV/MPEG can't play in the window (Edge's player); Windows makes their previews (`shell_previews`).
- Discord: no self-bots or anything against Discord's rules.

## Ideas not built yet
- ffmpeg (downloaded only when needed, ~90 MB): real previews and playable copies for AVI etc.
- Day: a schedule you check in to, a time tracker for all PC time, stats; Together: co-op view, no leaderboard.
- Roles (Artist / Editor / Music) that change the layout and route requests.

## About the people
- doolz99's internet is a phone hotspot: avoid big automatic downloads; ask first.
- Both are not programmers by trade: explain in plain words, no jargon in anything shown in the app.
