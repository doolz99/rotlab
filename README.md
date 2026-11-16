# RotLab

RotLab now lives at **[normanbatesbmotel-boop/rotlab](https://github.com/normanbatesbmotel-boop/rotlab)**. It started as [doolz99/rotlab](https://github.com/doolz99/rotlab), which now hands updates over to it. Everyone you sync with should be on 5.4 or newer, so they see the same tasks, calendar, inventory, radio and video.

## What's new in 5.x

- **Tasks** (tab): tasks with a deadline, a list of requirements people tick off, priority, an optional project, and any number of people assigned (including yourself). Comments and status (To do / Doing / Done / Cancelled). Tasks due within a week show in the strip at the top.
- **Calendar** (tab): a month view. Task deadlines appear on it automatically; add your own events (one day or several, with a time and notes).
- **Inventory** (tab): places (a room, a shelf, a bag, someone's house) and the things you own, with how many, owner, type and notes. Places can have one level of sub-places (shelves in a cupboard), shown as collapsible branches. Move things between places from the list; it shows who moved them and when.
- **Feedback** (tab, or Help menu): report bugs and suggest ideas, vote +1, reply, and mark them Planned / Done / Won't do.
- **RotRadio** (right column): anyone can add songs (each needs at least 3 tags): drop many files on the radio box at once, tick some and tag them together. One PC picks the songs and everyone hears the same song at the same moment. Mute and volume are per PC; the **Tags** button chooses which tags the radio plays: click a tag's box to go on → off → blocked, and a song with a blocked tag never plays (shared). **⏭ Skip** moves everyone on to the next song; each person gets 3 skips per 10 minutes. Audio files tagged **Music** in Files play on the radio too; their file tags become their radio tags. Songs are kept in `_hub\radio\music` and sync like everything else.
- **Name colours**: click your own name in the people list (or File > My name colour) to pick the colour everyone sees.
- **AFK** button next to your name.
- **Soundboard** (🎺 in the radio box): upload short sounds (up to 30 s, drag and drop works); clicking one plays it for everyone while the radio dips.
- **Broadcast** (Call menu, or hold the 📢 button in the radio box): hold your key (F9 by default; mouse side buttons work too) and everyone hears your microphone while the radio dips. Can work even when RotLab isn't the focused window.
- **Emojis**: 11 animated emojis in chat, comments and notes (the face button next to Say, or type codes like `:grin:`).
- **Show what I'm doing** (File menu, off by default): let others see which program you're using, or the program and its window title, plus "away" after 10 idle minutes.
- **AI automation** (File menu): add your own API key (Anthropic/Claude, or any OpenAI-compatible service such as OpenAI, OpenRouter, Groq, Gemini or a local Ollama). For now it sorts RotRadio's tags into groups (genre, period, mood...) whenever new tags appear. Only tag names are sent; the key stays on your PC and is never synced.
- **Cameras and screen sharing** (Call menu): anyone can turn on a camera (up to **3 cameras in total** across everyone) or share their screen. Video goes peer to peer, set up through RotLab's encrypted Live connection, with public STUN servers (Google, Cloudflare) helping the PCs find each other. It works on most home internet but may not connect on strict school, work or mobile networks. Live must be on (Settings).

A shared hub for a VEGAS video project between two PCs: a media library for the project folder (video, audio, images, graphics, renders, project files), notes and tags on files, project-file history, chat, a log of what changed, uploads from a phone, and file sync between the PCs (Syncthing, set up automatically).

## Invite a friend (easiest)

In RotLab: **Sync** menu → **Make invite file**. A file called *Join (your name)'s RotLab.cmd* appears in your Downloads. Send it to your friend (Discord is fine). They double-click it (if Windows warns about it, click **Run** / **More info → Run anyway**), type their name, and click **Install**. RotLab installs and links with your PC by itself.

Each invite file works **once**: it carries a one-time secret, and your PC only lets in the device that shows it (within a week). Anyone else who asks to join still needs you to click Accept.

## Install (Windows)

Open **PowerShell** (Start menu → type `powershell` → Enter), paste this line and press Enter:

```powershell
irm https://raw.githubusercontent.com/normanbatesbmotel-boop/rotlab/main/install.ps1 | iex
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
