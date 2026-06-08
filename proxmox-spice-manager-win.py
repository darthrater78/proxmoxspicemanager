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
  pyinstaller --onefile --windowed --name "Proxmox SPICE Manager" proxmox-spice-manager-win.py
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import ssl
import urllib.request
import urllib.parse
import urllib.error
import copy
import ctypes
import ctypes.wintypes
import winreg
import base64
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ─── Platform Paths ───────────────────────────────────────────────────────────
APPDATA = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
CONFIG_DIR = APPDATA / "proxmox-spice"
CONFIG_FILE = CONFIG_DIR / "connections.json"
APP_ID = "proxmox-spice-manager"
APP_VERSION = "2.1.1-win"

VIRT_VIEWER_DOWNLOAD = "https://www.spice-space.org/download.html"

# Common virt-viewer install locations on Windows
VIRT_VIEWER_SEARCH_PATHS = [
    r"C:\Program Files\VirtViewer v11.0-256\bin",
    r"C:\Program Files\VirtViewer\bin",
    r"C:\Program Files (x86)\VirtViewer v11.0-256\bin",
    r"C:\Program Files (x86)\VirtViewer\bin",
]


def _find_remote_viewer():
    """Find remote-viewer.exe on Windows."""
    # Check PATH first
    found = shutil.which("remote-viewer")
    if found:
        return found

    # Check common install locations
    for search_dir in VIRT_VIEWER_SEARCH_PATHS:
        candidate = Path(search_dir) / "remote-viewer.exe"
        if candidate.exists():
            return str(candidate)

    # Check registry for virt-viewer install path
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
    except Exception:
        pass

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


# ─── Theme Definitions ────────────────────────────────────────────────────────
THEMES = {
    "Catppuccin Mocha": {
        "base": "#1e1e2e", "mantle": "#181825", "crust": "#11111b",
        "surface0": "#313244", "surface1": "#45475a", "surface2": "#585b70",
        "overlay0": "#6c7086", "overlay1": "#7f849c",
        "text": "#cdd6f4", "subtext0": "#a6adc8", "subtext1": "#bac2de",
        "blue": "#89b4fa", "sapphire": "#74c7ec", "green": "#a6e3a1",
        "teal": "#94e2d5", "yellow": "#f9e2af", "peach": "#fab387",
        "red": "#f38ba8", "mauve": "#cba6f7", "lavender": "#b4befe",
    },
    "Catppuccin Latte": {
        "base": "#eff1f5", "mantle": "#e6e9ef", "crust": "#dce0e8",
        "surface0": "#ccd0da", "surface1": "#bcc0cc", "surface2": "#acb0be",
        "overlay0": "#9ca0b0", "overlay1": "#8c8fa1",
        "text": "#4c4f69", "subtext0": "#6c6f85", "subtext1": "#5c5f77",
        "blue": "#1e66f5", "sapphire": "#209fb5", "green": "#40a02b",
        "teal": "#179299", "yellow": "#df8e1d", "peach": "#fe640b",
        "red": "#d20f39", "mauve": "#8839ef", "lavender": "#7287fd",
    },
    "Nord": {
        "base": "#2e3440", "mantle": "#292e39", "crust": "#242933",
        "surface0": "#3b4252", "surface1": "#434c5e", "surface2": "#4c566a",
        "overlay0": "#616e88", "overlay1": "#6e7a94",
        "text": "#eceff4", "subtext0": "#d8dee9", "subtext1": "#e5e9f0",
        "blue": "#88c0d0", "sapphire": "#81a1c1", "green": "#a3be8c",
        "teal": "#8fbcbb", "yellow": "#ebcb8b", "peach": "#d08770",
        "red": "#bf616a", "mauve": "#b48ead", "lavender": "#81a1c1",
    },
    "Dracula": {
        "base": "#282a36", "mantle": "#21222c", "crust": "#191a21",
        "surface0": "#343746", "surface1": "#3e4157", "surface2": "#484b68",
        "overlay0": "#6272a4", "overlay1": "#7082b4",
        "text": "#f8f8f2", "subtext0": "#d0d0d0", "subtext1": "#e0e0e0",
        "blue": "#8be9fd", "sapphire": "#66d9ef", "green": "#50fa7b",
        "teal": "#50fa7b", "yellow": "#f1fa8c", "peach": "#ffb86c",
        "red": "#ff5555", "mauve": "#bd93f9", "lavender": "#bd93f9",
    },
    "OLED Dark": {
        "base": "#000000", "mantle": "#0a0a0a", "crust": "#050505",
        "surface0": "#1a1a1a", "surface1": "#262626", "surface2": "#333333",
        "overlay0": "#555555", "overlay1": "#666666",
        "text": "#e0e0e0", "subtext0": "#aaaaaa", "subtext1": "#c0c0c0",
        "blue": "#5ea6ff", "sapphire": "#4dc9f6", "green": "#67d98a",
        "teal": "#4dd8b0", "yellow": "#f0c060", "peach": "#e89050",
        "red": "#f06070", "mauve": "#b080e0", "lavender": "#9090e0",
    },
}

C = dict(THEMES["Catppuccin Mocha"])


# ─── Dependency Checking ─────────────────────────────────────────────────────
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
# Uses Windows Data Protection API to encrypt secrets with the current user's
# credentials. Encrypted blobs are stored as base64 in connections.json and
# cannot be decrypted by another user or on another machine.

class _DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.wintypes.DWORD),
                 ("pbData", ctypes.POINTER(ctypes.c_char))]

_crypt32 = ctypes.windll.crypt32
_kernel32 = ctypes.windll.kernel32


def _dpapi_encrypt(plaintext: str) -> str:
    """Encrypt a string with DPAPI, return base64-encoded ciphertext."""
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


def _dpapi_decrypt(b64_ciphertext: str) -> str:
    """Decrypt a base64-encoded DPAPI blob back to plaintext."""
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
def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                data = json.load(f)
                if "version" not in data:
                    data["version"] = APP_VERSION
                return data
        except (json.JSONDecodeError, IOError):
            pass
    return {"version": APP_VERSION, "clusters": [], "theme": "Catppuccin Mocha"}


def save_config(config):
    config["version"] = APP_VERSION
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def save_secret(cluster_name, secret, config):
    """Encrypt and store secret in the cluster's config entry."""
    try:
        encrypted = _dpapi_encrypt(secret)
        for cluster in config.get("clusters", []):
            if cluster["name"] == cluster_name:
                cluster["token_secret_enc"] = encrypted
                break
        save_config(config)
        return True
    except Exception as e:
        print(f"[debug] save_secret failed: {e}", file=sys.stderr)
        return False


def get_secret(cluster_name, config):
    """Retrieve and decrypt the secret for a cluster."""
    for cluster in config.get("clusters", []):
        if cluster["name"] == cluster_name:
            enc = cluster.get("token_secret_enc")
            if enc:
                try:
                    return _dpapi_decrypt(enc)
                except Exception as e:
                    print(f"[debug] get_secret decrypt failed: {e}", file=sys.stderr)
                    return None
    return None


def delete_secret(cluster_name, config):
    """Remove encrypted secret from a cluster's config entry."""
    for cluster in config.get("clusters", []):
        if cluster["name"] == cluster_name:
            cluster.pop("token_secret_enc", None)
            break
    save_config(config)


def migrate_secrets(config):
    """Migrate any plaintext token_secret fields to DPAPI-encrypted storage."""
    changed = False
    for cluster in config.get("clusters", []):
        if "token_secret" in cluster:
            secret = cluster["token_secret"]
            if secret:
                try:
                    cluster["token_secret_enc"] = _dpapi_encrypt(secret)
                except Exception:
                    pass
            del cluster["token_secret"]
            changed = True
    if changed:
        save_config(config)


