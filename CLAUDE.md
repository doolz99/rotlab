# Working on RotLab

Two friends (doolz99 and normanbatesbmotel-boop) both work on this repo. Both PCs install updates from `main` here.

## Before you start
- `git pull` first, so you start from the newest version and don't overwrite the other person's work.

## Every change that should reach the PCs
1. Make the change in `app/` (`hub.py`, `ui.html`, `phone.html`...). Python standard library only; keep `ui.html` one self-contained page.
2. Raise the version, higher than the current one, in **both** `app/hub.py` (`HUB_VERSION = "x.y"`) and `app/manifest.json` (`"version"`). RotLab only offers a version with a higher number.
3. Put one plain sentence in `app/manifest.json` → `"notes"` saying what changed. It's shown in the "Version x.y is available" bar, so write it for the other person, not for a programmer.
4. If you add a new file to `app/`, add it to `"files"` in `app/manifest.json`, or the PCs won't download it.
5. Test before pushing: `python -c "import ast; ast.parse(open('app/hub.py').read())"`, then run the hub with a throwaway folder (`HUB_ROOT=<temp dir> APPDATA=<temp dir> HUB_NO_BROWSER=1 HUB_NO_MIGRATE=1 HUB_PORT=8811 python app/hub.py --background`) and click through what you changed.
6. Commit with a message that says what it does, then push to `main`.
7. After pushing, set `$version` in `install.ps1` to the new commit's full hash (so new installs get a tested version), commit and push that too.

## Don't undo these (they keep both PCs safe)
- The program runs from `%LOCALAPPDATA%\RotLab\app`, never from inside the synced project folder; `/_hub/app` stays ignored by sync.
- Updates only download; they install when the person clicks **Install and restart**. Help → About keeps older versions to go back to.
- The local server only answers `localhost` / `127.0.0.1` (host and origin checks).
- Never run programs or scripts from the project folder (`RUNNABLE_EXT`), and don't add features that run code or commands that arrive through sync.
- Invite files carry a one-time secret; only that device is let in automatically.
- Phone uploads are off until switched on, for 30 minutes, with a new PIN.
- Anything shown in the page from synced data goes through `esc()`.

## If something goes wrong
- On a PC: Help → About → go back to an older version.
- In the repo: fix forward with a new, higher version number (never lower the number; PCs won't go down).
