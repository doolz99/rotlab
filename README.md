# RotLab

A shared hub for a VEGAS video project between two PCs: a media library for the project folder (video, audio, images, graphics, renders, project files), notes and tags on files, project-file history, chat, a log of what changed, uploads from a phone, and file sync between the PCs (Syncthing, set up automatically).

## Invite a friend (easiest)

In RotLab: **Sync** menu → **Make invite file**. A file called *Join (your name)'s RotLab.cmd* appears in your Downloads. Send it to your friend (Discord is fine). They double-click it (if Windows warns about it, click **Run** / **More info → Run anyway**), type their name, and click **Install**. RotLab installs and links with your PC by itself.

## Install (Windows)

Open **PowerShell** (Start menu → type `powershell` → Enter), paste this line and press Enter:

```powershell
irm https://raw.githubusercontent.com/doolz99/rotlab/main/install.ps1 | iex
```

That downloads RotLab into `C:\VegasProject\_hub\app` and starts the setup:

1. If Python isn't installed, it offers to install it for you.
2. Type your name, leave everything ticked, and click **Install**.
3. To link with the other PC: **Sync** menu → paste their invite code → **Join**. They click **Accept**.

Both PCs should use the same project folder path (`C:\VegasProject`) so VEGAS finds the media on both.

To install somewhere else, run `$env:ROTLAB_DIR = 'D:\MyProject'` first, then the line above.

## Updates

RotLab checks this repository every few hours and installs new versions by itself, and sync passes them to the other PC too. You can turn this off in **File → Settings**, or check right away from **Help → About**.

## What's in here

- `install.ps1`: the one-line installer
- `app/`: the program (`hub.py`), its window (`ui.html`), the phone upload page (`phone.html`), the setup (`Install RotLab.cmd` / `.pyw`), and `manifest.json` (current version, used for updates)

Settings live in `%APPDATA%\VegasHub` on each PC. Shared data (chat, notes, log, history) lives in the project's `_hub` folder.