# ─── Proxmox API Helpers ─────────────────────────────────────────────────────
def _get_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def api_request(host, endpoint, method="GET", auth=None, data=None):
    url = f"{host}{endpoint}"
    req = urllib.request.Request(url, method=method)

    if auth:
        if auth.get("token_id") and auth.get("token_secret"):
            req.add_header(
                "Authorization",
                f"PVEAPIToken={auth['token_id']}={auth['token_secret']}",
            )
        elif auth.get("ticket"):
            req.add_header("Cookie", f"PVEAuthCookie={auth['ticket']}")
            if auth.get("csrf"):
                req.add_header("CSRFPreventionToken", auth["csrf"])

    if method in ("POST", "DELETE", "PUT") and data is None:
        data = b""

    try:
        with urllib.request.urlopen(
            req, data=data, context=_get_ssl_context(), timeout=15
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
            if "message" in body and "error" not in body:
                body["error"] = body["message"]
            return body
        except Exception:
            return {"error": f"HTTP {e.code}: {e.reason}"}
    except urllib.error.URLError as e:
        return {"error": f"Connection failed: {e.reason}"}
    except Exception as e:
        return {"error": str(e)}


def authenticate_password(host, username, password):
    url = f"{host}/api2/json/access/ticket"
    data = urllib.parse.urlencode(
        {"username": username, "password": password}
    ).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")

    try:
        with urllib.request.urlopen(
            req, context=_get_ssl_context(), timeout=15
        ) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if res_data.get("data", {}).get("ticket"):
                return {
                    "ticket": res_data["data"]["ticket"],
                    "csrf": res_data["data"].get("CSRFPreventionToken", ""),
                }
    except Exception:
        pass
    return None


# ─── Hover Button ─────────────────────────────────────────────────────────────
class HoverButton(tk.Button):
    def __init__(self, master, hover_bg=None, hover_fg=None, **kw):
        self._normal_bg = kw.get("bg", C["surface0"])
        self._normal_fg = kw.get("fg", C["text"])
        self._hover_bg = hover_bg or kw.get("activebackground", C["surface1"])
        self._hover_fg = hover_fg or kw.get("activeforeground", self._normal_fg)
        super().__init__(master, **kw)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, e):
        self.config(bg=self._hover_bg, fg=self._hover_fg)

    def _on_leave(self, e):
        self.config(bg=self._normal_bg, fg=self._normal_fg)


# ─── Dialogs ─────────────────────────────────────────────────────────────────
class ClusterDialog(tk.Toplevel):
    def __init__(self, parent, cluster=None, config_data=None):
        super().__init__(parent)
        self.result = None
        self.config_data = config_data or {}
        self.original_name = cluster.get("name") if cluster else None

        self.title("Edit Cluster" if cluster else "Add Cluster")
        self.geometry("500x480")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.configure(bg=C["base"])

        tk.Frame(self, bg=C["mauve"], height=3).pack(fill="x")

        main = tk.Frame(self, bg=C["base"], padx=24, pady=20)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)

        lbl = {"bg": C["base"], "fg": C["subtext0"], "font": ("Segoe UI", 9)}
        entry_cfg = {
            "bg": C["surface0"], "fg": C["text"], "insertbackground": C["text"],
            "relief": "flat", "font": ("Consolas", 10), "highlightthickness": 1,
            "highlightcolor": C["blue"], "highlightbackground": C["surface1"],
        }

        tk.Label(main, text="CLUSTER NAME", **lbl).grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )
        self.name_entry = tk.Entry(main, **entry_cfg)
        self.name_entry.grid(row=1, column=0, sticky="ew", pady=(0, 16), ipady=6)

        tk.Label(
            main, text="HOST URL (e.g. https://192.168.1.100:8006)", **lbl
        ).grid(row=2, column=0, sticky="w", pady=(0, 4))
        self.host_entry = tk.Entry(main, **entry_cfg)
        self.host_entry.grid(row=3, column=0, sticky="ew", pady=(0, 16), ipady=6)

        tk.Label(main, text="AUTHENTICATION", **lbl).grid(
            row=4, column=0, sticky="w", pady=(0, 4)
        )
        self.auth_var = tk.StringVar(value="token")
        auth_frame = tk.Frame(main, bg=C["base"])
        auth_frame.grid(row=5, column=0, sticky="w", pady=(0, 12))

        radio_cfg = {
            "bg": C["base"], "fg": C["text"], "selectcolor": C["surface0"],
            "activebackground": C["base"], "activeforeground": C["text"],
            "font": ("Segoe UI", 10), "command": self._toggle_auth,
        }
        tk.Radiobutton(
            auth_frame, text="API Token", variable=self.auth_var,
            value="token", **radio_cfg,
        ).pack(side="left", padx=(0, 20))
        tk.Radiobutton(
            auth_frame, text="Password", variable=self.auth_var,
            value="password", **radio_cfg,
        ).pack(side="left")

        self.token_frame = tk.Frame(main, bg=C["base"])
        self.token_frame.grid(row=6, column=0, sticky="ew")
        self.token_frame.columnconfigure(0, weight=1)

        tk.Label(
            self.token_frame, text="TOKEN ID  (user@realm!token)", **lbl
        ).pack(anchor="w", pady=(0, 4))
        self.token_id_entry = tk.Entry(self.token_frame, **entry_cfg)
        self.token_id_entry.pack(fill="x", pady=(0, 10), ipady=6)

        tk.Label(self.token_frame, text="TOKEN SECRET", **lbl).pack(
            anchor="w", pady=(0, 4)
        )
        self.token_secret_entry = tk.Entry(
            self.token_frame, **entry_cfg, show="•"
        )
        self.token_secret_entry.pack(fill="x", pady=(0, 8), ipady=6)

        self.pass_frame = tk.Frame(main, bg=C["base"])
        self.pass_frame.columnconfigure(0, weight=1)
        tk.Label(self.pass_frame, text="USERNAME", **lbl).pack(
            anchor="w", pady=(0, 4)
        )
        self.user_entry = tk.Entry(self.pass_frame, **entry_cfg)
        self.user_entry.pack(fill="x", pady=(0, 8), ipady=6)
        self.user_entry.insert(0, "root@pam")

        btn_frame = tk.Frame(main, bg=C["base"])
        btn_frame.grid(row=7, column=0, sticky="e", pady=(20, 0))

        HoverButton(
            btn_frame, text="Cancel", command=self.destroy,
            bg=C["surface1"], fg=C["text"], relief="flat", padx=18, pady=6,
            hover_bg=C["surface2"], font=("Segoe UI", 10),
        ).pack(side="right", padx=(8, 0))
        HoverButton(
            btn_frame, text="  Save  ", command=self._save,
            bg=C["blue"], fg=C["crust"], relief="flat", padx=18, pady=6,
            hover_bg=C["sapphire"], hover_fg=C["crust"],
            font=("Segoe UI", 10, "bold"),
        ).pack(side="right")

        if cluster:
            self.name_entry.insert(0, cluster.get("name", ""))
            self.host_entry.insert(0, cluster.get("host", ""))
            self.auth_var.set(cluster.get("auth_method", "token"))
            self.token_id_entry.insert(0, cluster.get("token_id", ""))
            secret = get_secret(self.original_name, self.config_data)
            if secret:
                self.token_secret_entry.insert(0, secret)
            self.user_entry.delete(0, "end")
            self.user_entry.insert(0, cluster.get("username", "root@pam"))
            self._toggle_auth()
        else:
            self.host_entry.insert(0, "https://")

        self.name_entry.focus_set()
        self.wait_window()

    def _toggle_auth(self):
        if self.auth_var.get() == "token":
            self.pass_frame.grid_forget()
            self.token_frame.grid(row=6, column=0, sticky="ew")
        else:
            self.token_frame.grid_forget()
            self.pass_frame.grid(row=6, column=0, sticky="ew")

    def _save(self):
        name = self.name_entry.get().strip()
        host = self.host_entry.get().strip().rstrip("/")
        if not name or not host:
            messagebox.showwarning(
                "Missing Fields", "Name and Host URL are required.",
                parent=self,
            )
            return

        auth_method = self.auth_var.get()
        secret = self.token_secret_entry.get().strip()

        if self.original_name and self.original_name != name:
            delete_secret(self.original_name, self.config_data)

        # Secret will be encrypted and saved after the cluster entry exists
        self._pending_secret = secret if (auth_method == "token" and secret) else None

        self.result = {
            "name": name, "host": host, "auth_method": auth_method,
            "token_id": self.token_id_entry.get().strip(),
            "username": self.user_entry.get().strip(),
        }
        self.destroy()


