#!/usr/bin/env python3
"""
Proxmox SPICE Connection Manager — Windows Edition
A GUI app to manage and launch SPICE console sessions to Proxmox VMs.

Config: %APPDATA%\\proxmox-spice\\connections.json
Secrets: Encrypted via Windows DPAPI (tied to your Windows user account)

Dependencies:
  - Python 3.9+ with tkinter (included in standard Python installer)
  - virt-viewer (remote-viewer.exe) from https://www.spice-space.org/download.html

Build as single .exe:
  pip install pyinstaller
  pyinstaller "Proxmox SPICE Manager.spec"
"""

import json
import os
import shutil
import subprocess
import sys
import threading
import ctypes
import ctypes.wintypes
import winreg
import base64
from pathlib import Path

import tkinter as tk
from tkinter import messagebox

from proxmox_spice_common import (
    set_fonts, C, HoverButton, ProxmoxSpiceManagerBase,
    load_config, APP_VERSION,
)

# ─── Platform Paths ───────────────────────────────────────────────────────────
APPDATA = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
CONFIG_DIR = APPDATA / "proxmox-spice"
CONFIG_FILE = CONFIG_DIR / "connections.json"
APP_ID = "proxmox-spice-manager"
APP_VERSION_WIN = "2.2.2-win"

FONT = "Segoe UI"
MONO = "Consolas"
set_fonts(FONT, MONO)

_BASE_DIR = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent
ICON_PATH = _BASE_DIR / "icon.ico"

VIRT_VIEWER_DOWNLOAD = "https://www.spice-space.org/download.html"

VIRT_VIEWER_SEARCH_PATHS = [
    r"C:\Program Files\VirtViewer v11.0-256\bin",
    r"C:\Program Files\VirtViewer\bin",
    r"C:\Program Files (x86)\VirtViewer v11.0-256\bin",
    r"C:\Program Files (x86)\VirtViewer\bin",
]


def _find_remote_viewer():
    found = shutil.which("remote-viewer")
    if found:
        return found

    for search_dir in VIRT_VIEWER_SEARCH_PATHS:
        candidate = Path(search_dir) / "remote-viewer.exe"
        if candidate.exists():
            return str(candidate)

    try:
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for subkey in (
                r"SOFTWARE\VirtViewer",
                r"SOFTWARE\WOW6432Node\VirtViewer",
            ):
                try:
                    key = winreg.OpenKey(hive, subkey)
                    install_dir, _ = winreg.QueryValueEx(key, "InstallDir")
                    winreg.CloseKey(key)
                    candidate = Path(install_dir) / "bin" / "remote-viewer.exe"
                    if candidate.exists():
                        return str(candidate)
                except (FileNotFoundError, OSError):
                    continue
    except Exception as e:
        print(f"[debug] find_remote_viewer failed: {type(e).__name__}", file=sys.stderr)

    return None


# ─── Dependency Definitions ───────────────────────────────────────────────────
REQUIRED_DEPS = {
    "virt-viewer": {
        "check": "remote-viewer",
        "desc": "SPICE client (remote-viewer.exe)",
        "install_hint": f"Download from {VIRT_VIEWER_DOWNLOAD}",
        "url": VIRT_VIEWER_DOWNLOAD,
    },
}


def check_deps():
    results = {}
    all_ok = True
    for name, info in REQUIRED_DEPS.items():
        if "check" in info:
            found = _find_remote_viewer() is not None
        else:
            found = False
        results[name] = found
        if not found:
            all_ok = False
    return all_ok, results


# ─── DPAPI Secret Encryption ─────────────────────────────────────────────────
class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.wintypes.DWORD),
                 ("pbData", ctypes.POINTER(ctypes.c_char))]

_crypt32 = ctypes.windll.crypt32
_kernel32 = ctypes.windll.kernel32


