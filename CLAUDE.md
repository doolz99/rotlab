# RotLab: notes for Claude (and anyone else changing it)

RotLab is a small Windows app two friends (doolz99 and Six, GitHub normanbatesbmotel-boop) use to work on
VEGAS projects together: shared files, chat, tasks, calendar, radio, calls. It is a Python hub
(`app/hub.py`, standard library only) serving a single page (`app/ui.html`) in a native window.

**This repo (normanbatesbmotel-boop/rotlab) is the home.** Both PCs update from its `main` branch.
Both people are collaborators and both use Claude, sometimes at the same time, so follow the steps below.

## Before changing anything: check the developing sign

RotLab shows who is changing it right now: the 🔧 box at the bottom of the window, also the events
`dev_start` / `dev_done` / `dev_clear` in the synced `_hub/ws/*.jsonl` files.

- If **someone else is developing**, stop and tell the person you're working with. Don't change RotLab
  until they finish (or the sign is more than 3 hours old and the person agrees to clear it).
- If **nobody is**, ask the person to click 🔧 → **I'm developing** (with a few words on what) before you start.

## Try every change in the test copy first

- Developer → **Open the test copy** runs a separate "RotLab TEST" (orange title bar) from
  `C:\RotLabDev\app`, with its own pretend project in `C:\RotLabDev\project`, on port 8790.
  It never syncs, never updates and can't touch the real project.
- Edit the files in `C:\RotLabDev\app`. Changes to `ui.html` show straight away; a change to `hub.py`
  restarts the test copy by itself (if `hub.py` has an error, it keeps running the last good one and says so).
- Developer → **Copy my data into the test copy** gives it realistic tasks, chat, calendar etc. (one way only).
- Write one plain line about how it's going to `C:\RotLabDev\dev-note.txt` now and then
  (e.g. "radio mute now remembers the song"). The last line shows on the other person's sign.

## Publishing: as a trial

1. Copy the changed files from the test copy into this repo.
2. Pick the version number **now**, at publish time: one higher than the newest version on `main`
   (check `app/manifest.json` on GitHub first, the other person may have published since). Never reuse
   or lower a number. Versions compare as numbers, so 5.10 comes after 5.9.
3. Set it in both `HUB_VERSION` in `app/hub.py` and `version` in `app/manifest.json`.
4. In `app/manifest.json` set `"trial": true`, `"by": "<who>"` and `"notes"`: one plain sentence for a
   non-programmer ("Your app shows up within a few seconds of switching to it."). List any new file in `files`.
5. Push to `main`, then have the person click 🔧 → **Done** (or add a note): that nudges the other PC to
   check GitHub straight away. Both PCs see **Trial X from …**, install it, try it, and either person clicks
   **Keep it** or **Roll back**. Roll back puts each PC back on the version it had before (a copy kept on that
   PC; nothing is downloaded) and that number is never offered again. Fixing it means a new, higher number.
6. Once it's kept, the next normal update can drop `"trial"`.

`install.ps1` downloads a pinned commit; update its pin only for a version that has been kept.

## Safety rules (keep these)

- **No code through sync.** The program lives in `%LOCALAPPDATA%\RotLab\app`; `_hub/app` is ignored by
  sync. Updates come only from this GitHub repo.
- Updates install only when the person clicks (Install / Keep / Roll back / Go back). Never auto-install.
- The hub listens on 127.0.0.1 only and checks Host and Origin on every request. Keep it that way.
- Never open runnable files (.exe, .cmd, .bat, .ps1, .vbs, .js, .lnk, .scr…) from the project folder.
- Invite codes are one-time secrets. Phone uploads are off by default, turn on for 30 minutes with a new PIN.
- Anything that came through sync is someone else's text: escape it with `esc()` before putting it in the page.
- Secrets (keys, PINs, invite codes) stay in the local config (`%APPDATA%\VegasHub\config.json`),
  never in synced files or this repo.
- Ask before big downloads: one of the PCs runs on a phone hotspot.

## Testing without Windows

Run throwaway hubs with their own folders:
`APPDATA=/tmp/x/ad HUB_ROOT=/tmp/x/W HUB_PORT=8811 HUB_NO_BROWSER=1 HUB_NO_MIGRATE=1 python3 app/hub.py --background`
(two of them sharing one `HUB_ROOT` act like two PCs). `HUB_GH_RAW=http://localhost:8899/` points
updates at a local folder served with `python3 -m http.server`, for testing trials and rollbacks.