class PasswordPrompt(tk.Toplevel):
    def __init__(self, parent, username, host):
        super().__init__(parent)
        self.result = None
        self.title("Authenticate")
        self.geometry("400x180")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(bg=C["base"])

        tk.Frame(self, bg=C["yellow"], height=3).pack(fill="x")

        main = tk.Frame(self, bg=C["base"], padx=24, pady=16)
        main.pack(fill="both", expand=True)

        entry_cfg = {
            "bg": C["surface0"], "fg": C["text"], "insertbackground": C["text"],
            "relief": "flat", "font": ("Consolas", 10), "highlightthickness": 1,
            "highlightcolor": C["blue"], "highlightbackground": C["surface1"],
        }

        tk.Label(
            main, text=f"Password for {username}", bg=C["base"], fg=C["text"],
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(0, 2))
        tk.Label(
            main, text=host, bg=C["base"], fg=C["overlay0"],
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(0, 10))

        self.pw_entry = tk.Entry(main, **entry_cfg, show="•")
        self.pw_entry.pack(fill="x", ipady=6)
        self.pw_entry.bind("<Return>", lambda e: self._submit())

        btn_frame = tk.Frame(main, bg=C["base"])
        btn_frame.pack(anchor="e", pady=(14, 0))

        HoverButton(
            btn_frame, text="Cancel", command=self.destroy,
            bg=C["surface1"], fg=C["text"], relief="flat", padx=16, pady=5,
            hover_bg=C["surface2"],
        ).pack(side="right", padx=(8, 0))
        HoverButton(
            btn_frame, text="  Connect  ", command=self._submit,
            bg=C["blue"], fg=C["crust"], relief="flat", padx=16, pady=5,
            hover_bg=C["sapphire"], hover_fg=C["crust"],
            font=("Segoe UI", 10, "bold"),
        ).pack(side="right")

        self.pw_entry.focus_set()
        self.wait_window()

    def _submit(self):
        self.result = self.pw_entry.get()
        self.destroy()


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
            bg=C["base"], fg=C["text"], font=("Segoe UI", 13, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        tk.Label(
            main,
            text="Some required tools are missing. Install them to continue.",
            bg=C["base"], fg=C["subtext0"], font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(0, 20))

        tk.Label(
            main, text="DEPENDENCIES", bg=C["base"], fg=C["overlay0"],
            font=("Segoe UI", 8, "bold"),
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
                fg=status_color, font=("Segoe UI", 12, "bold"),
            ).pack(side="left", padx=(0, 8))
            tk.Label(
                header_row, text=name, bg=C["surface0"], fg=C["text"],
                font=("Segoe UI", 10, "bold"),
            ).pack(side="left")

            status_text = "Installed" if found else "Not found"
            tk.Label(
                header_row, text=f"  —  {status_text}", bg=C["surface0"],
                fg=status_color, font=("Segoe UI", 9),
            ).pack(side="left")

            tk.Label(
                left, text=info["desc"], bg=C["surface0"], fg=C["subtext0"],
                font=("Segoe UI", 9),
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
                        font=("Segoe UI", 9, "bold"),
                    ).pack(side="left")

                if hint:
                    tk.Label(
                        install_frame, text=f"  {hint}", bg=C["surface0"],
                        fg=C["overlay0"], font=("Consolas", 8),
                    ).pack(side="left", padx=(8, 0))

        prereq_btn_frame = tk.Frame(main, bg=C["base"])
        prereq_btn_frame.pack(side="bottom", fill="x", pady=(12, 0))

        HoverButton(
            prereq_btn_frame, text="Quit", command=self._cancel,
            bg=C["surface1"], fg=C["text"], relief="flat", padx=18, pady=6,
            hover_bg=C["surface2"], font=("Segoe UI", 10),
        ).pack(side="right", padx=(8, 0))
        HoverButton(
            prereq_btn_frame, text="  Re-check  ", command=self._recheck,
            bg=C["blue"], fg=C["crust"], relief="flat", padx=18, pady=6,
            hover_bg=C["sapphire"], hover_fg=C["crust"],
            font=("Segoe UI", 10, "bold"),
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


# ─── Snapshot Dialog ──────────────────────────────────────────────────────────
class SnapshotDialog(tk.Toplevel):
    def __init__(self, parent, vm, cluster, auth, on_change=None):
        super().__init__(parent)
        self.vm = vm
        self.cluster = cluster
        self.auth = auth
        self.on_change = on_change
        self._initial_count = 0

        self.title(f"Snapshots — {vm['name']} (VM {vm['vmid']})")
        self.geometry("620x480")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.configure(bg=C["base"])

        tk.Frame(self, bg=C["lavender"], height=3).pack(fill="x")

        main = tk.Frame(self, bg=C["base"], padx=20, pady=16)
        main.pack(fill="both", expand=True)

        header = tk.Frame(main, bg=C["base"])
        header.pack(fill="x", pady=(0, 12))
        tk.Label(
            header, text=f"Snapshots for {vm['name']}", bg=C["base"],
            fg=C["text"], font=("Segoe UI", 12, "bold"),
        ).pack(side="left")
        HoverButton(
            header, text="  ↻ Refresh  ", command=self._load_snapshots,
            bg=C["surface0"], fg=C["subtext0"], relief="flat", padx=10,
            pady=3, hover_bg=C["surface1"], hover_fg=C["text"],
            font=("Segoe UI", 9),
        ).pack(side="right")

        tree_frame = tk.Frame(main, bg=C["base"])
        tree_frame.pack(fill="both", expand=True, pady=(0, 10))

        columns = ("name", "date", "description")
        self.snap_tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings",
            selectmode="browse", height=10,
        )

        style = ttk.Style()
        style.configure(
            "Snap.Treeview", background=C["surface0"], foreground=C["text"],
            fieldbackground=C["surface0"], rowheight=28,
            font=("Segoe UI", 10), borderwidth=0,
        )
        style.configure(
            "Snap.Treeview.Heading", background=C["surface1"],
            foreground=C["subtext0"], font=("Segoe UI", 9, "bold"),
            borderwidth=0, relief="flat",
        )
        style.map(
            "Snap.Treeview",
            background=[("selected", C["surface1"])],
            foreground=[("selected", C["blue"])],
        )

        self.snap_tree.configure(style="Snap.Treeview")
        self.snap_tree.heading("name", text="NAME")
        self.snap_tree.heading("date", text="DATE")
        self.snap_tree.heading("description", text="DESCRIPTION")
        self.snap_tree.column("name", width=160, minwidth=100)
        self.snap_tree.column("date", width=160, minwidth=100)
        self.snap_tree.column("description", width=250, minwidth=100)

        scrollbar = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.snap_tree.yview
        )
        self.snap_tree.configure(yscrollcommand=scrollbar.set)
        self.snap_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.status_label = tk.Label(
            main, text="", bg=C["base"], fg=C["overlay0"],
            font=("Segoe UI", 9), anchor="w",
        )
        self.status_label.pack(fill="x", pady=(0, 8))

        btn_frame = tk.Frame(main, bg=C["base"])
        btn_frame.pack(fill="x")

        HoverButton(
            btn_frame, text="  Close  ", command=self.destroy,
            bg=C["surface1"], fg=C["text"], relief="flat", padx=16, pady=6,
            hover_bg=C["surface2"], font=("Segoe UI", 10),
        ).pack(side="right")
        HoverButton(
            btn_frame, text="  Rollback  ", command=self._rollback_snapshot,
            bg=C["peach"], fg=C["crust"], relief="flat", padx=16, pady=6,
            hover_bg=C["yellow"], hover_fg=C["crust"],
            font=("Segoe UI", 10, "bold"),
        ).pack(side="right", padx=(0, 8))
        HoverButton(
            btn_frame, text="  Delete  ", command=self._delete_snapshot,
            bg=C["surface0"], fg=C["red"], relief="flat", padx=16, pady=6,
            hover_bg=C["surface1"], hover_fg=C["red"],
            font=("Segoe UI", 10),
        ).pack(side="right", padx=(0, 8))
        HoverButton(
            btn_frame, text="  + Create  ", command=self._create_snapshot,
            bg=C["surface0"], fg=C["green"], relief="flat", padx=16, pady=6,
            hover_bg=C["surface1"], hover_fg=C["green"],
            font=("Segoe UI", 10),
        ).pack(side="left")

        self._load_snapshots()
        self.wait_window()

    def _load_snapshots(self):
        self.status_label.config(text="Loading snapshots...", fg=C["yellow"])
        self.snap_tree.delete(*self.snap_tree.get_children())
        self.update_idletasks()

        data = api_request(
            self.cluster["host"],
            f"/api2/json/nodes/{self.vm['node']}/qemu/{self.vm['vmid']}/snapshot",
            auth=self.auth,
        )

        if "error" in data:
            self.status_label.config(text=f"Error: {data['error']}", fg=C["red"])
            return

        real_snaps = [
            s for s in data.get("data", []) if s.get("name") != "current"
        ]

        if not real_snaps:
            self._initial_count = 0
            self.status_label.config(text="No snapshots found.", fg=C["overlay0"])
            return

        count = 0
        for snap in sorted(
            real_snaps, key=lambda s: s.get("snaptime", 0), reverse=True
        ):
            name = snap.get("name", "")
            snaptime = snap.get("snaptime", 0)
            date_str = (
                datetime.fromtimestamp(snaptime).strftime("%Y-%m-%d  %H:%M:%S")
                if snaptime else "—"
            )
            desc = snap.get("description", "")
            self.snap_tree.insert("", "end", values=(name, date_str, desc))
            count += 1

        self._initial_count = count
        self.status_label.config(text=f"{count} snapshot(s)", fg=C["overlay0"])

    def _notify_change(self):
        if self.on_change:
            self.on_change(self.vm["vmid"], self.vm["node"], self._initial_count)

    def _get_selected_snapshot(self):
        sel = self.snap_tree.selection()
        if not sel:
            return None
        return self.snap_tree.item(sel[0], "values")[0]

    def _rollback_snapshot(self):
        snap_name = self._get_selected_snapshot()
        if not snap_name:
            messagebox.showinfo(
                "No Selection", "Select a snapshot to rollback to.",
                parent=self,
            )
            return

        if not messagebox.askyesno(
            "Confirm Rollback",
            f"Rollback VM {self.vm['vmid']} to '{snap_name}'?\n"
            "Current state will be lost.",
            parent=self,
        ):
            return

        self.status_label.config(
            text=f"Rolling back to '{snap_name}'...", fg=C["yellow"]
        )
        self.update_idletasks()

        data = api_request(
            self.cluster["host"],
            f"/api2/json/nodes/{self.vm['node']}/qemu/{self.vm['vmid']}"
            f"/snapshot/{snap_name}/rollback",
            method="POST", auth=self.auth,
        )

        if "error" in data:
            self.status_label.config(text="Rollback failed", fg=C["red"])
            messagebox.showerror("Rollback Failed", data["error"], parent=self)
        else:
            self.status_label.config(
                text=f"Rolled back to '{snap_name}'", fg=C["green"]
            )
            if hasattr(self.master, "_poll_until_changed"):
                self.master._poll_until_changed(
                    {str(self.vm["vmid"]): "stopped"}, auth=self.auth
                )
            self.after(3000, self._load_snapshots)

    def _create_snapshot(self):
        dlg = tk.Toplevel(self)
        dlg.title("Create Snapshot")
        dlg.geometry("400x300")
        dlg.resizable(True, True)
        dlg.transient(self)
        dlg.grab_set()
        dlg.configure(bg=C["base"])

        tk.Frame(dlg, bg=C["green"], height=3).pack(fill="x")
        main = tk.Frame(dlg, bg=C["base"], padx=20, pady=16)
        main.pack(fill="both", expand=True)

        entry_cfg = {
            "bg": C["surface0"], "fg": C["text"], "insertbackground": C["text"],
            "relief": "flat", "font": ("Consolas", 10), "highlightthickness": 1,
            "highlightcolor": C["blue"], "highlightbackground": C["surface1"],
        }
        lbl = {"bg": C["base"], "fg": C["subtext0"], "font": ("Segoe UI", 9)}

        tk.Label(main, text="SNAPSHOT NAME", **lbl).pack(anchor="w", pady=(0, 4))
        name_entry = tk.Entry(main, **entry_cfg)
        name_entry.pack(fill="x", ipady=6, pady=(0, 12))

        tk.Label(main, text="DESCRIPTION (optional)", **lbl).pack(
            anchor="w", pady=(0, 4)
        )
        desc_entry = tk.Entry(main, **entry_cfg)
        desc_entry.pack(fill="x", ipady=6, pady=(0, 12))

        include_ram = tk.BooleanVar(value=False)
        tk.Checkbutton(
            main, text="  Include RAM (VM state)", variable=include_ram,
            bg=C["base"], fg=C["text"], selectcolor=C["surface0"],
            activebackground=C["base"], activeforeground=C["text"],
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(0, 8))

        result = {"name": None}

        def on_create():
            n = name_entry.get().strip()
            if not n:
                messagebox.showwarning(
                    "Missing Name", "Enter a snapshot name.", parent=dlg
                )
                return
            result["name"] = n
            result["desc"] = desc_entry.get().strip()
            result["vmstate"] = include_ram.get()
            dlg.destroy()

        btn_frame = tk.Frame(main, bg=C["base"])
        btn_frame.pack(anchor="e")
        HoverButton(
            btn_frame, text="Cancel", command=dlg.destroy,
            bg=C["surface1"], fg=C["text"], relief="flat", padx=16, pady=5,
            hover_bg=C["surface2"], font=("Segoe UI", 10),
        ).pack(side="right", padx=(8, 0))
        HoverButton(
            btn_frame, text="  Create  ", command=on_create,
            bg=C["green"], fg=C["crust"], relief="flat", padx=16, pady=5,
            hover_bg=C["teal"], hover_fg=C["crust"],
            font=("Segoe UI", 10, "bold"),
        ).pack(side="right")

        name_entry.focus_set()
        dlg.wait_window()

        if not result["name"]:
            return

        self.status_label.config(
            text=f"Creating snapshot '{result['name']}'...", fg=C["yellow"]
        )
        self.update_idletasks()

        endpoint = (
            f"/api2/json/nodes/{self.vm['node']}/qemu/{self.vm['vmid']}"
            f"/snapshot?snapname={result['name']}"
        )
        if result["desc"]:
            endpoint += f"&description={urllib.parse.quote(result['desc'])}"
        if result["vmstate"]:
            endpoint += "&vmstate=1"

        data = api_request(
            self.cluster["host"], endpoint, method="POST", auth=self.auth
        )

        if "error" in data:
            self.status_label.config(text="Snapshot creation failed", fg=C["red"])
            messagebox.showerror("Snapshot Failed", data["error"], parent=self)
        else:
            self.status_label.config(
                text=f"Snapshot '{result['name']}' created", fg=C["green"]
            )
            self._notify_change()
            self.after(3000, self._load_snapshots)

    def _delete_snapshot(self):
        snap_name = self._get_selected_snapshot()
        if not snap_name:
            return

        if not messagebox.askyesno(
            "Delete Snapshot",
            f"Delete snapshot '{snap_name}'?\n\nThis cannot be undone.",
            parent=self,
        ):
            return

        self.status_label.config(text=f"Deleting '{snap_name}'...", fg=C["yellow"])
        self.update_idletasks()

        data = api_request(
            self.cluster["host"],
            f"/api2/json/nodes/{self.vm['node']}/qemu/{self.vm['vmid']}"
            f"/snapshot/{snap_name}",
            method="DELETE", auth=self.auth,
        )

        if "error" in data:
            self.status_label.config(text="Delete failed", fg=C["red"])
            messagebox.showerror("Delete Failed", data["error"], parent=self)
        else:
            self.status_label.config(
                text=f"Snapshot '{snap_name}' deleted", fg=C["green"]
            )
            self._notify_change()
            self.after(3000, self._load_snapshots)


