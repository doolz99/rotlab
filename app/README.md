# RotLab

One window for your shared VEGAS project: a media library for the project folder, notes and tags on files, project history, chat, and a log of what changed. The folder stays in sync between both PCs.

## The window
- **Left:** Video · Audio · Images · Graphics · Renders · Project · Inbox, with how many files are in each.
- **Middle:** the files, newest first, with a thumbnail, length, tags, who added them and how many notes they have. Click a file to preview it, tag it, read and add notes, open it, or show it in its folder. Double-click opens it.
- **Project (.veg) files:** **History...** lists every save (who and when). **Restore** brings an older one back, and the current one is kept too.
- **Right:** who's here (e.g. "Sam: in VEGAS, project.veg"), then **Chat | Log**.
  - **Chat:** messages, plus notes people add to files.
  - **Log:** what was added, changed, renamed, deleted, saved and uploaded, with "new since you were last here". Click a file name to jump to it. Files the other person deleted have a **Restore** link.
- **Find** (top right) searches names, tags and notes.
- A red bar warns you if you both have the same project open in VEGAS.

## Adding files
- **Add files...** (or Ctrl+O), or **drag files onto the window**. You can add a note for the batch, a note per file, tags, and pick where they go (automatic = sorted by type, video and photos into a folder per day).
- **Inbox:** drop anything into the project's `Inbox` folder in Explorer, and it gets sorted automatically. Each PC sorts its own Inbox.
- **From your phone:** Phone menu → Upload from phone. Open the address on your phone, enter the PIN, pick files, and add a note and tags.

## Sync
- **Sync** menu → link with your friend (Invite → send code → they Join → you Accept).
- Chat and notes usually arrive within seconds; big files take as long as they take.

## Setting it up on a new PC
1. Easiest: run the one-line installer from https://github.com/doolz99/rotlab in PowerShell. (If you use a zip instead: right-click it → Properties → tick Unblock before unzipping.)
2. Files end up in `C:\VegasProject\_hub\app\` (use the same path on both PCs).
3. Double-click **Install RotLab.cmd**. If Python is missing it offers to install it for you, then opens the installer.
4. Type your name, leave everything ticked, click **Install**. File sync is set up for you; nothing else to download.
5. Join your friend: **Sync** menu → paste their invite code → **Join**.

## Updates
RotLab checks GitHub (doolz99/rotlab) every few hours and installs new versions by itself. Also, new versions of `hub.py`, `ui.html` or `phone.html` arriving in `_hub\app` (from either PC) install themselves. The window reloads, or the hub restarts when nobody is using it.

## Where things live
- `_hub\` inside the project: chat, notes, log, presence, project history (shared via sync).
- `%APPDATA%\VegasHub\`: your name and settings (this PC only), plus `hub.log` for troubleshooting.
