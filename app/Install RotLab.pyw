"""
RotLab installer. Normally started by "Install RotLab.cmd", which checks for Python first.

Does, on THIS PC only:
  * installs pywebview (proper app window)          - optional
  * creates Desktop + Start Menu shortcuts with icon - optional
  * starts the hub with Windows                      - optional
  * saves your name, then launches the hub
Uninstall removes the shortcuts and the start-with-Windows entry.
"""
import json
import os
import subprocess
import sys
import threading
import tkinter as tk
import urllib.request
from tkinter import ttk, messagebox

APP_DIR = os.path.dirname(os.path.abspath(__file__))
HUB = os.path.join(APP_DIR, "hub.py")
ICON = os.path.join(APP_DIR, "hub.ico")
NO_WINDOW = 0x08000000
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "RotLab"
OLD_RUN_NAMES = ["VegasProjectHub"]
SHORTCUT_NAME = "RotLab.lnk"
OLD_SHORTCUTS = ["Vegas Hub.lnk"]


def python_paths():
    exe = sys.executable
    d = os.path.dirname(exe)
    py = os.path.join(d, "python.exe")
    pyw = os.path.join(d, "pythonw.exe")
    return (py if os.path.isfile(py) else exe), (pyw if os.path.isfile(pyw) else exe)


PY, PYW = python_paths()


def config_path():
    d = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "VegasHub")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "config.json")


def load_config():
    try:
        with open(config_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_name(name):
    c = load_config()
    c["name"] = name
    c.setdefault("auto_baton", True)
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(c, f, indent=1)


def ps(script):
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                       capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW)
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout).strip()[:400])
    return r.stdout.strip()


def q(s):  # PowerShell single-quoted string
    return "'" + s.replace("'", "''") + "'"


def shortcut_dirs(desktop, startmenu):
    script = "$o=@();"
    if desktop:
        script += "$o+=[Environment]::GetFolderPath('Desktop');"
    if startmenu:
        script += "$o+=[Environment]::GetFolderPath('Programs');"
    script += "$o -join '|'"
    out = ps(script)
    return [p for p in out.split("|") if p]


def make_shortcut(folder):
    for old in OLD_SHORTCUTS:  # remove shortcuts from before the rename
        try:
            os.remove(os.path.join(folder, old))
        except OSError:
            pass
    path = os.path.join(folder, SHORTCUT_NAME)
    ps("$s=(New-Object -ComObject WScript.Shell).CreateShortcut(%s);"
       "$s.TargetPath=%s;$s.Arguments=%s;$s.WorkingDirectory=%s;$s.IconLocation=%s;"
       "$s.Description='RotLab';$s.Save()"
       % (q(path), q(PYW), q('"%s"' % HUB), q(APP_DIR), q(ICON + ",0")))
    return path


def set_autostart(on):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        for old in OLD_RUN_NAMES:
            try:
                winreg.DeleteValue(k, old)
            except FileNotFoundError:
                pass
        if on:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, '"%s" "%s" --background' % (PYW, HUB))
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except FileNotFoundError:
                pass


def has_pywebview():
    r = subprocess.run([PY, "-c", "import webview"], capture_output=True, creationflags=NO_WINDOW)
    return r.returncode == 0