def _dpapi_encrypt(plaintext):
    data = plaintext.encode("utf-8")
    blob_in = _DATA_BLOB(len(data), ctypes.create_string_buffer(data, len(data)))
    blob_out = _DATA_BLOB()

    if not _crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0,
        ctypes.byref(blob_out),
    ):
        raise OSError("CryptProtectData failed")

    encrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    _kernel32.LocalFree(blob_out.pbData)
    return base64.b64encode(encrypted).decode("ascii")


def _dpapi_decrypt(b64_ciphertext):
    data = base64.b64decode(b64_ciphertext)
    blob_in = _DATA_BLOB(len(data), ctypes.create_string_buffer(data, len(data)))
    blob_out = _DATA_BLOB()

    if not _crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0,
        ctypes.byref(blob_out),
    ):
        raise OSError("CryptUnprotectData failed")

    decrypted = ctypes.string_at(blob_out.pbData, blob_out.cbData)
    _kernel32.LocalFree(blob_out.pbData)
    return decrypted.decode("utf-8")


# ─── Config & Secret Persistence ────────────────────────────────────────────
def save_config(config):
    config["version"] = APP_VERSION_WIN
    created = not CONFIG_DIR.exists()
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    if created:
        try:
            subprocess.run(
                ["icacls", str(CONFIG_DIR), "/inheritance:r",
                 "/grant:r", f"{os.environ.get('USERNAME', 'CURRENT_USER')}:(OI)(CI)F"],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass


def save_secret(cluster_name, secret, config):
    try:
        encrypted = _dpapi_encrypt(secret)
        for cluster in config.get("clusters", []):
            if cluster["name"] == cluster_name:
                cluster["token_secret_enc"] = encrypted
                break
        save_config(config)
        return True
    except Exception as e:
        print(f"[debug] save_secret failed: {type(e).__name__}", file=sys.stderr)
        return False


def get_secret(cluster_name, config):
    for cluster in config.get("clusters", []):
        if cluster["name"] == cluster_name:
            enc = cluster.get("token_secret_enc")
            if enc:
                try:
                    return _dpapi_decrypt(enc)
                except Exception as e:
                    print(f"[debug] get_secret decrypt failed: {type(e).__name__}", file=sys.stderr)
                    return None
    return None


def delete_secret(cluster_name, config):
    for cluster in config.get("clusters", []):
        if cluster["name"] == cluster_name:
            cluster.pop("token_secret_enc", None)
            break
    save_config(config)


def migrate_secrets(config):
    changed = False
    for cluster in config.get("clusters", []):
        if "token_secret" in cluster:
            secret = cluster["token_secret"]
            if secret:
                try:
                    cluster["token_secret_enc"] = _dpapi_encrypt(secret)
                except Exception as e:
                    print(f"[debug] migrate_secrets encrypt failed: {type(e).__name__}", file=sys.stderr)
            del cluster["token_secret"]
            changed = True
    if changed:
        save_config(config)


# ─── Prereq Dialog (Windows) ─────────────────────────────────────────────────
class PrereqDialog(tk.Toplevel):
    def __init__(self, parent, deps, results):
        super().__init__(parent)
        self.result = False
        self.deps = deps
        self.results = results
        self.title("Proxmox SPICE Manager — Setup")
        self.minsize(560, 200)
        self.resizable(True, True)
        self.grab_set()
        self.configure(bg=C["base"])
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.focus_force()

        tk.Frame(self, bg=C["peach"], height=3).pack(fill="x")

        main = tk.Frame(self, bg=C["base"], padx=28, pady=20)
        main.pack(fill="both", expand=True)

        tk.Label(
            main, text="Welcome to Proxmox SPICE Manager",
            bg=C["base"], fg=C["text"], font=(FONT, 13, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        tk.Label(
            main,
            text="Some required tools are missing. Install them to continue.",
            bg=C["base"], fg=C["subtext0"], font=(FONT, 10),
        ).pack(anchor="w", pady=(0, 20))

        tk.Label(
            main, text="DEPENDENCIES", bg=C["base"], fg=C["overlay0"],
            font=(FONT, 8, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        for name, info in deps.items():
            found = results[name]
            row = tk.Frame(main, bg=C["surface0"], padx=14, pady=10)
            row.pack(fill="x", pady=(0, 6))

            status_color = C["green"] if found else C["red"]
            status_icon = "✓" if found else "✗"

            left = tk.Frame(row, bg=C["surface0"])
            left.pack(side="left", fill="x", expand=True)

            header_row = tk.Frame(left, bg=C["surface0"])
            header_row.pack(fill="x")

            tk.Label(
                header_row, text=status_icon, bg=C["surface0"],
                fg=status_color, font=(FONT, 12, "bold"),
            ).pack(side="left", padx=(0, 8))
            tk.Label(
                header_row, text=name, bg=C["surface0"], fg=C["text"],
                font=(FONT, 10, "bold"),
            ).pack(side="left")

            status_text = "Installed" if found else "Not found"
            tk.Label(
                header_row, text=f"  —  {status_text}", bg=C["surface0"],
                fg=status_color, font=(FONT, 9),
            ).pack(side="left")

            tk.Label(
                left, text=info["desc"], bg=C["surface0"], fg=C["subtext0"],
                font=(FONT, 9),
            ).pack(anchor="w", padx=(28, 0))

            if not found:
                install_frame = tk.Frame(left, bg=C["surface0"])
                install_frame.pack(anchor="w", padx=(28, 0), pady=(4, 0))

                hint = info.get("install_hint", "")

                if info.get("url"):
                    HoverButton(
                        install_frame,
                        text="  ⬇  Open Download Page  ",
                        command=lambda u=info["url"]: self._open_url(u),
                        bg=C["peach"], fg=C["crust"], relief="flat",
                        padx=10, pady=3, hover_bg=C["yellow"],
                        hover_fg=C["crust"],
                        font=(FONT, 9, "bold"),
                    ).pack(side="left")

                if hint:
                    tk.Label(
                        install_frame, text=f"  {hint}", bg=C["surface0"],
                        fg=C["overlay0"], font=(MONO, 8),
                    ).pack(side="left", padx=(8, 0))

        prereq_btn_frame = tk.Frame(main, bg=C["base"])
        prereq_btn_frame.pack(side="bottom", fill="x", pady=(12, 0))

        HoverButton(
            prereq_btn_frame, text="Quit", command=self._cancel,
            bg=C["surface1"], fg=C["text"], relief="flat", padx=18, pady=6,
            hover_bg=C["surface2"], font=(FONT, 10),
        ).pack(side="right", padx=(8, 0))
        HoverButton(
            prereq_btn_frame, text="  Re-check  ", command=self._recheck,
            bg=C["blue"], fg=C["crust"], relief="flat", padx=18, pady=6,
            hover_bg=C["sapphire"], hover_fg=C["crust"],
            font=(FONT, 10, "bold"),
        ).pack(side="right")

        self.wait_window()

    def _open_url(self, url):
        try:
            os.startfile(url)
            messagebox.showinfo(
                "Download",
                "Your browser has been opened to the download page.\n"
                "Install virt-viewer, then click Re-check.",
                parent=self,
            )
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)

    def _recheck(self):
        all_ok, results = check_deps()
        self.results = results
        if all_ok:
            self.result = True
            self.destroy()
        else:
            messagebox.showinfo(
                "Still Missing",
                "Dependencies are still missing. Try again.",
                parent=self,
            )

    def _cancel(self):
        self.result = False
        self.destroy()


# ─── Main Application ────────────────────────────────────────────────────────
class ProxmoxSpiceManager(ProxmoxSpiceManagerBase):

    def _get_app_version(self):
        return APP_VERSION_WIN

    def _get_config_file(self):
        return CONFIG_FILE

    def _platform_set_icon(self):
        try:
            self.iconbitmap(str(ICON_PATH))
        except Exception:
            pass

    def _platform_save_config(self, config):
        save_config(config)

    def _platform_get_secret(self, cluster_name):
        return get_secret(cluster_name, self.config_data)

    def _platform_save_secret(self, cluster_name, secret):
        save_secret(cluster_name, secret, self.config_data)

    def _platform_delete_secret(self, cluster_name):
        delete_secret(cluster_name, self.config_data)

    def _platform_migrate_secrets(self):
        migrate_secrets(self.config_data)

    def _platform_find_viewer(self):
        return _find_remote_viewer()

    def _platform_set_vv_permissions(self, vv_path):
        try:
            subprocess.run(
                ["icacls", vv_path, "/inheritance:r", "/grant:r",
                 f"{os.environ.get('USERNAME', 'CURRENT_USER')}:(R,W,D)"],
                capture_output=True, timeout=5,
            )
        except Exception:
            pass

    def _platform_set_file_permissions(self, path):
        try:
            username = os.environ.get("USERNAME", "")
            if username:
                subprocess.run(
                    ["icacls", path, "/inheritance:r",
                     "/grant:r", f"{username}:(F)"],
                    capture_output=True, timeout=5,
                )
        except Exception:
            pass

    def _platform_launch_viewer(self, viewer, vv_path):
        proc = subprocess.Popen(
            [viewer, vv_path],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.DETACHED_PROCESS,
        )
        def _cleanup_vv(p=proc, path=vv_path):
            p.wait()
            try:
                os.unlink(path)
            except OSError:
                pass
        threading.Thread(target=_cleanup_vv, daemon=True).start()

    def _check_prereqs(self):
        all_ok, results = check_deps()
        if all_ok:
            return True
        dlg = PrereqDialog(self, REQUIRED_DEPS, results)
        return dlg.result

    def _recheck_prereqs(self):
        all_ok, results = check_deps()
        if all_ok:
            messagebox.showinfo(
                "All Good", "All prerequisites are installed.", parent=self
            )
        else:
            dlg = PrereqDialog(self, REQUIRED_DEPS, results)
            if dlg.result:
                self.config_data["prereqs_ok"] = True
                save_config(self.config_data)

    def _platform_header_buttons(self, header):
        hbtn = {
            "bg": C["crust"], "fg": C["subtext0"], "relief": "flat",
            "font": (FONT, 9), "padx": 10, "pady": 4,
            "activebackground": C["mantle"], "activeforeground": C["text"],
        }
        HoverButton(
            header, text="Create Start Menu Shortcut",
            command=self._create_shortcut,
            hover_bg=C["mantle"], hover_fg=C["text"], **hbtn,
        ).pack(side="right", padx=(0, 12))

    def _create_shortcut(self):
        try:
            start_menu = Path(os.environ.get(
                "APPDATA", ""
            )) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            start_menu.mkdir(parents=True, exist_ok=True)

            shortcut_path = start_menu / "Proxmox SPICE Manager.lnk"
            script_path = Path(os.path.abspath(__file__))

            ps_script = "\n".join([
                f'$sc = "{shortcut_path}"',
                f'$exe = "{sys.executable}"',
                f'$args = \'"{script_path}"\'',
                f'$dir = "{script_path.parent}"',
                '$ws = New-Object -ComObject WScript.Shell',
                '$s = $ws.CreateShortcut($sc)',
                '$s.TargetPath = $exe',
                '$s.Arguments = $args',
                '$s.WorkingDirectory = $dir',
                '$s.Description = "Proxmox SPICE Connection Manager"',
                '$s.Save()',
            ])
            encoded = base64.b64encode(ps_script.encode("utf-16-le")).decode("ascii")

            subprocess.run(
                ["powershell", "-EncodedCommand", encoded],
                capture_output=True, timeout=10,
            )

            messagebox.showinfo(
                "Shortcut Created",
                f"Start Menu shortcut created.\n\n{shortcut_path}",
                parent=self,
            )
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)


if __name__ == "__main__":
    app = ProxmoxSpiceManager()
    app.mainloop()