# ─── Main Application ────────────────────────────────────────────────────────
class ProxmoxSpiceManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Proxmox SPICE Manager v{APP_VERSION}")
        self.geometry("1100x640")
        self.configure(bg=C["base"])
        self.minsize(900, 500)

        self.config_data = load_config()
        self.current_cluster = None
        self.auth_cache = {}

        saved_theme = self.config_data.get("theme", "Catppuccin Mocha")
        if saved_theme in THEMES:
            C.update(THEMES[saved_theme])

        if not self.config_data.get("prereqs_ok"):
            self.update_idletasks()
            if not self._check_prereqs():
                self.destroy()
                return
            self.config_data["prereqs_ok"] = True
            save_config(self.config_data)

        migrate_secrets(self.config_data)
        self._build_ui()
        self._populate_clusters()

        if self.config_data.get("clusters"):
            self.cluster_listbox.select_set(0)
            self.current_cluster = self.config_data["clusters"][0]
            self.after(100, self._refresh_vms)

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

    def _build_ui(self):
        for widget in self.winfo_children():
            widget.destroy()
        self.configure(bg=C["base"])

        # Fonts
        FONT = "Segoe UI"
        MONO = "Consolas"

        header = tk.Frame(self, bg=C["crust"], height=52)
        header.pack(fill="x")
        header.pack_propagate(False)

        title_frame = tk.Frame(header, bg=C["crust"])
        title_frame.pack(side="left", padx=16)
        tk.Label(
            title_frame, text="◈", bg=C["crust"], fg=C["mauve"],
            font=(FONT, 18),
        ).pack(side="left", padx=(0, 8))
        tk.Label(
            title_frame, text=f"Proxmox SPICE Manager v{APP_VERSION}",
            bg=C["crust"], fg=C["text"], font=(FONT, 12, "bold"),
        ).pack(side="left")

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
        HoverButton(
            header, text="Check Prerequisites",
            command=self._recheck_prereqs,
            hover_bg=C["mantle"], hover_fg=C["text"], **hbtn,
        ).pack(side="right", padx=(0, 4))

        theme_frame = tk.Frame(header, bg=C["crust"])
        theme_frame.pack(side="right", padx=(0, 8))
        tk.Label(
            theme_frame, text="Theme:", bg=C["crust"], fg=C["overlay0"],
            font=(FONT, 9),
        ).pack(side="left", padx=(0, 6))

        self.theme_var = tk.StringVar(
            value=self.config_data.get("theme", "Catppuccin Mocha")
        )
        theme_menu = ttk.Combobox(
            theme_frame, textvariable=self.theme_var,
            values=list(THEMES.keys()), state="readonly", width=18,
            font=(FONT, 9),
        )
        theme_menu.pack(side="left")
        theme_menu.bind("<<ComboboxSelected>>", self._on_theme_change)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "TCombobox", fieldbackground=C["surface0"],
            background=C["surface1"], foreground=C["text"],
            arrowcolor=C["text"], borderwidth=0, relief="flat",
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", C["surface0"])],
            foreground=[("readonly", C["text"])],
            background=[("readonly", C["surface1"])],
        )

        tk.Frame(self, bg=C["mauve"], height=2).pack(fill="x")

        body = tk.Frame(self, bg=C["base"])
        body.pack(fill="both", expand=True)

        # Sidebar
        sidebar = tk.Frame(body, bg=C["mantle"], width=200)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(
            sidebar, text="CLUSTERS", bg=C["mantle"], fg=C["overlay0"],
            font=(FONT, 8, "bold"), anchor="w",
        ).pack(fill="x", padx=14, pady=(14, 6))
        tk.Frame(sidebar, bg=C["surface0"], height=1).pack(
            fill="x", padx=12, pady=(0, 6)
        )

        self.cluster_listbox = tk.Listbox(
            sidebar, bg=C["mantle"], fg=C["text"],
            selectbackground=C["surface0"], selectforeground=C["blue"],
            relief="flat", font=(FONT, 10), highlightthickness=0,
            activestyle="none", borderwidth=0,
        )
        self.cluster_listbox.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.cluster_listbox.bind("<<ListboxSelect>>", self._on_cluster_select)

        tk.Frame(sidebar, bg=C["surface0"], height=1).pack(fill="x", padx=12)

        sb_btn = {
            "bg": C["surface0"], "fg": C["subtext0"], "relief": "flat",
            "padx": 10, "pady": 4, "font": (FONT, 9),
            "activebackground": C["surface1"], "activeforeground": C["text"],
        }

        btn_bar = tk.Frame(sidebar, bg=C["mantle"])
        btn_bar.pack(fill="x", padx=8, pady=(10, 0))
        HoverButton(
            btn_bar, text="+ Add", command=self._add_cluster,
            hover_bg=C["surface1"], hover_fg=C["text"], **sb_btn,
        ).pack(side="left", padx=(0, 4))
        HoverButton(
            btn_bar, text="Edit", command=self._edit_cluster,
            hover_bg=C["surface1"], hover_fg=C["text"], **sb_btn,
        ).pack(side="left", padx=(0, 4))
        HoverButton(
            btn_bar, text="Remove", command=self._remove_cluster,
            hover_bg=C["surface1"], hover_fg=C["red"], **sb_btn,
        ).pack(side="left")

        io_bar = tk.Frame(sidebar, bg=C["mantle"])
        io_bar.pack(fill="x", padx=8, pady=(6, 10))
        HoverButton(
            io_bar, text="Import", command=self._import_config,
            hover_bg=C["surface1"], hover_fg=C["text"], **sb_btn,
        ).pack(side="left", padx=(0, 4), expand=True, fill="x")
        HoverButton(
            io_bar, text="Export", command=self._export_config,
            hover_bg=C["surface1"], hover_fg=C["text"], **sb_btn,
        ).pack(side="left", expand=True, fill="x")

        tk.Frame(body, bg=C["surface0"], width=1).pack(side="left", fill="y")

        # Content
        content = tk.Frame(body, bg=C["base"])
        content.pack(side="right", fill="both", expand=True)

        toolbar = tk.Frame(content, bg=C["base"])
        toolbar.pack(fill="x", padx=16, pady=(14, 0))

        self.status_label = tk.Label(
            toolbar, text="Select a cluster to view VMs", bg=C["base"],
            fg=C["overlay0"], font=(FONT, 10), anchor="w",
        )
        self.status_label.pack(side="left")

        HoverButton(
            toolbar, text="Refresh", command=self._refresh_vms,
            bg=C["surface0"], fg=C["subtext0"], relief="flat", padx=12,
            pady=4, hover_bg=C["surface1"], hover_fg=C["text"],
            font=(FONT, 9),
        ).pack(side="right")

        self._all_vm_rows = []

        # Filter row
        filter_row = tk.Frame(content, bg=C["surface1"])
        filter_row.pack(fill="x", padx=16, pady=(8, 0))

        fentry = {
            "bg": C["crust"], "fg": C["text"], "insertbackground": C["text"],
            "relief": "flat", "font": (FONT, 9), "highlightthickness": 1,
            "highlightcolor": C["blue"], "highlightbackground": C["surface1"],
        }

        tk.Label(
            filter_row, text="Filter:", bg=C["surface1"], fg=C["overlay0"],
            font=(FONT, 9),
        ).pack(side="left", padx=(4, 4))

        self._filter_vars = {}
        self._filter_entries = {}
        filter_defs = [
            ("vmid", "VMID"), ("name", "Name"), ("node", "Node"),
            ("pool", "Pool"), ("snaps", "Snaps"), ("status", "Status"),
        ]

        for col_id, placeholder in filter_defs:
            var = tk.StringVar()
            var.trace_add("write", lambda *args: self._apply_filters())
            self._filter_vars[col_id] = var

            entry = tk.Entry(filter_row, textvariable=var, width=1, **fentry)
            entry.pack(
                side="left", fill="x", expand=True, ipady=3, padx=(0, 1)
            )
            entry.insert(0, placeholder)
            entry.config(fg=C["overlay0"])
            entry.bind(
                "<FocusIn>",
                lambda e, en=entry, ph=placeholder, v=var:
                    self._filter_focus_in(en, ph, v),
            )
            entry.bind(
                "<FocusOut>",
                lambda e, en=entry, ph=placeholder, v=var:
                    self._filter_focus_out(en, ph, v),
            )
            self._filter_entries[col_id] = entry

        HoverButton(
            filter_row, text=" X ", command=self._clear_filters,
            bg=C["surface1"], fg=C["overlay0"], relief="flat", padx=4,
            pady=1, hover_bg=C["surface2"], hover_fg=C["red"],
            font=(FONT, 9),
        ).pack(side="right", padx=(2, 2))

        # VM Table
        table_frame = tk.Frame(content, bg=C["base"])
        table_frame.pack(fill="both", expand=True, padx=16, pady=(10, 0))

        columns = ("vmid", "name", "node", "pool", "snaps", "status")
        self.vm_tree = ttk.Treeview(
            table_frame, columns=columns, show="headings",
            selectmode="extended", height=12,
        )

        style.configure(
            "Treeview", background=C["surface0"], foreground=C["text"],
            fieldbackground=C["surface0"], rowheight=32,
            font=(FONT, 10), borderwidth=0,
        )
        style.configure(
            "Treeview.Heading", background=C["surface1"],
            foreground=C["subtext0"], font=(FONT, 9, "bold"),
            borderwidth=0, relief="flat",
        )
        style.map(
            "Treeview",
            background=[("selected", C["surface1"])],
            foreground=[("selected", C["blue"])],
        )
        style.map("Treeview.Heading", background=[("active", C["surface2"])])

        for col in columns:
            self.vm_tree.heading(
                col, text=col.upper(),
                command=lambda c=col: self._sort_tree(c),
            )

        self.vm_tree.column("vmid", width=70, minwidth=50, anchor="center")
        self.vm_tree.column("name", width=220, minwidth=120)
        self.vm_tree.column("node", width=120, minwidth=80)
        self.vm_tree.column("pool", width=100, minwidth=60)
        self.vm_tree.column("snaps", width=70, minwidth=50, anchor="center")
        self.vm_tree.column("status", width=110, minwidth=70, anchor="center")

        self._all_columns = list(columns)
        if not hasattr(self, "_tree_sort_col"):
            self._tree_sort_col = None
            self._tree_sort_asc = True
        if not hasattr(self, "_display_columns"):
            self._display_columns = list(columns)
        elif set(self._display_columns) != set(columns):
            self._display_columns = list(columns)
        self._drag_col = None
        self._drag_start_x = None

        self.vm_tree.bind("<ButtonPress-1>", self._on_heading_press)
        self.vm_tree.bind("<B1-Motion>", self._on_heading_drag)
        self.vm_tree.bind("<ButtonRelease-1>", self._on_heading_release)

        saved_order = self.config_data.get("column_order")
        if saved_order and set(saved_order) == set(columns):
            self._display_columns = saved_order
        self.vm_tree["displaycolumns"] = self._display_columns

        if self._tree_sort_col:
            for c in columns:
                label = c.upper()
                if c == self._tree_sort_col:
                    label += "  ▲" if self._tree_sort_asc else "  ▼"
                self.vm_tree.heading(c, text=label)

        scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.vm_tree.yview
        )
        style.configure(
            "Vertical.TScrollbar", background=C["surface0"],
            troughcolor=C["surface0"], arrowcolor=C["overlay0"], borderwidth=0,
        )
        self.vm_tree.configure(yscrollcommand=scrollbar.set)
        self.vm_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.vm_tree.bind("<Double-1>", self._on_vm_double_click)

        # Bottom bar
        tk.Frame(content, bg=C["surface0"], height=1).pack(fill="x", padx=16)
        bottom = tk.Frame(content, bg=C["base"])
        bottom.pack(fill="x", padx=16, pady=12)

        HoverButton(
            bottom, text=" Launch SPICE ", command=self._launch_spice,
            bg=C["green"], fg=C["crust"], relief="flat", padx=16, pady=8,
            hover_bg=C["teal"], hover_fg=C["crust"],
            font=(FONT, 11, "bold"),
        ).pack(side="right")

        power_frame = tk.Frame(bottom, bg=C["base"])
        power_frame.pack(side="left")

        pbtn = {"relief": "flat", "padx": 10, "pady": 8, "font": (FONT, 10)}
        HoverButton(
            power_frame, text=" Start ", command=self._start_vm,
            bg=C["surface0"], fg=C["green"], hover_bg=C["surface1"],
            hover_fg=C["green"], **pbtn,
        ).pack(side="left", padx=(0, 4))
        HoverButton(
            power_frame, text=" Shutdown ", command=self._shutdown_vm,
            bg=C["surface0"], fg=C["yellow"], hover_bg=C["surface1"],
            hover_fg=C["yellow"], **pbtn,
        ).pack(side="left", padx=(0, 4))
        HoverButton(
            power_frame, text=" Force Stop ", command=self._stop_vm,
            bg=C["surface0"], fg=C["red"], hover_bg=C["surface1"],
            hover_fg=C["red"], **pbtn,
        ).pack(side="left", padx=(0, 4))
        HoverButton(
            power_frame, text=" Snapshots ", command=self._show_snapshots,
            bg=C["surface0"], fg=C["lavender"], hover_bg=C["surface1"],
            hover_fg=C["lavender"], **pbtn,
        ).pack(side="left", padx=(0, 4))
        HoverButton(
            power_frame, text=" Quick Rollback ",
            command=self._quick_rollback,
            bg=C["surface0"], fg=C["peach"], hover_bg=C["surface1"],
            hover_fg=C["peach"], **pbtn,
        ).pack(side="left")

    # ── Theme ─────────────────────────────────────────────────────────────────
    def _on_theme_change(self, event=None):
        theme_name = self.theme_var.get()
        if theme_name not in THEMES:
            return
        C.update(THEMES[theme_name])
        self.config_data["theme"] = theme_name
        save_config(self.config_data)

        selected_idx = None
        sel = self.cluster_listbox.curselection()
        if sel:
            selected_idx = sel[0]

        self._build_ui()
        self._populate_clusters()

        if selected_idx is not None:
            self.cluster_listbox.select_set(selected_idx)
            clusters = self.config_data.get("clusters", [])
            if selected_idx < len(clusters):
                self.current_cluster = clusters[selected_idx]

        if self.current_cluster:
            self.after(100, self._refresh_vms)

    # ── Clusters ──────────────────────────────────────────────────────────────
    def _populate_clusters(self):
        self.cluster_listbox.delete(0, "end")
        for cluster in self.config_data.get("clusters", []):
            self.cluster_listbox.insert("end", f"  ◆  {cluster['name']}")

    def _get_selected_cluster(self):
        sel = self.cluster_listbox.curselection()
        if not sel:
            return None
        idx = sel[0]
        clusters = self.config_data.get("clusters", [])
        return (idx, clusters[idx]) if idx < len(clusters) else None

    def _on_cluster_select(self, event=None):
        result = self._get_selected_cluster()
        if result:
            _, cluster = result
            self.current_cluster = cluster
            self._refresh_vms()

    def _add_cluster(self):
        dlg = ClusterDialog(self, config_data=self.config_data)
        if dlg.result:
            self.config_data.setdefault("clusters", []).append(dlg.result)
            save_config(self.config_data)
            if getattr(dlg, "_pending_secret", None):
                save_secret(dlg.result["name"], dlg._pending_secret, self.config_data)
            self._populate_clusters()

    def _edit_cluster(self):
        result = self._get_selected_cluster()
        if not result:
            messagebox.showinfo("No Selection", "Select a cluster to edit.", parent=self)
            return
        idx, cluster = result
        dlg = ClusterDialog(self, cluster, config_data=self.config_data)
        if dlg.result:
            self.config_data["clusters"][idx] = dlg.result
            save_config(self.config_data)
            if getattr(dlg, "_pending_secret", None):
                save_secret(dlg.result["name"], dlg._pending_secret, self.config_data)
            self._populate_clusters()

    def _remove_cluster(self):
        result = self._get_selected_cluster()
        if not result:
            return
        idx, cluster = result
        if messagebox.askyesno("Confirm", f"Remove cluster '{cluster['name']}'?", parent=self):
            delete_secret(cluster["name"], self.config_data)
            self.config_data["clusters"].pop(idx)
            save_config(self.config_data)
            self._populate_clusters()
            self.vm_tree.delete(*self.vm_tree.get_children())
            self.current_cluster = None

    # ── Import / Export ───────────────────────────────────────────────────────
    def _export_config(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json", filetypes=[("JSON files", "*.json")]
        )
        if not path:
            return
        if not messagebox.askyesno(
            "Export",
            "This file will contain API secrets in plain text.\n"
            "Keep it safe. Proceed?",
            parent=self,
        ):
            return

        export_data = copy.deepcopy(self.config_data)
        for cluster in export_data.get("clusters", []):
            if cluster.get("auth_method") == "token":
                secret = get_secret(cluster["name"], self.config_data)
                if secret:
                    cluster["token_secret"] = secret
                # Don't export the encrypted blob
                cluster.pop("token_secret_enc", None)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2)
            messagebox.showinfo("Exported", f"Saved to:\n{path}", parent=self)
        except Exception as e:
            messagebox.showerror("Export Failed", str(e), parent=self)

    def _import_config(self):
        path = filedialog.askopenfilename(filetypes=[("JSON files", "*.json")])
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                imported = json.load(f)
        except Exception as e:
            messagebox.showerror("Import Failed", str(e), parent=self)
            return

        new_clusters = imported.get("clusters", [])
        if not new_clusters:
            messagebox.showinfo("Empty", "No clusters in file.", parent=self)
            return

        existing = [c["name"] for c in self.config_data.get("clusters", [])]
        for cluster in new_clusters:
            secret = cluster.pop("token_secret", None)
            cluster.pop("token_secret_enc", None)  # Can't decrypt another user's DPAPI blob
            if cluster["name"] in existing:
                cluster["name"] = f"{cluster['name']} (Imported)"
            self.config_data.setdefault("clusters", []).append(cluster)
            if secret:
                save_secret(cluster["name"], secret, self.config_data)

        save_config(self.config_data)
        self._populate_clusters()
        messagebox.showinfo("Imported", f"Imported {len(new_clusters)} cluster(s).", parent=self)

    # ── Auth ──────────────────────────────────────────────────────────────────
    def _get_auth(self, cluster):
        name = cluster["name"]
        if cluster["auth_method"] == "token":
            token_id = cluster.get("token_id")
            token_secret = get_secret(name, self.config_data)
            if token_id and token_secret:
                return {"token_id": token_id, "token_secret": token_secret}
            messagebox.showerror("Auth Error", "Token secret not found or could not be decrypted.", parent=self)
            return None

        if name in self.auth_cache:
            return self.auth_cache[name]

        prompt = PasswordPrompt(self, cluster.get("username", "root@pam"), cluster["host"])
        if not prompt.result:
            return None

        auth = authenticate_password(cluster["host"], cluster.get("username", "root@pam"), prompt.result)
        if auth:
            self.auth_cache[name] = auth
            return auth

        messagebox.showerror("Auth Failed", "Could not authenticate.", parent=self)
        return None

    # ── VM Refresh ────────────────────────────────────────────────────────────
    def _refresh_vms(self):
        if not self.current_cluster:
            return
        self.status_label.config(text="Loading VMs...", fg=C["yellow"])
        self.update_idletasks()

        def fetch():
            cluster = self.current_cluster
            auth = self._get_auth(cluster)
            if not auth:
                self.after(0, lambda: self.status_label.config(text="Auth failed", fg=C["red"]))
                return

            data = api_request(cluster["host"], "/api2/json/cluster/resources?type=vm", auth=auth)
            if "error" in data:
                self.after(0, lambda d=data: self.status_label.config(text=f"Error: {d['error']}", fg=C["red"]))
                return

            all_vms = data.get("data", [])
            if not all_vms:
                self.after(0, lambda: (self.vm_tree.delete(*self.vm_tree.get_children()), self.status_label.config(text="No VMs found", fg=C["red"])))
                return

            qemu_vms = [v for v in all_vms if v.get("type") == "qemu"]

            spice_vms = []
            for vm in qemu_vms:
                config = api_request(cluster["host"], f"/api2/json/nodes/{vm.get('node')}/qemu/{vm.get('vmid')}/config", auth=auth)
                if "error" in config:
                    continue
                vga = str(config.get("data", {}).get("vga", "")).lower()
                if "qxl" in vga or "spice" in vga:
                    snap_data = api_request(cluster["host"], f"/api2/json/nodes/{vm.get('node')}/qemu/{vm.get('vmid')}/snapshot", auth=auth)
                    snaps = snap_data.get("data", []) if "error" not in snap_data else []
                    vm["_snap_count"] = len([s for s in snaps if s.get("name") != "current"])
                    spice_vms.append(vm)

            def update_ui():
                self.vm_tree.delete(*self.vm_tree.get_children())
                if not spice_vms:
                    self._all_vm_rows = []
                    self.status_label.config(text=f"No SPICE VMs found ({len(qemu_vms)} checked)", fg=C["red"])
                    return

                spice_vms.sort(key=lambda v: v.get("vmid", 0))
                self._all_vm_rows = []
                for vm in spice_vms:
                    status = vm.get("status", "?")
                    display_status = "● running" if status == "running" else "○ stopped"
                    tag = "running" if status == "running" else "stopped"
                    snap_count = vm.get("_snap_count", 0)
                    snap_display = f"📸 {snap_count}" if snap_count > 0 else "—"
                    row = (str(vm.get("vmid", "?")), vm.get("name", "unnamed"), vm.get("node", "?"), vm.get("pool", "—"), snap_display, display_status)
                    self._all_vm_rows.append((row, tag))

                self._apply_filters()
                self.status_label.config(text=f"◈  {cluster['name']}  —  {len(spice_vms)} SPICE VMs", fg=C["text"])

                if hasattr(self, "_display_columns"):
                    self.vm_tree["displaycolumns"] = self._display_columns
                if self._tree_sort_col:
                    self._reapply_sort()

            self.after(0, update_ui)

        threading.Thread(target=fetch, daemon=True).start()

    # ── Filtering ─────────────────────────────────────────────────────────────
    def _filter_focus_in(self, entry, placeholder, var):
        if entry.get() == placeholder:
            entry.delete(0, "end")
            entry.config(fg=C["text"])

    def _filter_focus_out(self, entry, placeholder, var):
        if not entry.get():
            entry.insert(0, placeholder)
            entry.config(fg=C["overlay0"])

    def _apply_filters(self):
        if not hasattr(self, "_all_vm_rows"):
            return
        col_indices = {"vmid": 0, "name": 1, "node": 2, "pool": 3, "snaps": 4, "status": 5}
        placeholders = {"vmid": "VMID", "name": "Name", "node": "Node", "pool": "Pool", "snaps": "Snaps", "status": "Status"}

        filters = {}
        for col_id, var in self._filter_vars.items():
            val = var.get().strip().lower()
            if val and val != placeholders.get(col_id, "").lower():
                filters[col_id] = val

        self.vm_tree.delete(*self.vm_tree.get_children())
        visible = 0
        for row, tag in self._all_vm_rows:
            if all(f_text in str(row[col_indices.get(cid, -1)]).lower() for cid, f_text in filters.items()):
                self.vm_tree.insert("", "end", values=row, tags=(tag,))
                visible += 1

        self.vm_tree.tag_configure("running", foreground=C["green"])
        self.vm_tree.tag_configure("stopped", foreground=C["overlay0"])

        if self._tree_sort_col:
            self._reapply_sort()

        if filters and visible != len(self._all_vm_rows):
            self.status_label.config(text=f"Showing {visible} of {len(self._all_vm_rows)} VMs", fg=C["sapphire"])

    def _clear_filters(self):
        placeholders = {"vmid": "VMID", "name": "Name", "node": "Node", "pool": "Pool", "snaps": "Snaps", "status": "Status"}
        for col_id, var in self._filter_vars.items():
            var.set("")
            entry = self._filter_entries[col_id]
            entry.delete(0, "end")
            entry.insert(0, placeholders[col_id])
            entry.config(fg=C["overlay0"])

    # ── Sorting ───────────────────────────────────────────────────────────────
    def _reapply_sort(self):
        col = self._tree_sort_col
        if not col:
            return
        columns = ("vmid", "name", "node", "pool", "snaps", "status")
        rows = [(self.vm_tree.set(iid, col), iid) for iid in self.vm_tree.get_children("")]
        if col == "vmid":
            rows.sort(key=lambda r: int(r[0]) if r[0].isdigit() else 0, reverse=not self._tree_sort_asc)
        else:
            rows.sort(key=lambda r: r[0].lower(), reverse=not self._tree_sort_asc)
        for idx, (_, iid) in enumerate(rows):
            self.vm_tree.move(iid, "", idx)
        for c in columns:
            label = c.upper()
            if c == col:
                label += "  ▲" if self._tree_sort_asc else "  ▼"
            self.vm_tree.heading(c, text=label)

    def _sort_tree(self, col):
        if self._tree_sort_col == col:
            self._tree_sort_asc = not self._tree_sort_asc
        else:
            self._tree_sort_col = col
            self._tree_sort_asc = True
        self._reapply_sort()

    # ── Column reorder ────────────────────────────────────────────────────────
    def _col_from_x(self, x):
        if self.vm_tree.identify_region(x, 5) == "heading":
            col_id = self.vm_tree.identify_column(x)
            if col_id:
                idx = int(col_id.replace("#", "")) - 1
                if 0 <= idx < len(self._display_columns):
                    return idx
        return None

    def _on_heading_press(self, event):
        if self.vm_tree.identify_region(event.x, event.y) == "heading":
            self._drag_col, self._drag_start_x = self._col_from_x(event.x), event.x
        else:
            self._drag_col, self._drag_start_x = None, None

    def _on_heading_drag(self, event):
        if self._drag_col is not None and self._drag_start_x is not None and abs(event.x - self._drag_start_x) > 20:
            self.vm_tree.config(cursor="sb_h_double_arrow")

    def _on_heading_release(self, event):
        self.vm_tree.config(cursor="")
        if self._drag_col is None or self._drag_start_x is None or abs(event.x - self._drag_start_x) < 20:
            self._drag_col = self._drag_start_x = None
            return
        target_idx = self._col_from_x(event.x)
        if target_idx is None or target_idx == self._drag_col:
            self._drag_col = self._drag_start_x = None
            return
        cols = list(self._display_columns)
        cols.insert(target_idx, cols.pop(self._drag_col))
        self._display_columns = cols
        self.vm_tree["displaycolumns"] = cols
        self.config_data["column_order"] = cols
        save_config(self.config_data)
        self._drag_col = self._drag_start_x = None

    # ── VM Selection ──────────────────────────────────────────────────────────
    def _get_selected_vms(self):
        sel = self.vm_tree.selection()
        if not sel:
            return []
        vms = []
        for iid in sel:
            values = self.vm_tree.item(iid, "values")
            status = values[5].replace("● ", "").replace("○ ", "").strip()
            vms.append({"vmid": values[0], "name": values[1], "node": values[2], "pool": values[3], "snaps": values[4], "status": status})
        return vms

    def _get_selected_vm(self):
        vms = self._get_selected_vms()
        if not vms:
            return None
        if len(vms) > 1:
            messagebox.showinfo("Single Selection", "Select a single VM.", parent=self)
            return None
        return vms[0]

    def _on_vm_double_click(self, event):
        self._launch_spice()

    # ── SPICE Launch ──────────────────────────────────────────────────────────
    def _launch_spice(self):
        vm = self._get_selected_vm()
        if not vm:
            return
        if vm["status"] != "running":
            messagebox.showwarning("Not Running", f"{vm['name']} is not running.", parent=self)
            return

        cluster = self.current_cluster
        auth = self._get_auth(cluster)
        if not auth:
            return

        self.status_label.config(text=f"Connecting to {vm['name']}...", fg=C["yellow"])
        self.update_idletasks()

        def connect():
            data = api_request(
                cluster["host"],
                f"/api2/json/nodes/{vm['node']}/qemu/{vm['vmid']}/spiceproxy",
                method="POST", auth=auth,
            )
            spice_data = data.get("data")

            if "error" in data or not spice_data or not spice_data.get("type"):
                err = data.get("error", "Unknown Error")
                self.after(0, lambda: (
                    self.status_label.config(text="Connection failed", fg=C["red"]),
                    messagebox.showerror("SPICE Error", err, parent=self),
                ))
                return

            rv_path = _find_remote_viewer()
            if not rv_path:
                self.after(0, lambda: (
                    self.status_label.config(text="remote-viewer.exe not found", fg=C["red"]),
                    messagebox.showerror(
                        "Missing",
                        f"remote-viewer.exe not found.\n\n"
                        f"Download virt-viewer from:\n{VIRT_VIEWER_DOWNLOAD}",
                        parent=self,
                    ),
                ))
                return

            vv_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", prefix="proxmox-spice-", suffix=".vv",
                    delete=False, dir=tempfile.gettempdir(),
                    encoding="utf-8",
                ) as f:
                    vv_path = f.name
                    f.write("[virt-viewer]\n")
                    for key in ("type", "host", "port", "tls-port", "password", "proxy", "host-subject", "ca"):
                        f.write(f"{key}={spice_data.get(key, '')}\n")
                    f.write("toggle-fullscreen=shift+f11\nrelease-cursor=shift+f12\nsecure-attention=ctrl+alt+end\ndelete-this-file=1\n")

                subprocess.Popen([rv_path, vv_path])
                self.after(0, lambda: self.status_label.config(
                    text=f"Connected to {vm['name']} ({vm['vmid']})", fg=C["green"]
                ))
            except Exception as e:
                # Clean up .vv file (contains SPICE password) if launch failed
                if vv_path:
                    try:
                        os.unlink(vv_path)
                    except OSError:
                        pass
                self.after(0, lambda: messagebox.showerror("Launch Error", str(e), parent=self))

        threading.Thread(target=connect, daemon=True).start()

    # ── Power Actions ─────────────────────────────────────────────────────────
    def _vm_power_action(self, action, action_label):
        vms = self._get_selected_vms()
        if not vms:
            messagebox.showinfo("No Selection", "Select one or more VMs.", parent=self)
            return

        valid = [v for v in vms if v["status"] != "running"] if action == "start" else [v for v in vms if v["status"] == "running"]
        skipped = [v for v in vms if v not in valid]

        if not valid:
            messagebox.showinfo("No Action", "All selected VMs are already in the target state.", parent=self)
            return

        names = ", ".join(f"{v['name']} ({v['vmid']})" for v in valid)
        if action == "stop" and not messagebox.askyesno("Force Stop", f"Force stop?\n\n{names}\n\nUnsaved data may be lost.", parent=self):
            return
        if action == "shutdown" and not messagebox.askyesno("Shutdown", f"Shutdown?\n\n{names}", parent=self):
            return
        if action == "start" and len(valid) > 1 and not messagebox.askyesno("Start", f"Start {len(valid)} VMs?\n\n{names}", parent=self):
            return

        cluster = self.current_cluster
        auth = self._get_auth(cluster)
        if not auth:
            return

        self.status_label.config(text=f"{action_label} {len(valid)} VM(s)...", fg=C["yellow"])
        poll_auth = auth

        def do_action():
            errors = []
            for vm in valid:
                data = api_request(cluster["host"], f"/api2/json/nodes/{vm['node']}/qemu/{vm['vmid']}/status/{action}", method="POST", auth=auth)
                err = data.get("error")
                if err and "already" not in str(err).lower():
                    errors.append(f"{vm['name']}: {err}")

            expected = {str(vm["vmid"]): ("running" if action == "start" else "stopped") for vm in valid}

            def on_done():
                if errors:
                    self.status_label.config(text="Some actions failed", fg=C["red"])
                    messagebox.showerror("Errors", "\n".join(errors), parent=self)
                else:
                    self.status_label.config(text=f"{action_label} sent to {len(valid)} VM(s)", fg=C["green"])

            self.after(0, on_done)
            self.after(0, lambda: self._poll_until_changed(expected, auth=poll_auth))

        threading.Thread(target=do_action, daemon=True).start()

    def _start_vm(self):
        self._vm_power_action("start", "Starting")

    def _shutdown_vm(self):
        self._vm_power_action("shutdown", "Shutting down")

    def _stop_vm(self):
        self._vm_power_action("stop", "Force stopping")

    # ── Quick Rollback ────────────────────────────────────────────────────────
    def _quick_rollback(self):
        vm = self._get_selected_vm()
        if not vm:
            return
        cluster = self.current_cluster
        auth = self._get_auth(cluster)
        if not auth:
            return

        saved_auth = auth

        def fetch():
            data = api_request(cluster["host"], f"/api2/json/nodes/{vm['node']}/qemu/{vm['vmid']}/snapshot", auth=saved_auth)
            if "error" in data:
                self.after(0, lambda: messagebox.showerror("Error", data["error"], parent=self))
                return
            snaps = [s for s in data.get("data", []) if s.get("name") != "current"]
            if not snaps:
                self.after(0, lambda: messagebox.showinfo("No Snapshots", "No snapshots found.", parent=self))
                return

            latest = max(snaps, key=lambda s: s.get("snaptime", 0))
            snap_name = latest.get("name")

            def confirm():
                if not messagebox.askyesno("Quick Rollback", f"Rollback to '{snap_name}'?", parent=self):
                    return
                self.status_label.config(text=f"Rolling back to '{snap_name}'...", fg=C["yellow"])

                def do_rb():
                    rb = api_request(cluster["host"], f"/api2/json/nodes/{vm['node']}/qemu/{vm['vmid']}/snapshot/{snap_name}/rollback", method="POST", auth=saved_auth)
                    if "error" in rb:
                        self.after(0, lambda: messagebox.showerror("Failed", rb["error"], parent=self))
                    else:
                        self.after(0, lambda: self.status_label.config(text=f"Rolled back to '{snap_name}'", fg=C["green"]))
                        self.after(0, lambda: self._poll_until_changed({str(vm["vmid"]): "stopped"}, auth=saved_auth))

                threading.Thread(target=do_rb, daemon=True).start()

            self.after(0, confirm)

        threading.Thread(target=fetch, daemon=True).start()

    # ── Polling ───────────────────────────────────────────────────────────────
    def _poll_until_changed(self, expected, auth=None, attempts=0, max_attempts=12):
        if attempts >= max_attempts:
            self._refresh_vms()
            return
        cluster = self.current_cluster
        if not auth:
            auth = self._get_auth(cluster)
        if not auth:
            return
        saved_auth = auth

        def check():
            data = api_request(cluster["host"], "/api2/json/cluster/resources?type=vm", auth=saved_auth)
            if "error" in data:
                return
            vms = data.get("data", [])
            all_ok = all(next((v for v in vms if str(v.get("vmid")) == vmid), {}).get("status") == exp for vmid, exp in expected.items())
            if all_ok:
                self.after(0, self._refresh_vms)
            else:
                self.after(0, lambda: self.after(10000, lambda: self._poll_until_changed(expected, auth=saved_auth, attempts=attempts + 1)))

        threading.Thread(target=check, daemon=True).start()

    def _poll_snap_changed(self, vmid, node, old_count, auth=None, attempts=0, max_attempts=12):
        if attempts >= max_attempts:
            self._refresh_vms()
            return
        cluster = self.current_cluster
        if not auth:
            auth = self._get_auth(cluster)
        if not auth:
            return
        saved_auth = auth

        def check():
            snap_data = api_request(cluster["host"], f"/api2/json/nodes/{node}/qemu/{vmid}/snapshot", auth=saved_auth)
            if "error" in snap_data:
                return
            current = len([s for s in snap_data.get("data", []) if s.get("name") != "current"])
            if current != old_count:
                self.after(0, self._refresh_vms)
            else:
                self.after(0, lambda: self.after(10000, lambda: self._poll_snap_changed(vmid, node, old_count, auth=saved_auth, attempts=attempts + 1)))

        threading.Thread(target=check, daemon=True).start()

    # ── Snapshots ─────────────────────────────────────────────────────────────
    def _show_snapshots(self):
        vm = self._get_selected_vm()
        if not vm:
            return
        auth = self._get_auth(self.current_cluster)
        if not auth:
            return
        saved_auth = auth
        SnapshotDialog(self, vm, self.current_cluster, auth, on_change=lambda vmid, node, old_count: self._poll_snap_changed(vmid, node, old_count, auth=saved_auth))

    # ── Windows Shortcut ──────────────────────────────────────────────────────
    def _create_shortcut(self):
        """Create a Start Menu shortcut for this app."""
        try:
            start_menu = Path(os.environ.get(
                "APPDATA", ""
            )) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            start_menu.mkdir(parents=True, exist_ok=True)

            shortcut_path = start_menu / "Proxmox SPICE Manager.lnk"
            script_path = Path(os.path.abspath(__file__))

            # Use PowerShell to create .lnk — encode as base64 to safely
            # handle paths containing spaces, quotes, or special characters.
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
