#!/usr/bin/env python3
"""
RotLab (Vegas Project Hub)
--------------------------
One window for a shared VEGAS project:

  * Media library: Video / Audio / Images / Graphics / Renders / Project, with notes and tags per file
  * Inbox: drop anything in, it gets sorted into the right folder
  * Uploads from the PC or a phone, with a note and tags
  * Project history: every save of a .veg is kept, restore in one click
  * Who's here (and who has which project open in VEGAS), chat, and a log of what changed
  * File sync between the two PCs (Syncthing, managed invisibly)

Everything shared is stored as small files inside <ProjectFolder>/_hub/ so sync carries it.
Each person only ever writes their OWN log/chat/notes/presence files, so there are no conflicts.

Run:   pythonw hub.py   (opens its own window; http://localhost:8765)
Needs: Python 3.8+ (standard library). Optional: pywebview for a native window.
"""
import csv
import hashlib
import io
import json
import mimetypes
import os
import py_compile
import re
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import webbrowser
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse, quote

HUB_VERSION = "2.1"
PORT = int(os.environ.get("HUB_PORT", "8765"))
APP_DIR = os.path.dirname(os.path.abspath(__file__))
HUB_DIR = os.path.dirname(APP_DIR)  # <Project>/_hub
ROOT = os.path.realpath(os.environ.get("HUB_ROOT") or os.path.dirname(HUB_DIR))  # <Project>
PRESENCE_DIR = os.path.join(HUB_DIR, "presence")
ACTIVITY_DIR = os.path.join(HUB_DIR, "activity")
CHAT_DIR = os.path.join(HUB_DIR, "chat")
NOTES_DIR = os.path.join(HUB_DIR, "notes")
HISTORY_DIR = os.path.join(HUB_DIR, "history")
INBOX = os.path.join(ROOT, "Inbox")
for _d in (PRESENCE_DIR, ACTIVITY_DIR, CHAT_DIR, NOTES_DIR, HISTORY_DIR, INBOX):
    os.makedirs(_d, exist_ok=True)

CATS = ["Video", "Audio", "Images", "Graphics", "Renders", "Project", "Other"]
CAT_EXT = {
    "Video": {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".mts", ".m2ts", ".webm", ".3gp", ".wmv", ".mxf", ".mpg", ".mpeg"},
    "Audio": {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma", ".aif", ".aiff", ".opus"},
    "Images": {".jpg", ".jpeg", ".heic", ".heif", ".dng", ".raw", ".cr2", ".cr3", ".nef", ".arw", ".tif", ".tiff", ".bmp"},
    "Graphics": {".png", ".gif", ".webp", ".svg", ".psd", ".ai", ".eps", ".ttf", ".otf"},
    "Project": {".veg"},
}
RENDER_WORDS = ("render", "export", "preview")
SKIP_EXT = {".sfk", ".sfap0", ".sfvp0", ".bak", ".tmp", ".ini", ".db", ".part"}
PRESENCE_HEARTBEAT = 60
HISTORY_KEEP = 60  # saves kept per project file


# ---------------------------------------------------------------- utilities
def now():
    return time.time()


def slug(name):
    s = re.sub(r"[^a-zA-Z0-9_-]+", "_", name.strip()).strip("_").lower()
    return s or "user"


def is_temp(fn):
    return (".sync-conflict-" in fn or fn.startswith("~syncthing~") or fn.startswith(".syncthing.")
            or fn.endswith(".tmp") or fn.startswith("~$"))


is_conflict = is_temp  # old name


def write_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def rel(path):
    return os.path.relpath(path, ROOT).replace("\\", "/")


def safe_path(relpath):
    p = os.path.realpath(os.path.join(ROOT, (relpath or "").replace("/", os.sep)))
    if os.path.commonpath([p, ROOT]) != ROOT:
        raise ValueError("path outside project")
    return p


def category_of(relpath):
    ext = os.path.splitext(relpath)[1].lower()
    for cat, exts in CAT_EXT.items():
        if ext in exts:
            if cat == "Video" and any(w in relpath.lower() for w in RENDER_WORDS):
                return "Renders"
            return cat
    return "Other"


def clean_name(name):
    name = os.path.basename((name or "").replace("\\", "/"))
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    if not name or is_temp(name):
        name = "upload_%s" % time.strftime("%Y%m%d_%H%M%S")
    stem, ext = os.path.splitext(name)
    return stem[:120] + ext[:10]


def unique_path(folder, name):
    stem, ext = os.path.splitext(name)
    p, n = os.path.join(folder, name), 1
    while os.path.exists(p):
        p = os.path.join(folder, "%s (%d)%s" % (stem, n, ext))
        n += 1
    return p


def read_jsonl_dir(folder):
    out = []
    try:
        names = os.listdir(folder)
    except OSError:
        return out
    for fn in names:
        if not fn.endswith(".jsonl") or is_temp(fn):
            continue
        try:
            with open(os.path.join(folder, fn), "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except Exception:
                            pass  # half-synced last line
        except OSError:
            pass
    out.sort(key=lambda e: e.get("ts", 0))
    return out


# ---------------------------------------------------------------- config (per machine, NOT synced)
def config_file():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, "VegasHub")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "config.json")


CONFIG = {"name": "", "syncthing_url": "http://127.0.0.1:8384", "syncthing_api_key": "",
          "auto_sort": True, "date_folders": True, "phone_uploads": True,
          "folders": {"Video": "Video", "Audio": "Audio", "Images": "Images", "Graphics": "Graphics", "Other": "Other"},
          "read": {"chat": 0, "log": 0}}
CONFIG.update(read_json(config_file(), {}) or {})
CONFIG_LOCK = threading.Lock()


def save_config():
    with CONFIG_LOCK:
        write_json_atomic(config_file(), CONFIG)


def me():
    return CONFIG.get("name") or ""


# ---------------------------------------------------------------- sync engine (Syncthing, managed by the hub)
# The hub either uses a Syncthing the user already installed ("external"), or downloads its own
# copy and runs it invisibly in the background ("built-in"). Pairing, folder sharing and status
# all happen inside the hub - nobody has to open Syncthing's own page.
import base64
import zipfile

ST_DIR = os.path.join(os.path.dirname(config_file()), "syncthing")
ST_EXE = os.path.join(ST_DIR, "syncthing.exe" if os.name == "nt" else "syncthing")
ST_HOME = os.path.join(ST_DIR, "home")
BUILTIN_URL = "http://127.0.0.1:%s" % os.environ.get("HUB_ST_PORT", "8385")
ST_FALLBACK_TAG = "v2.0.15"
IGNORE_DEFAULTS = ["// added by Vegas Hub: skip files VEGAS can rebuild (saves data),",
                   "// and the Inbox, which each PC sorts on its own",
                   "/Inbox", "(?d)*.sfk", "(?d)Thumbs.db", "(?d)desktop.ini"]
IGNORE_REQUIRED = ["/Inbox", "(?d)*.sfk"]

ST = {"mode": None, "url": None, "key": None, "proc": None}  # mode: external | builtin | missing
SYNC = {"installing": False, "progress": 0, "message": "", "error": None}

_LOCAL_SSL = ssl.create_default_context()
_LOCAL_SSL.check_hostname = False
_LOCAL_SSL.verify_mode = ssl.CERT_NONE


def _st_request(method, url, key, body=None, timeout=5):
    host = urlparse(url).hostname or ""
    ctx = _LOCAL_SSL if host in ("127.0.0.1", "localhost", "::1") else None
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"X-API-Key": key}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        raw = r.read().decode("utf-8")
        return json.loads(raw) if raw.strip() else None


def st(method, path, body=None, timeout=5):
    if not ST["url"]:
        raise RuntimeError("sync not running")
    return _st_request(method, ST["url"].rstrip("/") + path, ST["key"], body, timeout)


def st_get(path, key=None):  # kept for compatibility
    return st("GET", path)


def _alive(url, key):
    try:
        _st_request("GET", url.rstrip("/") + "/rest/system/status", key, timeout=3)
        return True
    except Exception:
        return False