def syncthing_found():
    for env in ("LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(env)
        if base and os.path.isfile(os.path.join(base, "Syncthing", "config.xml")):
            return True
    return False


def stop_running_hub():
    try:
        req = urllib.request.Request("http://127.0.0.1:8765/api/quit", data=b"{}", method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=2).read()
        return True
    except Exception:
        return False


# ------------------------------------------------------------------ UI
class App:
    def __init__(self, root):
        self.root = root
        root.title("Install RotLab")
        root.geometry("540x600")
        root.resizable(False, False)
        try:
            root.iconbitmap(ICON)
        except Exception:
            pass
        f = ttk.Frame(root, padding=18)
        f.pack(fill="both", expand=True)

        ttk.Label(f, text="🎬  RotLab", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        ttk.Label(f, text="Sets up the hub on this PC. Your friend runs this too, on theirs.",
                  foreground="#666").pack(anchor="w", pady=(2, 12))

        ttk.Label(f, text="Your name (shown to your friend):").pack(anchor="w")
        self.name = tk.StringVar(value=load_config().get("name", ""))
        e = ttk.Entry(f, textvariable=self.name, width=40)
        e.pack(anchor="w", pady=(2, 12))
        e.focus()

        self.o_sync = tk.BooleanVar(value=True)
        self.o_webview = tk.BooleanVar(value=True)
        self.o_desktop = tk.BooleanVar(value=True)
        self.o_start = tk.BooleanVar(value=True)
        self.o_boot = tk.BooleanVar(value=True)
        self.o_launch = tk.BooleanVar(value=True)
        for var, text in [
            (self.o_sync, "Set up file sync (built-in Syncthing, ~12 MB download)"),
            (self.o_webview, "Install proper app window (pywebview, ~10 MB download)"),
            (self.o_desktop, "Desktop shortcut"),
            (self.o_start, "Start Menu shortcut"),
            (self.o_boot, "Start the hub with Windows (runs quietly in the background)"),
            (self.o_launch, "Open the hub when finished"),
        ]:
            ttk.Checkbutton(f, text=text, variable=var).pack(anchor="w", pady=1)

        st = ("✅ Syncthing is already installed on this PC. The hub will use it." if syncthing_found()
              else "File sync will be set up automatically. After installing, use Invite / Join in the hub to link with your friend.")
        ttk.Label(f, text=st, wraplength=480, foreground="#555").pack(anchor="w", pady=(10, 6))

        self.log = tk.Text(f, height=9, width=60, font=("Consolas", 9), state="disabled", relief="solid", bd=1)
        self.log.pack(fill="both", expand=True, pady=(4, 10))

        b = ttk.Frame(f)
        b.pack(fill="x")
        self.uninstall_btn = ttk.Button(b, text="Uninstall", command=self.uninstall)
        self.uninstall_btn.pack(side="left")
        self.install_btn = ttk.Button(b, text="Install", command=self.install)
        self.install_btn.pack(side="right")
        root.bind("<Return>", lambda e: self.install())

        self.say("Hub location: " + APP_DIR)
        self.say("Python: " + PYW)

    def say(self, text):
        def _w():
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(0, _w)

    def busy(self, on):
        s = "disabled" if on else "normal"
        self.root.after(0, lambda: (self.install_btn.configure(state=s), self.uninstall_btn.configure(state=s)))

    def install(self):
        if str(self.install_btn["state"]) == "disabled":
            return
        name = self.name.get().strip()
        if not name:
            messagebox.showwarning("RotLab", "Please enter your name first.")
            return
        self.busy(True)
        threading.Thread(target=self._install, args=(name,), daemon=True).start()

    def _install(self, name):
        ok = True
        try:
            save_name(name[:40])
            self.say("✔ Saved your name: " + name)
        except Exception as e:
            ok = False
            self.say("✖ Couldn't save name: %s" % e)

        invite = os.environ.get("ROTLAB_INVITE", "").strip()
        if invite:
            try:
                import base64
                c = invite[9:] if invite.upper().startswith("VEGASHUB-") else invite
                who = json.loads(base64.urlsafe_b64decode(c + "=" * (-len(c) % 4)).decode()).get("n") or "your friend"
                cfg = load_config()
                cfg["pending_invite"] = invite
                with open(config_path(), "w", encoding="utf-8") as fh:
                    json.dump(cfg, fh, indent=1)
                self.o_sync.set(True)
                self.say("✔ Will link with %s's PC as soon as sync starts" % who)
            except Exception as e:
                self.say("✖ The invite in this installer didn't work (%s). Ask for a new one." % e)

        if self.o_sync.get():
            if syncthing_found():
                self.say("✔ Using the Syncthing already installed on this PC")
            else:
                try:
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("vegas_hub", HUB)
                    hub = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(hub)
                    if os.path.isfile(hub.ST_EXE):
                        self.say("✔ File sync already downloaded")
                    else:
                        self.say("… Downloading file sync (Syncthing)")
                        last = [-10]

                        def prog(pct, msg):
                            if pct - last[0] >= 10 or pct >= 100:
                                last[0] = pct
                                self.say("   %3d%%  %s" % (pct, msg))
                        hub.install_syncthing(prog)
                        self.say("✔ File sync installed")
                except Exception as e:
                    ok = False
                    self.say("✖ File sync download failed: %s" % e)
                    self.say("   (You can retry later from the hub: File sync → Set up sync)")

        if self.o_webview.get():
            if has_pywebview():
                self.say("✔ App window add-on already installed")
            else:
                self.say("… Installing app window add-on (this can take a minute)")
                r = subprocess.run([PY, "-m", "pip", "install", "--user", "pywebview"],
                                   capture_output=True, text=True, errors="replace", creationflags=NO_WINDOW)
                if r.returncode == 0 and has_pywebview():
                    self.say("✔ App window add-on installed")
                else:
                    ok = False
                    self.say("✖ Add-on install failed (internet on?). The hub still works in a browser-style window.")
                    tail = (r.stderr or r.stdout).strip().splitlines()[-2:]
                    for line in tail:
                        self.say("   " + line[:120])

        try:
            for folder in shortcut_dirs(self.o_desktop.get(), self.o_start.get()):
                self.say("✔ Shortcut: " + make_shortcut(folder))
        except Exception as e:
            ok = False
            self.say("✖ Shortcut failed: %s" % e)

        try:
            set_autostart(self.o_boot.get())
            self.say("✔ Start with Windows: " + ("on" if self.o_boot.get() else "off"))
        except Exception as e:
            ok = False
            self.say("✖ Start-with-Windows failed: %s" % e)

        if self.o_launch.get():
            if stop_running_hub():
                self.say("… Restarting the running hub")
                import time
                time.sleep(1.5)
            subprocess.Popen([PYW, HUB], cwd=APP_DIR, creationflags=0x00000008)  # DETACHED_PROCESS
            self.say("✔ Hub launched")

        self.say("\nAll done! 🎉" if ok else "\nFinished with some problems (see above).")
        self.busy(False)

    def uninstall(self):
        if not messagebox.askyesno("RotLab", "Remove the shortcuts and start-with-Windows from this PC?\n\n"
                                   "(Your project files and the hub folder are not touched.)"):
            return
        self.busy(True)
        threading.Thread(target=self._uninstall, daemon=True).start()

    def _uninstall(self):
        if stop_running_hub():
            self.say("✔ Stopped the running hub")
        try:
            for folder in shortcut_dirs(True, True):
                for nm in [SHORTCUT_NAME] + OLD_SHORTCUTS:
                    p = os.path.join(folder, nm)
                    if os.path.exists(p):
                        os.remove(p)
                        self.say("✔ Removed " + p)
        except Exception as e:
            self.say("✖ %s" % e)
        try:
            set_autostart(False)
            self.say("✔ Start with Windows: off")
        except Exception as e:
            self.say("✖ %s" % e)
        self.say("\nUninstalled from this PC.")
        self.busy(False)


if __name__ == "__main__":
    if os.name != "nt":
        print("This installer is for Windows.")
        sys.exit(1)
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except Exception:
        pass
    App(root)
    root.mainloop()
