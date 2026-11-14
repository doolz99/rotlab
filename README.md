# RotLab

A shared hub for a VEGAS video project between two PCs: a media library for the project folder (video, audio, images, graphics, renders, project files), notes and tags on files, project-file history, chat, a log of what changed, uploads from a phone, and file sync between the PCs (Syncthing, set up automatically).

## Invite a friend (easiest)

In RotLab: **Sync** menu → **Make invite file**. A file called *Join (your name)'s RotLab.cmd* appears in your Downloads. Send it to your friend (Discord is fine). They double-click it (if Windows warns about it, click **Run** / **More info → Run anyway**), type their name, and click **Install**. RotLab installs and links with your PC by itself.

Each invite file works **once**: it carries a one-time secret, and your PC only lets in the device that shows it (within a week). Anyone else who asks to join still needs you to click Accept.

## Install (Windows)

Open **PowerShell** (Start menu → type `powershell` → Enter), paste this line and press Enter:

```powershell
irm https://raw.githubusercontent.com/doolz99/rotlab/main/install.ps1 | iex
```

That downloads a tested version of RotLab into this PC's own app folder (`%LOCALAPPDATA%\RotLab\app`) and starts the setup. The project folder is `C:\VegasProject`. The program is kept outside it on purpose, so nobody you sync with can change the code that runs on your PC.

1. If Python isn't installed, it offers to install it for you.
2. Type your name, leave everything ticked, and click **Install**.
3. To link with the other PC: **Sync** menu → paste their invite code → **Join**. They click **Accept**.

Both PCs should use the same project folder path (`C:\VegasProject`) so VEGAS finds the media on both.

To install somewhere else, run `$env:ROTLAB_DIR = 'D:\MyProject'` first, then the line above.

## Updates

RotLab checks this repository every few hours. When there's a new version it downloads it and shows a bar with what changed; nothing is installed until you click **Install and restart**. Sync never carries the program between PCs. Check right away from **Help → About**, or turn checking off in **File → Settings**.

## Safety notes

- The program runs from `%LOCALAPPDATA%\RotLab\app`, outside the synced folder (older installs move there by themselves).
- The window only answers this PC (`localhost`), and only to requests that use that name.
- **Upload from phone** is off until you turn it on; it switches off after 30 minutes and gets a new PIN each time. Use it on your own Wi-Fi or hotspot.
- RotLab never runs programs or scripts (.exe, .cmd, .ps1, ...) from the project folder; it shows them in Explorer instead.
- Everything depends on the GitHub account that owns this repo, so keep two-factor sign-in turned on for it.

## What's in here

- `install.ps1`: the one-line installer
- `app/`: the program (`hub.py`), its window (`ui.html`), the phone upload page (`phone.html`), the setup (`Install RotLab.cmd` / `.pyw`), and `manifest.json` (current version, used for updates)

Settings live in `%APPDATA%\VegasHub` on each PC, the program in `%LOCALAPPDATA%\RotLab\app`. Shared data (chat, notes, log, history) lives in the project's `_hub` folder.