def find_external():
    """An already-installed Syncthing (normal install). Returns (url, key) or None."""
    home = os.path.expanduser("~")
    cands = []
    for env in ("LOCALAPPDATA", "APPDATA"):
        if os.environ.get(env):
            cands.append(os.path.join(os.environ[env], "Syncthing", "config.xml"))
    cands += [os.path.join(home, ".local", "state", "syncthing", "config.xml"),
              os.path.join(home, ".config", "syncthing", "config.xml"),
              os.path.join(home, "Library", "Application Support", "Syncthing", "config.xml")]
    for c in cands:
        try:
            gui = ET.parse(c).getroot().find("gui")
            key = CONFIG.get("syncthing_api_key") or gui.findtext("apikey")
            addr = (gui.findtext("address") or "127.0.0.1:8384").strip()
            if not key or ":" not in addr or addr.startswith("/"):
                continue
            hostpart, port = addr.rsplit(":", 1)
            if hostpart in ("", "0.0.0.0", "[::]", "::"):
                hostpart = "127.0.0.1"
            scheme = "https" if (gui.get("tls") or "").lower() == "true" else "http"
            for url in ("%s://%s:%s" % (scheme, hostpart, port),
                        "%s://%s:%s" % ("http" if scheme == "https" else "https", hostpart, port)):
                if _alive(url, key):
                    return url, key
        except Exception:
            pass
    return None


def builtin_key():
    if not CONFIG.get("builtin_key"):
        CONFIG["builtin_key"] = uuid.uuid4().hex + uuid.uuid4().hex[:8]
        save_config()
    return CONFIG["builtin_key"]


def start_builtin(wait=25):
    key = builtin_key()
    if _alive(BUILTIN_URL, key):
        return True
    os.makedirs(ST_HOME, exist_ok=True)
    args = [ST_EXE, "serve", "--home=" + ST_HOME, "--gui-address=" + BUILTIN_URL,
            "--gui-apikey=" + key, "--no-browser"]
    log = open(os.path.join(ST_DIR, "syncthing.log"), "ab")
    flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW
    ST["proc"] = subprocess.Popen(args, cwd=ST_DIR, stdout=log, stderr=subprocess.STDOUT,
                                  stdin=subprocess.DEVNULL, creationflags=flags)
    t0 = now()
    while now() - t0 < wait:
        if _alive(BUILTIN_URL, key):
            return True
        if ST["proc"].poll() is not None:
            return False
        time.sleep(0.5)
    return False


def resolve_sync():
    """Pick which Syncthing to talk to. Safe to call repeatedly."""
    if ST["mode"] in ("external", "builtin") and _alive(ST["url"], ST["key"]):
        return ST["mode"]
    ext = find_external()
    if ext:
        ST.update(mode="external", url=ext[0], key=ext[1])
    elif os.path.isfile(ST_EXE) and start_builtin():
        ST.update(mode="builtin", url=BUILTIN_URL, key=builtin_key())
        try:
            my = st("GET", "/rest/system/status")["myID"]
            if me():
                st("PATCH", "/rest/config/devices/" + my, {"name": "%s's PC" % me()})
        except Exception:
            pass
    else:
        ST.update(mode="missing" if not os.path.isfile(ST_EXE) else "error", url=None, key=None)
    if ST["mode"] in ("external", "builtin"):
        try:
            ensure_project_folder()
        except Exception as e:
            print("folder setup:", e)
    return ST["mode"]


def stop_builtin():
    if ST["mode"] == "builtin":
        try:
            st("POST", "/rest/system/shutdown", timeout=3)
        except Exception:
            pass


# ---- download
def _latest_tag():
    try:
        req = urllib.request.Request("https://api.github.com/repos/syncthing/syncthing/releases/latest",
                                     headers={"User-Agent": "VegasHub", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            tag = json.loads(r.read().decode("utf-8")).get("tag_name")
            if tag and re.match(r"^v\d+\.\d+\.\d+$", tag):
                return tag
    except Exception:
        pass
    try:
        req = urllib.request.Request("https://github.com/syncthing/syncthing/releases/latest", headers={"User-Agent": "VegasHub"})
        with urllib.request.urlopen(req, timeout=15) as r:
            m = re.search(r"/tag/(v\d+\.\d+\.\d+)$", r.geturl())
            if m:
                return m.group(1)
    except Exception:
        pass
    return ST_FALLBACK_TAG


def install_syncthing(progress=None):
    """Download Syncthing for this PC into %APPDATA%\\VegasHub\\syncthing. progress(pct, msg)."""
    def p(pct, msg):
        SYNC["progress"], SYNC["message"] = pct, msg
        if progress:
            progress(pct, msg)
    if os.name != "nt":
        raise RuntimeError("Built-in sync download is for Windows")
    arch = "arm64" if "ARM" in (os.environ.get("PROCESSOR_ARCHITECTURE", "") + os.environ.get("PROCESSOR_ARCHITEW6432", "")).upper() else "amd64"
    p(2, "Finding latest Syncthing version…")
    tag = _latest_tag()
    url = "https://github.com/syncthing/syncthing/releases/download/%s/syncthing-windows-%s-%s.zip" % (tag, arch, tag)
    os.makedirs(ST_DIR, exist_ok=True)
    tmp = os.path.join(ST_DIR, "download.zip.part")
    p(5, "Downloading Syncthing %s…" % tag)
    req = urllib.request.Request(url, headers={"User-Agent": "VegasHub"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if total:
                p(5 + int(85 * got / total), "Downloading Syncthing… %d / %d MB" % (got >> 20, total >> 20))
    p(92, "Unpacking…")
    with zipfile.ZipFile(tmp) as z:
        member = next((n for n in z.namelist() if n.lower().endswith("/syncthing.exe")), None)
        if not member:
            raise RuntimeError("syncthing.exe not found in download")
        with z.open(member) as src, open(ST_EXE + ".new", "wb") as dst:
            while True:
                b = src.read(1 << 20)
                if not b:
                    break
                dst.write(b)
    os.replace(ST_EXE + ".new", ST_EXE)
    os.remove(tmp)
    p(96, "Starting sync…")
    mode = resolve_sync()
    p(100, "Sync ready" if mode in ("builtin", "external") else "Installed, but couldn't start (see syncthing.log)")
    return mode


def install_syncthing_bg():
    if SYNC["installing"]:
        return
    SYNC.update(installing=True, error=None, progress=0, message="Starting…")

    def run():
        try:
            install_syncthing()
        except Exception as e:
            SYNC["error"] = "Download failed: %s" % e
        finally:
            SYNC["installing"] = False
    threading.Thread(target=run, daemon=True).start()


# ---- project folder + pairing
def my_id():
    return st("GET", "/rest/system/status")["myID"]


def project_folder():
    for f in st("GET", "/rest/config/folders"):
        try:
            if os.path.realpath(f["path"]) == ROOT:
                return f
        except Exception:
            pass
    return None


def ensure_ignores(fid):
    try:
        cur = (st("GET", "/rest/db/ignores?folder=" + fid) or {}).get("ignore") or []
        if not cur:
            st("POST", "/rest/db/ignores?folder=" + fid, {"ignore": IGNORE_DEFAULTS})
        else:
            missing = [x for x in IGNORE_REQUIRED if x not in cur]
            if missing:
                st("POST", "/rest/db/ignores?folder=" + fid, {"ignore": cur + missing})
    except Exception as e:
        print("ignores:", e)


def quick_scan(sub):
    """Ask Syncthing to look at a sub-folder right now, so small changes (chat) arrive in seconds."""
    def run():
        try:
            fid = CONFIG.get("folder_id")
            if fid and ST["mode"] in ("external", "builtin"):
                st("POST", "/rest/db/scan?folder=%s&sub=%s" % (fid, urllib.request.quote(sub)), timeout=10)
        except Exception:
            pass
    threading.Thread(target=run, daemon=True).start()


def ensure_project_folder(fid=None):
    """Make sure the project folder is in Syncthing (with the given id, if joining)."""
    f = project_folder()
    if f and (fid is None or f["id"] == fid):
        if CONFIG.get("folder_id") != f["id"] or not SYNC.get("ignores_checked"):
            ensure_ignores(f["id"])
            SYNC["ignores_checked"] = True
        CONFIG["folder_id"] = f["id"]
        return f
    me_id = my_id()
    devices = [{"deviceID": me_id}]
    if f and fid and f["id"] != fid:
        # joining someone else's project: re-create our folder entry with their folder ID
        devices = f.get("devices") or devices
        st("DELETE", "/rest/config/folders/" + f["id"])
    new_id = fid or CONFIG.get("folder_id") or "vegas-" + uuid.uuid4().hex[:10]
    st("PUT", "/rest/config/folders/" + new_id, {
        "id": new_id, "label": os.path.basename(ROOT) or "VegasProject", "path": ROOT,
        "type": "sendreceive", "devices": devices, "fsWatcherEnabled": True, "fsWatcherDelayS": 5,
        "rescanIntervalS": 3600,
        "versioning": {"type": "trashcan", "params": {"cleanoutDays": "14"}},
    })
    ensure_ignores(new_id)
    CONFIG["folder_id"] = new_id
    save_config()
    return st("GET", "/rest/config/folders/" + new_id)


def share_with(device_id, name):
    st("PUT", "/rest/config/devices/" + device_id,
       {"deviceID": device_id, "name": name, "addresses": ["dynamic"], "autoAcceptFolders": False})
    f = ensure_project_folder()
    if not any(d["deviceID"] == device_id for d in f.get("devices", [])):
        f["devices"].append({"deviceID": device_id})
        st("PUT", "/rest/config/folders/" + f["id"], f)


def make_invite():
    f = ensure_project_folder()
    data = {"v": 1, "d": my_id(), "n": me(), "f": f["id"]}
    code = base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).decode().rstrip("=")
    return "VEGASHUB-" + code


def parse_invite(code):
    code = re.sub(r"\s+", "", code or "")
    if code.upper().startswith("VEGASHUB-"):
        code = code[9:]
    try:
        data = json.loads(base64.urlsafe_b64decode(code + "=" * (-len(code) % 4)).decode())
        if not re.match(r"^[A-Z0-9]{7}(-[A-Z0-9]{7}){7}$", data["d"]) or not data.get("f"):
            raise ValueError
        return data
    except Exception:
        raise ValueError("That doesn't look like a valid invite code")


def join_invite(code):
    data = parse_invite(code)
    if data["d"] == my_id():
        raise ValueError("That's your own invite code - send it to your friend instead")
    ensure_project_folder(fid=data["f"])
    share_with(data["d"], "%s's PC" % (data.get("n") or "Friend"))
    return data


def pending_requests():
    try:
        pend = st("GET", "/rest/cluster/pending/devices") or {}
    except Exception:
        return []
    return [{"id": k, "name": v.get("name") or k[:7], "time": v.get("time")} for k, v in pend.items()]


def accept_request(device_id):
    pend = {p["id"]: p for p in pending_requests()}
    name = pend.get(device_id, {}).get("name") or "Friend's PC"
    share_with(device_id, name)


def dismiss_request(device_id):
    st("DELETE", "/rest/cluster/pending/devices?device=" + device_id)


def poll_syncthing():
    mode = ST["mode"]
    if mode not in ("external", "builtin"):
        if os.path.isfile(ST_EXE) or find_external():
            mode = resolve_sync()
        if mode not in ("external", "builtin"):
            return {"ok": False, "mode": ST["mode"] or "missing",
                    "error": "File sync isn't set up on this PC" if mode == "missing" else "Sync couldn't start"}
    try:
        me_id = my_id()
        devices = st("GET", "/rest/config/devices")
        conns = (st("GET", "/rest/system/connections") or {}).get("connections", {})
        stats = st("GET", "/rest/stats/device") or {}
        folder = project_folder()
        fstate = None
        if folder:
            s = st("GET", "/rest/db/status?folder=" + folder["id"])
            fstate = {"id": folder["id"], "label": folder.get("label") or folder["id"],
                      "state": s.get("state"), "needBytes": s.get("needBytes", 0), "needFiles": s.get("needFiles", 0)}
        devs = []
        for d in devices:
            if d["deviceID"] == me_id:
                continue
            c = conns.get(d["deviceID"], {})
            comp = None
            shared = bool(folder and any(x["deviceID"] == d["deviceID"] for x in folder.get("devices", [])))
            if shared:
                try:
                    comp = st("GET", "/rest/db/completion?folder=%s&device=%s" % (folder["id"], d["deviceID"])).get("completion")
                except Exception:
                    pass
            devs.append({"id": d["deviceID"], "name": d.get("name") or d["deviceID"][:7],
                         "connected": bool(c.get("connected")), "shared": shared,
                         "lastSeen": stats.get(d["deviceID"], {}).get("lastSeen"), "completion": comp})
        return {"ok": True, "mode": ST["mode"], "devices": devs, "folder": fstate,
                "pending": pending_requests(), "gui": ST["url"]}
    except Exception as e:
        ST["mode"] = None  # re-resolve next time
        return {"ok": False, "mode": "error", "error": "Can't reach sync (%s)" % e.__class__.__name__}



# ---------------------------------------------------------------- shared logs (each person appends to their own file)
APPEND_LOCK = threading.Lock()


def append_jsonl(folder, entry):
    entry.setdefault("id", uuid.uuid4().hex[:12])
    entry.setdefault("ts", now())
    entry.setdefault("user", me())
    path = os.path.join(folder, slug(me() or "user") + ".jsonl")
    with APPEND_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    quick_scan(rel(folder))
    return entry


def log_event(etype, **data):
    if not me():
        return None
    data["type"] = etype
    return append_jsonl(ACTIVITY_DIR, data)


LOG_TYPES = {"files", "saved", "upload", "note", "restore", "joined", "sync_join", "sync_accept", "updated", "sorted"}


def all_log():
    return [e for e in read_jsonl_dir(ACTIVITY_DIR) if e.get("type") in LOG_TYPES]


def all_chat():
    return read_jsonl_dir(CHAT_DIR)


# ---------------------------------------------------------------- notes + tags per file
def notes_index():
    """-> (notes_by_path {path: [note,...]}, tags_by_path {path: [tags]})  following renames/moves."""
    notes, tags = {}, {}
    for e in read_jsonl_dir(NOTES_DIR):
        k = e.get("kind")
        if k == "note" and e.get("file") and e.get("text"):
            notes.setdefault(e["file"], []).append(e)
        elif k == "tags" and e.get("file") is not None:
            tags[e["file"]] = [t for t in (e.get("tags") or []) if isinstance(t, str)][:12]
        elif k == "move" and e.get("from") and e.get("to"):
            f, t = e["from"], e["to"]
            if f in notes:
                notes.setdefault(t, []).extend(notes.pop(f))
            if f in tags:
                tags[t] = tags.pop(f)
        elif k == "delete_note":
            for lst in notes.values():
                lst[:] = [n for n in lst if n.get("id") != e.get("note")]
    return notes, tags


def add_note(file, text, via=None):
    text = (text or "").strip()[:2000]
    if not text:
        return None
    e = append_jsonl(NOTES_DIR, {"kind": "note", "file": file, "text": text, "via": via})
    return e


def set_tags(file, tag_list):
    clean = []
    for t in tag_list or []:
        t = re.sub(r"\s+", " ", str(t)).strip()[:24]
        if t and t not in clean:
            clean.append(t)
    append_jsonl(NOTES_DIR, {"kind": "tags", "file": file, "tags": clean})


def record_move(src, dst):
    append_jsonl(NOTES_DIR, {"kind": "move", "from": src, "to": dst})


# ---------------------------------------------------------------- library scan
LIB = {"items": [], "gen": 0, "sig": None}
LIB_LOCK = threading.Lock()


def scan_library():
    items = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        r = rel(dirpath)
        dirnames[:] = [d for d in dirnames if not d.startswith((".", "~")) and not (r == "." and d in ("_hub", "Inbox"))]
        for fn in filenames:
            if is_temp(fn) or fn.startswith("."):
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext in SKIP_EXT:
                continue
            full = os.path.join(dirpath, fn)
            try:
                st_ = os.stat(full)
            except OSError:
                continue
            p = rel(full)
            items.append({"path": p, "name": fn, "folder": os.path.dirname(p), "cat": category_of(p),
                          "size": st_.st_size, "mtime": st_.st_mtime})
    sig = hashlib.md5(json.dumps([(i["path"], i["size"], int(i["mtime"])) for i in items]).encode()).hexdigest()
    with LIB_LOCK:
        if sig != LIB["sig"]:
            LIB["items"], LIB["sig"] = items, sig
            LIB["gen"] += 1
    return items


def added_by_index():
    """path -> who added it (from upload + file log entries)."""
    who = {}
    for e in all_log():
        if e.get("type") == "upload" or (e.get("type") == "files" and e.get("action") == "added"):
            for f in e.get("files") or []:
                who[f] = e.get("user")
        elif e.get("type") == "files" and e.get("action") == "renamed":
            for pair in e.get("pairs") or []:
                if pair[0] in who:
                    who[pair[1]] = who.pop(pair[0])
    return who


def library(cat=None, q=None):
    with LIB_LOCK:
        items = list(LIB["items"])
    notes, tags = notes_index()
    who = added_by_index()
    counts = {c: 0 for c in CATS}
    for i in items:
        counts[i["cat"]] = counts.get(i["cat"], 0) + 1
    ql = (q or "").strip().lower()
    out = []
    for i in items:
        if ql:
            hay = " ".join([i["path"], " ".join(tags.get(i["path"], []))] +
                           [n.get("text", "") for n in notes.get(i["path"], [])]).lower()
            if not all(w in hay for w in ql.split()):
                continue
        elif cat and i["cat"] != cat:
            continue
        d = dict(i)
        d["tags"] = tags.get(i["path"], [])
        d["notes"] = len(notes.get(i["path"], []))
        d["by"] = who.get(i["path"])
        out.append(d)
    out.sort(key=lambda x: -x["mtime"])
    return {"items": out[:2000], "counts": counts, "gen": LIB["gen"], "inbox": inbox_files_count()}


def file_detail(path):
    full = safe_path(path)
    notes, tags = notes_index()
    st_ = os.stat(full)
    hist = history_list(path) if path.lower().endswith(".veg") else []
    return {"path": path, "name": os.path.basename(full), "cat": category_of(path), "size": st_.st_size,
            "mtime": st_.st_mtime, "notes": notes.get(path, []), "tags": tags.get(path, []),
            "by": added_by_index().get(path), "history": hist[:5], "history_count": len(hist)}


# ---------------------------------------------------------------- where new files go
def auto_dest(name, mtime=None):
    cat = category_of(name)
    if cat == "Project":
        return ROOT
    if cat == "Renders":
        cat = "Video"
    folders = CONFIG.get("folders") or {}
    base = folders.get(cat) or cat
    d = os.path.join(ROOT, base)
    if CONFIG.get("date_folders", True) and cat in ("Video", "Images"):
        d = os.path.join(d, time.strftime("%Y-%m-%d", time.localtime(mtime or now())))
    return d


def dest_folder(dest, name, mtime=None):
    if not dest or dest == "auto":
        return auto_dest(name, mtime)
    return safe_path(dest)


RECENT_WRITES = {k: v for k, v in (CONFIG.get("recent_writes") or {}).items() if now() - v < 600}
# ^ path -> ts: files the hub itself wrote (so the change log doesn't double-report)


def mark_written(relpath):
    RECENT_WRITES[relpath] = now()
    for k in [k for k, t in RECENT_WRITES.items() if now() - t > 600]:
        RECENT_WRITES.pop(k, None)
    CONFIG["recent_writes"] = dict(RECENT_WRITES)
    try:
        save_config()
    except Exception:
        pass


# ---------------------------------------------------------------- uploads (PC and phone share this)
BATCHES = {}  # batch id -> {"files": [...], "bytes": n, "ts": t}
CURRENT_UPLOAD = {"v": None}


def receive_upload(rfile, total, name, dest="auto", lm=None, batch=None, fnote=None):
    """Stream an upload to disk under a temp name sync ignores, then move it into place."""
    name = clean_name(name)
    mt = (int(lm) / 1000.0) if (lm and str(lm).isdigit()) else None
    if mt and not (946684800 < mt < now() + 86400):
        mt = None
    folder = dest_folder(dest, name, mt)
    os.makedirs(folder, exist_ok=True)
    if shutil.disk_usage(folder).free < total + 500 * 1024 * 1024:
        raise IOError("Not enough free space on the PC")
    tmp = os.path.join(folder, "~syncthing~vhupload-%s.tmp" % uuid.uuid4().hex[:12])
    CURRENT_UPLOAD["v"] = {"name": name, "got": 0, "total": total, "ts": now()}
    got = 0
    try:
        with open(tmp, "wb") as f:
            while got < total:
                chunk = rfile.read(min(1024 * 1024, total - got))
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                CURRENT_UPLOAD["v"].update(got=got, ts=now())
        if got != total:
            raise IOError("connection dropped")
        final = unique_path(folder, name)
        os.replace(tmp, final)
        if mt:
            os.utime(final, (mt, mt))
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        CURRENT_UPLOAD["v"] = None
        raise
    CURRENT_UPLOAD["v"] = None
    r = rel(final)
    mark_written(r)
    if fnote:
        add_note(r, fnote)
    if batch:
        b = BATCHES.setdefault(str(batch)[:40], {"files": [], "bytes": 0, "ts": now()})
        b["files"].append(r)
        b["bytes"] += total
    return r


def finish_batch(batch, note=None, tags=None, via="pc"):
    b = BATCHES.pop(str(batch)[:40], None)
    if not b or not b["files"]:
        return 0
    note = (note or "").strip()
    for f in b["files"]:
        if note:
            add_note(f, note, via="upload")
        if tags:
            set_tags(f, tags)
    folders = sorted({os.path.dirname(f) for f in b["files"]})
    log_event("upload", via=via, count=len(b["files"]), bytes=b["bytes"], files=b["files"][:300],
              folder=folders[0] if len(folders) == 1 else "%d folders" % len(folders), note=note[:500], tags=tags or [])
    with LIB_LOCK:
        LIB["sig"] = None
    return len(b["files"])


# ---------------------------------------------------------------- Inbox (local to each PC, sorted automatically)
INBOX_SEEN = {}  # path -> (size, first_seen)


def inbox_files():
    out = []
    for dirpath, dirnames, filenames in os.walk(INBOX):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            if is_temp(fn) or fn.startswith(".") or os.path.splitext(fn)[1].lower() in SKIP_EXT:
                continue
            out.append(os.path.join(dirpath, fn))
    return out


def inbox_files_count():
    try:
        return len(inbox_files())
    except Exception:
        return 0


def sort_inbox(force=False):
    if not (CONFIG.get("auto_sort", True) or force):
        return []
    moved = []
    for full in inbox_files():
        try:
            st_ = os.stat(full)
        except OSError:
            continue
        prev = INBOX_SEEN.get(full)
        INBOX_SEEN[full] = (st_.st_size, prev[1] if prev else now())
        stable = prev and prev[0] == st_.st_size and now() - st_.st_mtime > 10
        if not (stable or force):
            continue
        dest = unique_path(auto_dest(os.path.basename(full), st_.st_mtime), os.path.basename(full))
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(full, dest)
            INBOX_SEEN.pop(full, None)
            moved.append(rel(dest))
        except OSError as e:
            print("inbox move failed:", full, e)
    # tidy empty sub-folders left in the Inbox
    for dirpath, dirnames, filenames in os.walk(INBOX, topdown=False):
        if dirpath != INBOX and not os.listdir(dirpath):
            try:
                os.rmdir(dirpath)
            except OSError:
                pass
    if moved:
        log_event("sorted", count=len(moved), files=moved[:300],
                  folder=sorted({os.path.dirname(m) for m in moved})[0] if len({os.path.dirname(m) for m in moved}) == 1 else "several folders")
        for m in moved:
            mark_written(m)
        with LIB_LOCK:
            LIB["sig"] = None
    return moved


# ---------------------------------------------------------------- project history (.veg saves)
def history_dir_for(relpath):
    return os.path.join(HISTORY_DIR, re.sub(r"[^A-Za-z0-9._-]+", "_", relpath))


def history_list(relpath):
    d = history_dir_for(relpath)
    out = []
    who = {slug(p["user"]): p["user"] for p in read_presence()}
    if me():
        who[slug(me())] = me()
    try:
        names = os.listdir(d)
    except OSError:
        return out
    for fn in names:
        m = re.match(r"^(\d{8}-\d{6})__(.+)\.veg$", fn)
        if not m or is_temp(fn):
            continue
        full = os.path.join(d, fn)
        try:
            size = os.path.getsize(full)
        except OSError:
            continue
        ts = time.mktime(time.strptime(m.group(1), "%Y%m%d-%H%M%S"))
        out.append({"id": fn, "ts": ts, "user": who.get(m.group(2), m.group(2).replace("_", " ")), "size": size, "path": rel(full)})
    out.sort(key=lambda x: -x["ts"])
    return out


LAST_SNAPSHOT_HASH = {}


def snapshot(relpath, reason="saved"):
    """Copy a .veg into history if its content changed. Returns the history entry or None."""
    try:
        full = safe_path(relpath)
        with open(full, "rb") as f:
            data = f.read()
    except (OSError, ValueError):
        return None
    h = hashlib.sha256(data).hexdigest()
    if LAST_SNAPSHOT_HASH.get(relpath) is None:
        prev = history_list(relpath)
        if prev:
            try:
                with open(os.path.join(ROOT, prev[0]["path"]), "rb") as f:
                    LAST_SNAPSHOT_HASH[relpath] = hashlib.sha256(f.read()).hexdigest()
            except OSError:
                pass
    if LAST_SNAPSHOT_HASH.get(relpath) == h:
        return None
    d = history_dir_for(relpath)
    os.makedirs(d, exist_ok=True)
    fn = "%s__%s.veg" % (time.strftime("%Y%m%d-%H%M%S"), slug(me() or "someone"))
    with open(os.path.join(d, fn + ".tmp"), "wb") as f:
        f.write(data)
    os.replace(os.path.join(d, fn + ".tmp"), os.path.join(d, fn))
    LAST_SNAPSHOT_HASH[relpath] = h
    hist = history_list(relpath)
    for old in hist[HISTORY_KEEP:]:
        try:
            os.remove(os.path.join(ROOT, old["path"]))
        except OSError:
            pass
    return {"id": fn, "path": rel(os.path.join(d, fn))}


def restore_history(relpath, hist_id):
    if not re.match(r"^\d{8}-\d{6}__[A-Za-z0-9_-]+\.veg$", hist_id or ""):
        raise ValueError("bad history id")
    src = os.path.join(history_dir_for(relpath), hist_id)
    if not os.path.isfile(src):
        raise ValueError("That saved copy isn't here yet (still syncing?)")
    target = safe_path(relpath)
    if os.path.exists(target):
        snapshot(relpath, "before restore")
    tmp = target + ".restore.tmp"
    shutil.copyfile(src, tmp)
    os.replace(tmp, target)
    mark_written(relpath)
    LAST_SNAPSHOT_HASH.pop(relpath, None)
    snapshot(relpath)
    log_event("restore", file=relpath, version=hist_id)


# ---------------------------------------------------------------- change log from sync's own change events
# Syncthing reports every change it notices on THIS PC ("LocalChangeDetected"), so each hub logs
# exactly what its own person did, and the other person's hub shows it.
WATCH = {"since": None, "start": None, "ready": False, "pending": [], "first": 0, "last": 0,
         "sizes": {}, "known": set(), "veg_mtimes": {}}


def _watch_path_ok(p):
    p = p.replace("\\", "/")
    parts = p.split("/")
    if parts[0] in ("_hub", "Inbox") or any(x.startswith((".", "~")) for x in parts):
        return False
    fn = parts[-1]
    return not is_temp(fn) and os.path.splitext(fn)[1].lower() not in SKIP_EXT


def watch_init():
    with LIB_LOCK:
        items = list(LIB["items"])
    WATCH["known"] = {i["path"] for i in items}
    WATCH["sizes"] = {i["path"]: i["size"] for i in items}


def watch_poll():
    """Pull new disk events from Syncthing. Called by the monitor every few seconds."""
    if ST["mode"] not in ("external", "builtin") or not CONFIG.get("folder_id"):
        return watch_poll_nosync()
    try:
        status = st("GET", "/rest/system/status")
    except Exception:
        return
    if WATCH["start"] != status.get("startTime"):
        WATCH["start"] = status.get("startTime")
        if CONFIG.get("disk_start") == WATCH["start"] and CONFIG.get("disk_since") is not None:
            # only the hub restarted: carry on where we left off
            WATCH["since"] = CONFIG["disk_since"]
        else:
            # Syncthing (re)started: its event numbers start again from 1
            first_ever = CONFIG.get("disk_since") is None
            WATCH["since"] = 0
            WATCH["skip_backlog"] = first_ever
        CONFIG["disk_start"] = WATCH["start"]
    try:
        fstat = st("GET", "/rest/db/status?folder=" + CONFIG["folder_id"])
        if fstat.get("state") == "idle":
            WATCH["ready"] = True
    except Exception:
        pass
    if not WATCH["ready"]:
        return
    try:
        evs = st("GET", "/rest/events/disk?since=%d&timeout=1&limit=1000" % WATCH["since"], timeout=8) or []
    except Exception:
        return
    if not evs:
        if WATCH.get("skip_backlog"):
            WATCH["skip_backlog"] = False
        return
    WATCH["since"] = max(e.get("id", 0) for e in evs)
    CONFIG["disk_since"] = WATCH["since"]
    save_config()
    if WATCH.pop("skip_backlog", False):
        return  # first run: don't log the whole folder as "added"
    for e in evs:
        d = e.get("data") or {}
        if d.get("folder") != CONFIG.get("folder_id") or d.get("type") != "file":
            continue
        p = (d.get("path") or "").replace("\\", "/")
        if not _watch_path_ok(p):
            continue
        if e.get("type") == "RemoteChangeDetected":
            if d.get("action") == "deleted":
                WATCH["known"].discard(p)
            else:
                WATCH["known"].add(p)
                try:
                    WATCH["sizes"][p] = os.path.getsize(os.path.join(ROOT, p))
                except OSError:
                    pass
            continue
        WATCH["pending"].append((d.get("action"), p))
        WATCH["first"] = WATCH["first"] or now()
        WATCH["last"] = now()


def watch_poll_nosync():
    """Without sync running, at least keep .veg history by watching file times."""
    with LIB_LOCK:
        items = list(LIB["items"])
    for i in items:
        if i["cat"] != "Project":
            continue
        old = WATCH["veg_mtimes"].get(i["path"])
        WATCH["veg_mtimes"][i["path"]] = i["mtime"]
        if old is not None and i["mtime"] > old + 1 and i["path"] not in RECENT_WRITES:
            if snapshot(i["path"]):
                log_event("saved", file=i["path"])


def watch_flush(force=False):
    if not WATCH["pending"]:
        return
    if not force and now() - WATCH["last"] < 8 and now() - WATCH["first"] < 40:
        return  # wait until things settle so a big copy becomes one log line
    pend, WATCH["pending"], WATCH["first"] = WATCH["pending"], [], 0
    final = {}
    for action, p in pend:
        final[p] = action
    added, modified, deleted = [], [], []
    for p, action in final.items():
        if action == "deleted":
            if p in WATCH["known"]:
                deleted.append(p)
            WATCH["known"].discard(p)
        else:
            (modified if p in WATCH["known"] else added).append(p)
            WATCH["known"].add(p)
    # pair deletes + adds of the same size/extension into renames / moves
    pairs = []
    for dp in list(deleted):
        dsz = WATCH["sizes"].get(dp)
        for ap in added:
            try:
                asz = os.path.getsize(os.path.join(ROOT, ap))
            except OSError:
                continue
            if dsz is not None and asz == dsz and os.path.splitext(ap)[1].lower() == os.path.splitext(dp)[1].lower():
                pairs.append((dp, ap))
                deleted.remove(dp)
                added.remove(ap)
                break
    for p in added + modified:
        try:
            WATCH["sizes"][p] = os.path.getsize(os.path.join(ROOT, p))
        except OSError:
            pass
    for dp, ap in pairs:
        record_move(dp, ap)
    if pairs:
        log_event("files", action="renamed", count=len(pairs), pairs=[list(x) for x in pairs[:200]],
                  files=[x[1] for x in pairs[:200]], folder=_common_folder([x[1] for x in pairs]))
    # .veg saves -> history + "saved" line
    for p in [x for x in added + modified if x.lower().endswith(".veg")]:
        if p in RECENT_WRITES:
            continue
        snap = snapshot(p)
        log_event("saved", file=p, snapshot=(snap or {}).get("id"))
    added = [p for p in added if not p.lower().endswith(".veg") and p not in RECENT_WRITES]
    modified = [p for p in modified if not p.lower().endswith(".veg") and p not in RECENT_WRITES]
    deleted = [p for p in deleted if p not in RECENT_WRITES]
    for action, lst in (("added", added), ("modified", modified), ("deleted", deleted)):
        groups = {}
        for p in lst:
            groups.setdefault(os.path.dirname(p), []).append(p)
        for folder, files in groups.items():
            log_event("files", action=action, count=len(files), files=files[:300], folder=folder)
    save_config()


def _common_folder(paths):
    ds = sorted({os.path.dirname(p) for p in paths})
    return ds[0] if len(ds) == 1 else "several folders"


def restore_deleted(relpath):
    """Bring back a file the other person deleted, from Syncthing's .stversions trash on this PC."""
    vdir = os.path.join(ROOT, ".stversions", os.path.dirname(relpath.replace("/", os.sep)))
    stem, ext = os.path.splitext(os.path.basename(relpath))
    best = None
    try:
        for fn in os.listdir(vdir):
            if fn == os.path.basename(relpath) or (fn.startswith(stem + "~") and fn.endswith(ext)):
                full = os.path.join(vdir, fn)
                if not best or os.path.getmtime(full) > os.path.getmtime(best):
                    best = full
    except OSError:
        pass
    if not best:
        raise ValueError("No saved copy found on this PC (only files the other person deleted can be restored)")
    target = safe_path(relpath)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    shutil.copy2(best, unique_path(os.path.dirname(target), os.path.basename(target)))
    with LIB_LOCK:
        LIB["sig"] = None


# ---------------------------------------------------------------- local machine: is VEGAS open, with which project?
def detect_vegas():
    if os.name != "nt":
        return None
    try:
        out = subprocess.run(["tasklist", "/v", "/fo", "csv", "/nh"], capture_output=True, text=True,
                             errors="replace", timeout=20, creationflags=0x08000000).stdout
    except Exception:
        return None
    found = None
    for row in csv.reader(io.StringIO(out)):
        if not row:
            continue
        exe = row[0].lower()
        if exe.startswith("vegas") and exe.endswith(".exe"):
            title = row[-1] if row[-1] != "N/A" else ""
            m = re.search(r"([^\\/:*?\"<>|]+\.veg)\b", title, re.I)
            info = {"exe": row[0], "title": title, "project": m.group(1).strip() if m else ""}
            if not found or (info["project"] and not found["project"]):
                found = info
    return found


# ---------------------------------------------------------------- presence
def read_presence():
    out = []
    for fn in os.listdir(PRESENCE_DIR):
        if fn.endswith(".json") and not is_temp(fn):
            p = read_json(os.path.join(PRESENCE_DIR, fn))
            if p and p.get("user"):
                age = now() - p.get("ts", 0)
                p["live"] = "offline" if (p.get("status", {}).get("kind") == "offline" or age > 180) else p["status"].get("kind", "online")
                out.append(p)
    return out


def write_presence(status):
    if me():
        write_json_atomic(os.path.join(PRESENCE_DIR, slug(me()) + ".json"),
                          {"user": me(), "status": status, "ts": now(), "version": HUB_VERSION})
        quick_scan("_hub/presence")


def write_offline_presence():
    write_presence({"kind": "offline", "text": "offline"})


# ---------------------------------------------------------------- self-update
# The app lives inside the synced _hub folder, so new files from either person arrive via sync.
# ui.html / phone.html are read fresh on every request (the window just reloads);
# a new hub.py is checked for errors and then restarted into.
SELF = os.path.abspath(__file__)
SERVER = None
UPDATE = {"pending": False, "version": None}


def file_hash(path):
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return None


START_HASH = file_hash(SELF)


def read_version(path):
    try:
        with open(path, encoding="utf-8") as f:
            m = re.search(r'^HUB_VERSION\s*=\s*"([^"]+)"', f.read(), re.M)
            return m.group(1) if m else "?"
    except OSError:
        return "?"


def check_for_update():
    h = file_hash(SELF)
    if not h or h == START_HASH:
        UPDATE["pending"] = False
        return False
    try:
        py_compile.compile(SELF, cfile=os.path.join(os.path.dirname(config_file()), "check.pyc"), doraise=True)
    except Exception as e:
        print("update ignored, new hub.py has errors:", e)
        return False
    UPDATE["pending"], UPDATE["version"] = True, read_version(SELF)
    return True


def restart(with_window):
    print("restarting into new version", UPDATE.get("version"))
    try:
        write_offline_presence()
    except Exception:
        pass
    for srv in (PHONE.get("server"), SERVER):
        if srv:
            try:
                srv.server_close()
            except Exception:
                pass
    exe = sys.executable
    if os.name == "nt" and exe.lower().endswith("python.exe") and os.path.isfile(exe[:-10] + "pythonw.exe"):
        exe = exe[:-10] + "pythonw.exe"
    args = [exe, SELF] + ([] if with_window else ["--background"])
    flags = 0x00000008 if os.name == "nt" else 0  # DETACHED_PROCESS
    subprocess.Popen(args, cwd=APP_DIR, creationflags=flags)
    os._exit(0)


# ---------------------------------------------------------------- updates from GitHub
# Every few hours, look at the app's GitHub repo. If it has a newer version, download the files into
# _hub/app (window files first, hub.py last); the normal self-update above then restarts into it,
# and sync carries the same files to the other PC.
GITHUB_RAW = os.environ.get("HUB_GH_RAW", "https://raw.githubusercontent.com/doolz99/rotlab/main/app/")
GH = {"checked": 0, "latest": None, "error": None, "busy": False}


def _vtuple(v):
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:4])


def github_check(force=False):
    if GH["busy"] or not (CONFIG.get("github_updates", True) or force):
        return
    if not force and now() - GH["checked"] < 3 * 3600:
        return
    GH["busy"], GH["checked"] = True, now()
    try:
        req = urllib.request.Request(GITHUB_RAW + "manifest.json?t=%d" % int(now()), headers={"User-Agent": "RotLab"})
        with urllib.request.urlopen(req, timeout=20) as r:
            man = json.loads(r.read().decode("utf-8"))
        GH["latest"], GH["error"] = man.get("version"), None
        if _vtuple(man.get("version", "0")) <= _vtuple(HUB_VERSION) or UPDATE.get("pending"):
            return
        files = [f for f in man.get("files", []) if re.match(r"^[A-Za-z0-9 ._-]+$", f) and ".." not in f]
        data = {}
        for f in files:
            req = urllib.request.Request(GITHUB_RAW + quote(f), headers={"User-Agent": "RotLab"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data[f] = r.read()
        if "hub.py" in data:  # never install a broken hub.py
            tmp = os.path.join(os.path.dirname(config_file()), "incoming_hub.py")
            with open(tmp, "wb") as fh:
                fh.write(data["hub.py"])
            py_compile.compile(tmp, cfile=tmp + "c", doraise=True)
        for f in sorted(data, key=lambda x: x == "hub.py"):  # hub.py last
            dst = os.path.join(APP_DIR, f)
            try:
                with open(dst, "rb") as fh:
                    if fh.read() == data[f]:
                        continue
            except OSError:
                pass
            with open(dst + ".tmp", "wb") as fh:
                fh.write(data[f])
            os.replace(dst + ".tmp", dst)
        print("downloaded version", man.get("version"), "from GitHub")
    except Exception as e:
        GH["error"] = "%s" % e.__class__.__name__
        print("github update check:", repr(e))
    finally:
        GH["busy"] = False


def ui_file(name):
    try:
        with open(os.path.join(APP_DIR, name), "r", encoding="utf-8") as f:
            return f.read()
    except OSError:
        return "<h1>%s is missing</h1>" % name


def ui_hash():
    return (file_hash(os.path.join(APP_DIR, "ui.html")) or "")[:12]


# ---------------------------------------------------------------- background monitor
STATE = {"vegas": None, "syncthing": {"ok": False, "error": "starting…"}, "ui_seen": 0, "ui_view": ""}
STATE_LOCK = threading.Lock()


def compute_status(vegas, ui_seen, view):
    if vegas:
        proj = vegas.get("project") or "a project"
        return {"kind": "editing", "text": "in VEGAS, " + proj, "project": vegas.get("project") or ""}
    if now() - ui_seen < 90:
        return {"kind": "hub", "text": "browsing " + (view or "the hub")}
    return {"kind": "online", "text": "online"}


def monitor():
    last_written, last_presence_write, tick = None, 0, 0
    scan_library()
    watch_init()
    while True:
        try:
            if tick % 2 == 0:
                scan_library()
            vegas = detect_vegas() if tick % 2 == 0 else STATE["vegas"]
            with STATE_LOCK:
                STATE["vegas"] = vegas
                ui_seen, view = STATE["ui_seen"], STATE["ui_view"]
            if tick % 2 == 0:
                sort_inbox()
            if me():
                watch_poll()
                watch_flush()
                status = compute_status(vegas, ui_seen, view)
                if status != last_written or now() - last_presence_write > PRESENCE_HEARTBEAT:
                    write_presence(status)
                    last_written, last_presence_write = status, now()
            if tick % 20 == 5:
                threading.Thread(target=github_check, daemon=True).start()
            if tick % 6 == 0 and check_for_update():
                with STATE_LOCK:
                    ui_recent = now() - STATE["ui_seen"] < 120
                if not vegas and not ui_recent:
                    log_event("updated", version=UPDATE["version"]) if me() else None
                    restart(with_window=False)
            if tick % 2 == 0:
                st_ = poll_syncthing()
                with STATE_LOCK:
                    STATE["syncthing"] = st_
        except Exception as e:
            print("monitor error:", repr(e), file=sys.stderr)
        tick += 1
        time.sleep(3)


# ---------------------------------------------------------------- API
def build_state():
    log, chat = all_log(), all_chat()
    people = read_presence()
    with STATE_LOCK:
        s = dict(STATE)
    rd = CONFIG.get("read") or {}
    unread_chat = sum(1 for m in chat if m.get("user") != me() and m.get("ts", 0) > rd.get("chat", 0))
    unread_log = sum(1 for e in log if e.get("user") != me() and e.get("ts", 0) > rd.get("log", 0))
    # warn when both people have the same project open
    clash = None
    mine = (s["vegas"] or {}).get("project")
    if mine:
        for p in people:
            if p["user"] != me() and p["live"] == "editing" and (p["status"].get("project") or "").lower() == mine.lower():
                clash = {"user": p["user"], "project": mine}
    up = CURRENT_UPLOAD["v"]
    if up and now() - up["ts"] > 30:
        up = None
    return {
        "me": me(), "configured": bool(me()), "now": now(), "root": ROOT, "version": HUB_VERSION,
        "ui": ui_hash(), "update": dict(UPDATE), "people": people, "my_vegas": s["vegas"], "clash": clash,
        "chat": chat[-300:], "log": log[-300:], "unread": {"chat": unread_chat, "log": unread_log},
        "read": rd, "lib_gen": LIB["gen"], "inbox": inbox_files_count(), "upload": up,
        "syncthing": s["syncthing"], "sync": dict(SYNC), "phone": phone_state(),
        "settings": {"auto_sort": CONFIG.get("auto_sort", True), "date_folders": CONFIG.get("date_folders", True),
                     "autostart": get_autostart(), "windows": os.name == "nt",
                     "native_window": has_native_window(), "folders": CONFIG.get("folders"),
                     "github_updates": CONFIG.get("github_updates", True)},
        "github": {"latest": GH["latest"], "error": GH["error"], "checked": GH["checked"], "busy": GH["busy"]},
    }


def open_path(full):
    if os.name == "nt":
        os.startfile(full)  # noqa
    else:
        raise ValueError("Opening files only works on Windows")


def handle_post(path, body):
    if path == "/api/setup":
        name = (body.get("name") or "").strip()[:40]
        if not name:
            return 400, {"error": "Please type your name"}
        first = not CONFIG.get("name")
        CONFIG["name"] = name
        for k in ("auto_sort", "date_folders", "github_updates"):
            if k in body:
                CONFIG[k] = bool(body[k])
        if "api_key" in body and body["api_key"] is not None:
            CONFIG["syncthing_api_key"] = str(body["api_key"]).strip()
            ST["mode"] = None
        if "autostart" in body:
            try:
                set_autostart(bool(body["autostart"]))
            except Exception as e:
                print("autostart failed:", e)
        save_config()
        if ST["mode"] == "builtin":
            try:
                st("PATCH", "/rest/config/devices/" + my_id(), {"name": "%s's PC" % name})
            except Exception:
                pass
        if first:
            log_event("joined")
        return 200, {"ok": True}
    if not me():
        return 400, {"error": "not set up"}

    if path == "/api/library":
        return 200, library(body.get("cat"), body.get("q"))
    if path == "/api/file":
        return 200, file_detail(body.get("path", ""))
    if path == "/api/note":
        f = body.get("file", "")
        safe_path(f)
        e = add_note(f, body.get("text", ""))
        if e:
            log_event("note", file=f, text=e["text"][:300])
        return 200, {"ok": bool(e)}
    if path == "/api/tags":
        f = body.get("file", "")
        safe_path(f)
        set_tags(f, body.get("tags") or [])
        return 200, {"ok": True}
    if path == "/api/chat":
        text = (body.get("text") or "").strip()[:2000]
        if text:
            append_jsonl(CHAT_DIR, {"text": text})
            CONFIG.setdefault("read", {})["chat"] = now()
        return 200, {"ok": True}
    if path == "/api/read":
        which = body.get("which")
        if which in ("chat", "log"):
            CONFIG.setdefault("read", {})[which] = now()
            save_config()
        return 200, {"ok": True}
    if path == "/api/view":
        with STATE_LOCK:
            STATE["ui_view"], STATE["ui_seen"] = str(body.get("view", ""))[:30], now()
        return 200, {"ok": True}
    if path == "/api/upload_done":
        n = finish_batch(body.get("batch"), body.get("note"), body.get("tags"), via="pc")
        return 200, {"ok": True, "count": n}
    if path == "/api/history":
        return 200, {"items": history_list(body.get("file", ""))}
    if path == "/api/restore":
        restore_history(body.get("file", ""), body.get("id", ""))
        return 200, {"ok": True}
    if path == "/api/restore_deleted":
        restore_deleted(body.get("file", ""))
        log_event("files", action="restored", count=1, files=[body.get("file", "")], folder=os.path.dirname(body.get("file", "")))
        return 200, {"ok": True}
    if path == "/api/open":
        full = safe_path(body.get("path", ""))
        if not os.path.exists(full):
            return 404, {"error": "That file isn't on this PC (still syncing?)"}
        open_path(full)
        return 200, {"ok": True}
    if path == "/api/reveal":
        full = safe_path(body.get("path", ""))
        if os.name == "nt":
            if os.path.isdir(full):
                os.startfile(full)  # noqa
            else:
                subprocess.Popen(["explorer", "/select,", full])
            return 200, {"ok": True}
        return 501, {"error": "Only works on Windows"}
    if path == "/api/check_updates":
        threading.Thread(target=github_check, kwargs={"force": True}, daemon=True).start()
        return 200, {"ok": True}
    if path == "/api/sort_inbox":
        moved = sort_inbox(force=True)
        return 200, {"ok": True, "count": len(moved)}
    if path == "/api/phone":
        if "enabled" in body:
            CONFIG["phone_uploads"] = bool(body["enabled"])
        if body.get("new_pin"):
            CONFIG["phone_pin"] = ""
        save_config()
        phone_pin()
        if CONFIG.get("phone_uploads", True):
            start_phone_server()
        else:
            stop_phone_server()
        return 200, {"ok": True}
    if path == "/api/sync/install":
        install_syncthing_bg()
        return 200, {"ok": True}
    if path == "/api/sync/invite":
        if resolve_sync() not in ("external", "builtin"):
            return 400, {"error": "Set up sync first"}
        return 200, {"ok": True, "code": make_invite()}
    if path == "/api/sync/join":
        if resolve_sync() not in ("external", "builtin"):
            return 400, {"error": "Set up sync first"}
        data = join_invite(body.get("code", ""))
        log_event("sync_join", friend=data.get("n") or "")
        return 200, {"ok": True, "friend": data.get("n")}
    if path == "/api/sync/accept":
        accept_request(str(body.get("id", "")))
        log_event("sync_accept", device=str(body.get("name", ""))[:60])
        return 200, {"ok": True}
    if path == "/api/sync/dismiss":
        dismiss_request(str(body.get("id", "")))
        return 200, {"ok": True}
    if path == "/api/restart":
        if not check_for_update() and not body.get("force"):
            return 200, {"ok": False, "error": "no update"}
        log_event("updated", version=UPDATE.get("version") or HUB_VERSION)
        threading.Thread(target=lambda: (time.sleep(0.4), restart(with_window=bool(body.get("window", True)))), daemon=True).start()
        return 200, {"ok": True}
    if path == "/api/quit":
        def _q():
            time.sleep(0.5)
            try:
                write_offline_presence()
                stop_builtin()
            finally:
                os._exit(0)
        threading.Thread(target=_q, daemon=True).start()
        return 200, {"ok": True}
    return 404, {"error": "unknown endpoint"}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _origin_ok(self):
        o = self.headers.get("Origin")
        return not o or re.match(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$", o)

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/":
            data = ui_file("ui.html").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        elif u.path == "/api/state":
            q = parse_qs(u.query)
            if q.get("focused", ["0"])[0] == "1":
                with STATE_LOCK:
                    STATE["ui_seen"] = now()
            self._json(200, build_state())
        elif u.path == "/media":
            try:
                self._send_file(safe_path(parse_qs(u.query).get("path", [""])[0]))
            except (ValueError, OSError):
                self._json(404, {"error": "not found"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self._origin_ok():
            return self._json(403, {"error": "bad origin"})
        u = urlparse(self.path)
        if u.path == "/api/upload":
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            try:
                total = int(self.headers.get("Content-Length") or -1)
                if total < 0:
                    return self._json(411, {"error": "Missing file size"})
                saved = receive_upload(self.rfile, total, q.get("name"), q.get("dest", "auto"),
                                       q.get("lm"), q.get("batch"), q.get("fnote"))
                return self._json(200, {"ok": True, "saved": saved})
            except Exception as e:
                return self._json(500, {"error": str(e)})
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            code, obj = handle_post(u.path, body)
        except ValueError as e:
            code, obj = 400, {"error": str(e)}
        except Exception as e:
            code, obj = 500, {"error": str(e)}
        self._json(code, obj)

    def _send_file(self, path):
        size = os.path.getsize(path)
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        start, end, status = 0, size - 1, 200
        m = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        if m and (m.group(1) or m.group(2)):
            status = 206
            if m.group(1):
                start = int(m.group(1))
                if m.group(2):
                    end = min(int(m.group(2)), size - 1)
            else:
                start = max(0, size - int(m.group(2)))
        length = max(0, end - start + 1)
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.end_headers()
        try:
            with open(path, "rb") as f:
                f.seek(start)
                left = length
                while left > 0:
                    chunk = f.read(min(256 * 1024, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass


# ---------------------------------------------------------------- phone uploads (separate server, reachable on the local network)
# The main window's server stays localhost-only. This small second server listens on the network
# so a phone on the same Wi-Fi / hotspot can open a page and upload. Everything needs the PIN.
PHONE_PORT = int(os.environ.get("HUB_PHONE_PORT", "8766"))
PHONE = {"server": None, "error": None, "fails": {}}


def phone_pin():
    if not re.match(r"^\d{6}$", str(CONFIG.get("phone_pin", ""))):
        CONFIG["phone_pin"] = "%06d" % (uuid.uuid4().int % 1000000)
        save_config()
    return CONFIG["phone_pin"]


def lan_ips():
    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))  # no packets are sent; just picks the outgoing interface
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    ok = [ip for ip in ips if re.match(r"^(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)", ip)]
    if not ok:
        ok = [ip for ip in ips if not ip.startswith(("127.", "169.254.", "0."))]
    return sorted(ok, key=lambda ip: (not ip.startswith("192.168."), ip))


class PhoneHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, code, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _check(self):
        ip = self.client_address[0]
        fails = PHONE["fails"].get(ip, [0, 0])
        if fails[0] >= 8 and now() - fails[1] < 300:
            self._json(429, {"error": "Too many wrong PINs - wait 5 minutes"})
            return False
        if self.headers.get("X-Pin", "") == phone_pin():
            PHONE["fails"].pop(ip, None)
            return True
        PHONE["fails"][ip] = [fails[0] + 1, now()]
        self._json(401, {"error": "Wrong PIN"})
        return False

    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            data = ui_file("phone.html").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        elif u.path == "/api/hello":
            if self._check():
                others = [p["user"] for p in read_presence() if p["user"] != me() and p["live"] != "offline"]
                self._json(200, {"ok": True, "pc": me() or "the PC", "free": shutil.disk_usage(ROOT).free,
                                 "online": others, "tags": ["B-roll", "Interview", "Music", "SFX", "Best", "Don't use"]})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if not self._check():
            return
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path == "/api/upload":
            try:
                total = int(self.headers.get("Content-Length") or -1)
                if total < 0:
                    return self._json(411, {"error": "Missing file size"})
                saved = receive_upload(self.rfile, total, q.get("name"), "auto", q.get("lm"), q.get("batch"), q.get("fnote"))
                return self._json(200, {"ok": True, "saved": saved})
            except Exception as e:
                try:
                    return self._json(500, {"error": "Upload failed: %s" % e})
                except Exception:
                    return
        if u.path == "/api/done":
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            except Exception:
                body = {}
            count = finish_batch(body.get("batch"), body.get("note"), body.get("tags"), via="phone")
            return self._json(200, {"ok": True, "count": count})
        self._json(404, {"error": "not found"})


def start_phone_server():
    if PHONE["server"] or not CONFIG.get("phone_uploads", True):
        return
    try:
        srv = ThreadingHTTPServer(("0.0.0.0", PHONE_PORT), PhoneHandler)
        PHONE["server"], PHONE["error"] = srv, None
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        phone_pin()
    except OSError as e:
        PHONE["error"] = "Couldn't open port %d (%s)" % (PHONE_PORT, e.__class__.__name__)


def stop_phone_server():
    srv, PHONE["server"] = PHONE["server"], None
    if srv:
        threading.Thread(target=lambda: (srv.shutdown(), srv.server_close()), daemon=True).start()


def phone_state():
    return {"enabled": bool(CONFIG.get("phone_uploads", True)), "running": bool(PHONE["server"]),
            "error": PHONE["error"], "pin": phone_pin(), "port": PHONE_PORT, "ips": lan_ips()}

def find_app_browser():
    """Edge (on every Windows PC) or Chrome, used in 'app mode' = its own window, no tabs/address bar."""
    if os.name != "nt":
        return None
    cands = []
    for env in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            cands += [os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"),
                      os.path.join(base, "Google", "Chrome", "Application", "chrome.exe")]
    for c in cands:
        if os.path.isfile(c):
            return c
    return None


def open_window():
    url = "http://localhost:%d" % PORT
    exe = find_app_browser()
    if exe:
        try:
            profile = os.path.join(os.path.dirname(config_file()), "window")
            subprocess.Popen([exe, "--app=" + url, "--window-size=1320,900",
                              "--user-data-dir=" + profile, "--no-first-run"])
            return
        except Exception:
            pass
    webbrowser.open(url)


# ---------------------------------------------------------------- start with Windows (registry Run key, no console)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "RotLab"
OLD_RUN_NAMES = ["VegasProjectHub"]


def autostart_command():
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        w = exe[:-10] + "pythonw.exe"
        if os.path.isfile(w):
            exe = w
    return '"%s" "%s" --background' % (exe, os.path.abspath(__file__))


def get_autostart():
    if os.name != "nt":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            for nm in [RUN_NAME] + OLD_RUN_NAMES:
                try:
                    winreg.QueryValueEx(k, nm)
                    return True
                except FileNotFoundError:
                    pass
    except Exception:
        pass
    return False


def set_autostart(on):
    if os.name != "nt":
        return
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        for nm in OLD_RUN_NAMES:
            try:
                winreg.DeleteValue(k, nm)
            except FileNotFoundError:
                pass
        if on:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------- window
def has_native_window():
    try:
        import webview  # noqa: F401  (pip install pywebview)
        return True
    except Exception:
        return False


def run_native_window():
    """Real desktop window (pywebview / Edge WebView2). Blocks until the window is closed."""
    import webview
    webview.create_window("RotLab", "http://localhost:%d" % PORT,
                          width=1320, height=900, min_size=(760, 560))
    webview.start()


def show_window():
    if has_native_window():
        try:
            run_native_window()
            return True
        except Exception as e:
            print("native window failed:", e)
    open_window()  # fallback: Edge/Chrome app-mode window
    return False


def main():
    # pythonw.exe (no console window) has no stdout - send output to a log file instead
    if sys.stdout is None or sys.stderr is None:
        log = open(os.path.join(os.path.dirname(config_file()), "hub.log"), "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
    background = "--background" in sys.argv
    print("RotLab", time.strftime("%Y-%m-%d %H:%M"))
    print("  project folder:", ROOT)
    print("  open:          http://localhost:%d" % PORT)
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
        global SERVER
        SERVER = srv
    except OSError:
        # already running (e.g. started with Windows) -> just open a window onto it
        print("Hub already running - opening window.")
        if not background:
            show_window()
        return
    threading.Thread(target=monitor, daemon=True).start()
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    start_phone_server()
    try:
        if not background and not os.environ.get("HUB_NO_BROWSER"):
            time.sleep(0.5)
            show_window()  # closing the window keeps the hub running in the background
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            write_offline_presence()
        except Exception:
            pass


if __name__ == "__main__":
    main()
