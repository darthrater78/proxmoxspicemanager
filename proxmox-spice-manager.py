#!/usr/bin/env python3
"""
Proxmox SPICE Connection Manager — Linux
A GUI app to manage and launch SPICE console sessions to Proxmox VMs.
Connections are saved to ~/.config/proxmox-spice/connections.json

Dependencies: python3-tkinter, python3-keyring, remote-viewer (virt-viewer)

Install on Fedora:  sudo dnf install python3-tkinter python3-keyring virt-viewer
Install on Debian:  sudo apt install python3-tk python3-keyring virt-viewer

VERSION 3.0.0
"""

import copy
import fcntl
import importlib
import ipaddress
import json
import logging
import logging.handlers
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import ssl
import urllib.request
import urllib.parse
import urllib.error
import webbrowser
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter import font as tkfont

APP_ID = "proxmox-spice-manager"
APP_VERSION = "3.0.0"
REPO_URL = "https://github.com/darthrater78/proxmoxspicemanager"


# ─── Debug Logger ────────────────────────────────────────────────────────────
class DebugLogger:
    _LOG_DIR = Path.home() / ".config" / "proxmox-spice"
    _LOG_FILE = _LOG_DIR / "debug.log"
    _MAX_BYTES = 5 * 1024 * 1024
    _logger = logging.getLogger("proxmox-spice-debug")
    _handler = None
    enabled = False

    @classmethod
    def set_enabled(cls, on: bool):
        if on == cls.enabled:
            return
        cls.enabled = on
        if on:
            cls._LOG_DIR.mkdir(parents=True, exist_ok=True)
            handler = logging.handlers.RotatingFileHandler(
                cls._LOG_FILE, maxBytes=cls._MAX_BYTES, backupCount=1,
                encoding="utf-8",
            )
            handler.setFormatter(
                logging.Formatter("%(asctime)s.%(msecs)03d  %(message)s",
                                  datefmt="%Y-%m-%d %H:%M:%S")
            )
            cls._logger.addHandler(handler)
            cls._logger.setLevel(logging.DEBUG)
            cls._handler = handler
            cls.log("--- Debug logging started ---")
        else:
            cls.log("--- Debug logging stopped ---")
            if cls._handler:
                cls._logger.removeHandler(cls._handler)
                cls._handler.close()
                cls._handler = None

    @classmethod
    def log(cls, message: str):
        if cls.enabled:
            cls._logger.debug(message)

    @classmethod
    def log_file_path(cls) -> str:
        return str(cls._LOG_FILE)


# ─── Single-Instance Lock ────────────────────────────────────────────────────
_lock_fd = None


def _acquire_instance_lock() -> bool:
    global _lock_fd
    lock_path = Path.home() / ".config" / "proxmox-spice" / ".instance.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _lock_fd = open(lock_path, "w", encoding="utf-8")
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (OSError, IOError):
        return False


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

DEFAULT_THEME = "Catppuccin Mocha"
DEFAULT_ACCENT = "Orange"

# Accent presets name a colour slot, so each one takes the active theme's shade of it
ACCENTS = {
    "Orange": "peach",
    "Blue": "blue",
    "Teal": "teal",
    "Green": "green",
    "Purple": "mauve",
    "Red": "red",
    "Yellow": "yellow",
}


def on_accent(hex_color):
    """Near-black or white, whichever contrasts more with the accent."""
    def lin(c):
        v = c / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    dark_lum = 0.0103  # relative luminance of #1a1a1a
    return "#1a1a1a" if (lum + 0.05) / (dark_lum + 0.05) >= 1.05 / (lum + 0.05) else "#ffffff"


def apply_theme(theme, accent):
    """Load a theme and accent into C, the palette every widget reads."""
    C.update(THEMES.get(theme, THEMES[DEFAULT_THEME]))
    C["accent"] = C[ACCENTS.get(accent, ACCENTS[DEFAULT_ACCENT])]
    C["on_accent"] = on_accent(C["accent"])


C = {}
apply_theme(DEFAULT_THEME, DEFAULT_ACCENT)

# Font constants — overridden by platform scripts before UI is built
FONT = "sans-serif"
MONO = "monospace"




# ─── Proxmox API Helpers ─────────────────────────────────────────────────────
def _get_ssl_context(skip_tls_verify=False):
    ctx = ssl.create_default_context()
    if skip_tls_verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def api_request(host, endpoint, method="GET", auth=None, data=None):
    if not host.startswith("https://"):
        return {"error": "Host must use https://"}
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
            req, data=data,
            context=_get_ssl_context(auth.get("skip_tls_verify", False) if auth else False),
            timeout=15,
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


def authenticate_password(host, username, password, skip_tls_verify=False):
    # Never send a password over plain HTTP (an imported or hand-edited config
    # can bypass the check in ClusterDialog).
    if not host.lower().startswith("https://"):
        return None
    url = f"{host}/api2/json/access/ticket"
    data = urllib.parse.urlencode(
        {"username": username, "password": password}
    ).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")

    try:
        with urllib.request.urlopen(
            req, context=_get_ssl_context(skip_tls_verify), timeout=15
        ) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            if res_data.get("data", {}).get("ticket"):
                return {
                    "ticket": res_data["data"]["ticket"],
                    "csrf": res_data["data"].get("CSRFPreventionToken", ""),
                }
    except Exception as e:
        import sys
        print(f"[debug] authenticate_password failed: {type(e).__name__}",
              file=sys.stderr)
    return None


# ─── Config Persistence ──────────────────────────────────────────────────────
def load_config(config_file):
    if config_file.exists():
        try:
            with open(config_file, encoding="utf-8") as f:
                data = json.load(f)
                if "version" not in data:
                    data["version"] = APP_VERSION
                return data
        except (json.JSONDecodeError, IOError) as e:
            import sys
            print(f"[warn] Config file corrupt or unreadable, starting fresh: {e}",
                  file=sys.stderr)
    return {"version": APP_VERSION, "clusters": [], "theme": "Catppuccin Mocha"}


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
    def __init__(self, parent, cluster=None, get_secret_fn=None):
        super().__init__(parent)
        self.result = None
        self._pending_secret = None
        self.original_name = cluster.get("name") if cluster else None
        self._get_secret_fn = get_secret_fn

        self.title("Edit Cluster" if cluster else "Add Cluster")
        self.geometry("500x510")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.configure(bg=C["base"])

        tk.Frame(self, bg=C["mauve"], height=3).pack(fill="x")

        main = tk.Frame(self, bg=C["base"], padx=24, pady=20)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)

        lbl = {"bg": C["base"], "fg": C["subtext0"], "font": (FONT, 9)}
        entry_cfg = {
            "bg": C["surface0"], "fg": C["text"], "insertbackground": C["text"],
            "relief": "flat", "font": (MONO, 10), "highlightthickness": 1,
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
        self.host_entry.grid(row=3, column=0, sticky="ew", pady=(0, 8), ipady=6)

        self.skip_tls_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            main, text="Skip TLS verification (self-signed certificate)",
            variable=self.skip_tls_var,
            bg=C["base"], fg=C["subtext0"], selectcolor=C["surface0"],
            activebackground=C["base"], activeforeground=C["text"],
            font=(FONT, 9),
        ).grid(row=4, column=0, sticky="w", pady=(0, 12))

        tk.Label(main, text="AUTHENTICATION", **lbl).grid(
            row=5, column=0, sticky="w", pady=(0, 4)
        )
        self.auth_var = tk.StringVar(value="token")
        auth_frame = tk.Frame(main, bg=C["base"])
        auth_frame.grid(row=6, column=0, sticky="w", pady=(0, 12))

        radio_cfg = {
            "bg": C["base"], "fg": C["text"], "selectcolor": C["surface0"],
            "activebackground": C["base"], "activeforeground": C["text"],
            "font": (FONT, 10), "command": self._toggle_auth,
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
        self.token_frame.grid(row=7, column=0, sticky="ew")
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
        btn_frame.grid(row=8, column=0, sticky="e", pady=(20, 0))

        HoverButton(
            btn_frame, text="Cancel", command=self.destroy,
            bg=C["surface1"], fg=C["text"], relief="flat", padx=18, pady=6,
            hover_bg=C["surface2"], font=(FONT, 10),
        ).pack(side="right", padx=(8, 0))
        HoverButton(
            btn_frame, text="  Save  ", command=self._save,
            bg=C["blue"], fg=C["crust"], relief="flat", padx=18, pady=6,
            hover_bg=C["sapphire"], hover_fg=C["crust"],
            font=(FONT, 10, "bold"),
        ).pack(side="right")

        if cluster:
            self.name_entry.insert(0, cluster.get("name", ""))
            self.host_entry.insert(0, cluster.get("host", ""))
            self.skip_tls_var.set(cluster.get("skip_tls_verify", False))
            self.auth_var.set(cluster.get("auth_method", "token"))
            self.token_id_entry.insert(0, cluster.get("token_id", ""))
            if self._get_secret_fn:
                secret = self._get_secret_fn(self.original_name)
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
            self.token_frame.grid(row=7, column=0, sticky="ew")
        else:
            self.token_frame.grid_forget()
            self.pass_frame.grid(row=7, column=0, sticky="ew")

    def _save(self):
        name = self.name_entry.get().strip()
        host = self.host_entry.get().strip().rstrip("/")
        if not name or not host:
            messagebox.showwarning(
                "Missing Fields", "Name and Host URL are required.",
                parent=self,
            )
            return
        parsed = urllib.parse.urlparse(host)
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            messagebox.showwarning(
                "Invalid Host URL",
                "The host URL must start with https://, for example\n"
                "https://pve.example.com:8006",
                parent=self,
            )
            return

        auth_method = self.auth_var.get()
        secret = self.token_secret_entry.get().strip()

        self._pending_secret = secret if (auth_method == "token" and secret) else None

        self.result = {
            "name": name, "host": host, "auth_method": auth_method,
            "token_id": self.token_id_entry.get().strip(),
            "username": self.user_entry.get().strip(),
            "skip_tls_verify": self.skip_tls_var.get(),
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
            "relief": "flat", "font": (MONO, 10), "highlightthickness": 1,
            "highlightcolor": C["blue"], "highlightbackground": C["surface1"],
        }

        tk.Label(
            main, text=f"Password for {username}", bg=C["base"], fg=C["text"],
            font=(FONT, 10),
        ).pack(anchor="w", pady=(0, 2))
        tk.Label(
            main, text=host, bg=C["base"], fg=C["overlay0"],
            font=(FONT, 9),
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
            font=(FONT, 10, "bold"),
        ).pack(side="right")

        self.pw_entry.focus_set()
        self.wait_window()

    def _submit(self):
        self.result = self.pw_entry.get()
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
            fg=C["text"], font=(FONT, 12, "bold"),
        ).pack(side="left")
        HoverButton(
            header, text="  ↻ Refresh  ", command=self._load_snapshots,
            bg=C["surface0"], fg=C["subtext0"], relief="flat", padx=10,
            pady=3, hover_bg=C["surface1"], hover_fg=C["text"],
            font=(FONT, 9),
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
            font=(FONT, 10), borderwidth=0,
        )
        style.configure(
            "Snap.Treeview.Heading", background=C["surface1"],
            foreground=C["subtext0"], font=(FONT, 9, "bold"),
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
            font=(FONT, 9), anchor="w",
        )
        self.status_label.pack(fill="x", pady=(0, 8))

        btn_frame = tk.Frame(main, bg=C["base"])
        btn_frame.pack(fill="x")

        HoverButton(
            btn_frame, text="  Close  ", command=self.destroy,
            bg=C["surface1"], fg=C["text"], relief="flat", padx=16, pady=6,
            hover_bg=C["surface2"], font=(FONT, 10),
        ).pack(side="right")
        HoverButton(
            btn_frame, text="  Rollback  ", command=self._rollback_snapshot,
            bg=C["peach"], fg=C["crust"], relief="flat", padx=16, pady=6,
            hover_bg=C["yellow"], hover_fg=C["crust"],
            font=(FONT, 10, "bold"),
        ).pack(side="right", padx=(0, 8))
        HoverButton(
            btn_frame, text="  Delete  ", command=self._delete_snapshot,
            bg=C["surface0"], fg=C["red"], relief="flat", padx=16, pady=6,
            hover_bg=C["surface1"], hover_fg=C["red"],
            font=(FONT, 10),
        ).pack(side="right", padx=(0, 8))
        HoverButton(
            btn_frame, text="  + Create  ", command=self._create_snapshot,
            bg=C["surface0"], fg=C["green"], relief="flat", padx=16, pady=6,
            hover_bg=C["surface1"], hover_fg=C["green"],
            font=(FONT, 10),
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
            f"/snapshot/{urllib.parse.quote(snap_name, safe='')}/rollback",
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
            "relief": "flat", "font": (MONO, 10), "highlightthickness": 1,
            "highlightcolor": C["blue"], "highlightbackground": C["surface1"],
        }
        lbl = {"bg": C["base"], "fg": C["subtext0"], "font": (FONT, 9)}

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
            font=(FONT, 10),
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
            hover_bg=C["surface2"], font=(FONT, 10),
        ).pack(side="right", padx=(8, 0))
        HoverButton(
            btn_frame, text="  Create  ", command=on_create,
            bg=C["green"], fg=C["crust"], relief="flat", padx=16, pady=5,
            hover_bg=C["teal"], hover_fg=C["crust"],
            font=(FONT, 10, "bold"),
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
            f"/snapshot?snapname={urllib.parse.quote(result['name'], safe='')}"
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
            f"/snapshot/{urllib.parse.quote(snap_name, safe='')}",
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


# ─── Base Application ────────────────────────────────────────────────────────
# ─── Main-window widgets ──────────────────────────────────────────────────────
def mix(c1, c2, t):
    """Blend two #rrggbb colours; t=0 gives c1, t=1 gives c2."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def round_rect(canvas, x1, y1, x2, y2, r, **kw):
    points = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
              x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(points, smooth=True, **kw)


def os_badge(ostype):
    if ostype.startswith("w"):
        return "WIN"
    return {"l24": "LNX", "l26": "LNX", "solaris": "SOL"}.get(ostype, "VM")


OS_LABELS = {
    "win11": "Windows 11", "win10": "Windows 10", "win8": "Windows 8",
    "win7": "Windows 7", "w2k8": "Windows Server 2008",
    "w2k3": "Windows Server 2003", "w2k": "Windows 2000",
    "wvista": "Windows Vista", "wxp": "Windows XP",
    "l24": "Linux", "l26": "Linux", "solaris": "Solaris", "other": "Other OS",
}


def os_label(ostype):
    return OS_LABELS.get(ostype, ostype or "Unknown OS")


# Sort keys, shared names with the Windows app's `vm_sort` config value
SORT_LABELS = {
    "name": "Name", "vmid": "ID", "ip": "Address", "node": "Node",
    "pool": "Pool", "snaps": "Snapshots", "status": "Status", "notes": "Notes",
}


def agent_has_agent(value):
    """True when a VM config's `agent` value ("1", "enabled=1,fstrim_cloned_disks=1") turns it on."""
    value = str(value or "")
    return value.startswith("1") or "enabled=1" in value.split(",")


def agent_ips(interfaces):
    """(adapter, address) pairs live on the guest's adapters, from network-get-interfaces.

    Loopback, link-local and unspecified addresses are left out. IPv4 comes first,
    each family in adapter order.
    """
    found = []
    for iface in interfaces or []:
        adapter = str(iface.get("name", ""))
        for addr in iface.get("ip-addresses") or []:
            try:
                ip = ipaddress.ip_address(str(addr.get("ip-address", "")).split("%")[0])
            except ValueError:
                continue
            if not (ip.is_loopback or ip.is_link_local or ip.is_unspecified):
                found.append((adapter, str(ip)))
    return sorted(found, key=lambda a: ":" in a[1])


def vm_ips(vm, ipv6):
    """The VM's addresses to show: IPv6 only when that setting is on."""
    return [(a, ip) for a, ip in vm.get("ips", []) if ipv6 or ":" not in ip]


def note_lines(text):
    """Proxmox notes as plain lines: no markdown heading or list markers, no blank lines."""
    lines = (line.strip().lstrip("#*->").strip() for line in (text or "").splitlines())
    return [line for line in lines if line]


def notes_cell(vm):
    """The list's Notes column: the first line of the Proxmox notes, else this app's note."""
    return next(iter(note_lines(vm.get("pve_note", ""))), "") or vm["note"]


def fit_addresses(ips, width, measure):
    """As many addresses as fit in `width` pixels, then "+N" for the rest."""
    full = ", ".join(ips)
    if len(ips) <= 1 or measure(full) <= width:
        return full
    for shown in range(len(ips) - 1, 0, -1):
        text = f"{', '.join(ips[:shown])} +{len(ips) - shown}"
        if measure(text) <= width:
            return text
    return f"{ips[0]} +{len(ips) - 1}"


def _ip_key(vm, ipv6):
    """Numeric order by first address, IPv4 before IPv6; no address ("no agent") after them."""
    ips = vm_ips(vm, ipv6)
    if ips:
        ip = ipaddress.ip_address(ips[0][1])
        return (0, ip.version, int(ip), "")
    return (1, 0, 0, vm.get("ip_note", ""))


def vm_sort_key(vm, column, ipv6=False):
    """The sort key for one column; blanks sort after values."""
    if column == "vmid":
        return vm["vmid"]
    if column == "snaps":
        return vm["snaps"]
    if column == "ip":
        return _ip_key(vm, ipv6)
    if column == "status":
        return (vm["status"] != "running", vm["status"])
    text = {"name": vm["name"], "node": vm["node"], "pool": vm["pool"],
            "notes": notes_cell(vm)}.get(column, "")
    return (text == "", text.casefold())


class KeyCap(tk.Label):
    """A key hint such as "F5"."""

    def __init__(self, master, text, bg, fg=None):
        fg = fg or C["overlay1"]
        super().__init__(
            master, text=text, bg=bg, fg=fg, font=(MONO, 8), padx=4, pady=0,
            highlightthickness=1, highlightbackground=mix(fg, bg, 0.5),
        )


class ActionButton(tk.Frame):
    """Flat button made of labels: icon, text and key hint, with hover and a
    disabled state. tk.Button can't hold a right-aligned key hint."""

    def __init__(self, master, text, command, icon="", key="", bg=None, fg=None,
                 hover_bg=None, border=None, bold=False, pady=6):
        bg = bg or C["surface0"]
        super().__init__(master, bg=bg, highlightthickness=1,
                         highlightbackground=border or C["surface1"], cursor="hand2")
        self._bg = bg
        self._hover_bg = hover_bg or C["surface1"]
        self._fg = fg or C["text"]
        self._command = command
        self._enabled = True
        font = (FONT, 10, "bold") if bold else (FONT, 10)
        inner = tk.Frame(self, bg=bg)
        inner.pack(fill="x", padx=10, pady=pady)
        self._parts = [self, inner]
        self._labels = []
        if key:
            cap = KeyCap(inner, key, bg, fg=None if fg is None else fg)
            cap.pack(side="right", padx=(8, 0))
            self._parts.append(cap)
        if icon:
            glyph = tk.Label(inner, text=icon, bg=bg, fg=self._fg, font=font, width=2, anchor="w")
            glyph.pack(side="left")
            self._parts.append(glyph)
            self._labels.append(glyph)
        self.label = tk.Label(inner, text=text, bg=bg, fg=self._fg, font=font, anchor="w")
        self.label.pack(side="left")
        self._parts.append(self.label)
        self._labels.append(self.label)
        for part in self._parts:
            part.bind("<Button-1>", self._click)
            part.bind("<Enter>", lambda e: self._paint(self._hover_bg))
            part.bind("<Leave>", lambda e: self._paint(self._bg))

    def _paint(self, color):
        if not self._enabled:
            color = self._bg
        for part in self._parts:
            part.config(bg=color)

    def _click(self, event=None):
        if self._enabled and self._command:
            self._command()
        return "break"

    def set_enabled(self, enabled):
        self._enabled = enabled
        fg = self._fg if enabled else mix(self._fg, self._bg, 0.6)
        for label in self._labels:
            label.config(fg=fg)
        self.config(cursor="hand2" if enabled else "arrow")

    def set_text(self, text):
        self.label.config(text=text)


class ProxmoxSpiceManagerBase(tk.Tk):
    """Base class with all shared UI and logic. Subclasses must implement
    the platform-specific methods listed below."""

    # ── Platform hooks (override in subclass) ────────────────────────────────
    def _platform_save_config(self, config):
        raise NotImplementedError

    def _platform_get_secret(self, cluster_name):
        raise NotImplementedError

    def _platform_save_secret(self, cluster_name, secret):
        raise NotImplementedError

    def _platform_delete_secret(self, cluster_name):
        raise NotImplementedError

    def _platform_launch_viewer(self, vv_path, vm):
        raise NotImplementedError

    def _platform_find_viewer(self):
        raise NotImplementedError

    def _platform_menu_entries(self):
        """Extra Settings menu entries: (label, action) tuples."""
        return []

    def _platform_set_vv_permissions(self, vv_path):
        pass

    def _platform_set_icon(self):
        pass

    def _get_config_file(self):
        raise NotImplementedError

    def _get_app_version(self):
        return APP_VERSION

    def _vm_note_key(self, vmid) -> str:
        if self.current_cluster:
            return f"{self.current_cluster.get('name', '')}:{vmid}"
        return str(vmid)

    def _lookup_vm_note(self, vmid) -> str:
        vm_notes = self.config_data.get("vm_notes", {})
        composite = self._vm_note_key(vmid)
        if composite in vm_notes:
            return vm_notes[composite]
        legacy = str(vmid)
        if legacy in vm_notes:
            return vm_notes[legacy]
        return ""

    # ── Init ─────────────────────────────────────────────────────────────────
    def __init__(self):
        super().__init__()
        version = self._get_app_version()
        self.title(f"Proxmox SPICE Manager v{version}")
        self.geometry("1280x760")
        self.minsize(1000, 600)
        self._platform_set_icon()

        self.config_data = load_config(self._get_config_file())
        self.current_cluster = None
        self.auth_cache = {}
        self._closing = False
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        if self.config_data.get("debug_logging", False):
            DebugLogger.set_enabled(True)

        apply_theme(self.config_data.get("theme", DEFAULT_THEME),
                    self.config_data.get("accent", DEFAULT_ACCENT))
        self.configure(bg=C["crust"])

        # Main-window state that outlives a rebuild (theme changes rebuild the UI)
        self._vms = []                 # dicts from the last refresh
        self._iid_to_vm = {}
        self._vm_filter = "all"
        self._group_by_node = self.config_data.get("group_by_node", True)
        self._sort_col = self.config_data.get("vm_sort", "vmid")
        if self._sort_col not in SORT_LABELS:
            self._sort_col = "vmid"
        self._sort_desc = self.config_data.get("vm_sort_desc", False)
        self._collapsed_nodes = set()
        self._show_ipv6 = bool(self.config_data.get("show_ipv6", False))
        self._row_font = tkfont.Font(font=(FONT, 10))
        self._heading_font = tkfont.Font(font=(FONT, 11, "bold"))  # node headings
        self._cluster_idx = -1
        self._cluster_status = {}      # name -> (online, vm count)
        self._loaded_cluster = None
        self._notes_vm = None
        self._popup = None
        self._popup_anchor = None
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_search_changed)
        self.notes_var = tk.StringVar()

        if not self.config_data.get("prereqs_ok"):
            self.update_idletasks()
            if not self._check_prereqs():
                self.destroy()
                return
            self.config_data["prereqs_ok"] = True
            self._save_config()

        self._platform_migrate_secrets()
        if self.config_data.get("clusters"):
            self._cluster_idx = 0
            self.current_cluster = self.config_data["clusters"][0]
        self._build_ui()
        self.bind("<Key>", self._on_key)
        self.bind_all("<ButtonPress>", self._on_global_click, add="+")

        if self.current_cluster:
            self.after(100, self._refresh_vms)

    def _save_config(self):
        self.config_data["version"] = self._get_app_version()
        self._platform_save_config(self.config_data)

    def _platform_migrate_secrets(self):
        pass

    # ── Prereqs ──────────────────────────────────────────────────────────────
    def _check_prereqs(self):
        raise NotImplementedError

    def _recheck_prereqs(self):
        raise NotImplementedError

    # ── UI Construction ──────────────────────────────────────────────────────
    def _on_close(self):
        self._closing = True
        self._commit_note()
        for child in self.winfo_children():
            if isinstance(child, tk.Toplevel):
                child.destroy()
        self.quit()
        self.destroy()

    # ── Debug Logging ───────────────────────────────────────────────────────
    def _toggle_ipv6(self):
        self._show_ipv6 = not self._show_ipv6
        self.config_data["show_ipv6"] = self._show_ipv6
        self._save_config()
        self._render_vms()

    def _toggle_debug_log(self):
        new_state = not DebugLogger.enabled
        DebugLogger.set_enabled(new_state)
        self.config_data["debug_logging"] = new_state
        self._save_config()
        self.status_label.config(
            text=f"Debug logging on — {DebugLogger.log_file_path()}" if new_state
            else "Debug logging off",
            fg=C["subtext0"],
        )

    def _open_debug_log(self):
        path = DebugLogger.log_file_path()
        if os.path.isfile(path):
            subprocess.Popen(["xdg-open", path])
        else:
            messagebox.showinfo(
                "No Log", "No debug log file exists yet.\n"
                "Enable debug logging first.",
                parent=self,
            )

    def _build_ui(self):
        self._close_popup()
        for widget in self.winfo_children():
            widget.destroy()
        self.configure(bg=C["crust"])

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
        style.configure(
            "Vertical.TScrollbar", background=C["surface1"], troughcolor=C["base"],
            arrowcolor=C["overlay0"], borderwidth=0, relief="flat",
        )
        style.map("Vertical.TScrollbar", background=[("active", C["surface2"])])
        style.configure(
            "Vm.Treeview", background=C["base"], fieldbackground=C["base"],
            foreground=C["text"], rowheight=30, font=(FONT, 10), borderwidth=0,
        )
        style.map(
            "Vm.Treeview",
            background=[("selected", C["surface1"])],
            foreground=[("selected", C["text"])],
        )
        style.configure(
            "Vm.Treeview.Heading", background=C["base"], foreground=C["subtext0"],
            font=(FONT, 9, "bold"), borderwidth=0, relief="flat", padding=(6, 4),
        )
        style.map("Vm.Treeview.Heading", background=[("active", C["surface0"])],
                  foreground=[("active", C["text"])])
        style.layout("Vm.Treeview", [("Vm.Treeview.treearea", {"sticky": "nswe"})])

        sidebar = tk.Frame(self, bg=C["crust"], width=232)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        card = tk.Frame(self, bg=C["base"], highlightthickness=1,
                        highlightbackground=C["surface0"])
        card.pack(side="left", fill="both", expand=True, padx=(0, 8), pady=8)
        inspector = tk.Frame(card, bg=C["mantle"], width=290)
        inspector.pack(side="right", fill="y")
        inspector.pack_propagate(False)
        tk.Frame(card, bg=C["surface0"], width=1).pack(side="right", fill="y")
        main = tk.Frame(card, bg=C["base"])
        main.pack(side="left", fill="both", expand=True, padx=(24, 16), pady=(20, 12))

        self._build_list(main)
        self._build_inspector(inspector)
        self._populate_clusters()
        self._render_vms()

    # ── Sidebar ──────────────────────────────────────────────────────────────
    def _build_sidebar(self, sidebar):
        brand = tk.Frame(sidebar, bg=C["crust"])
        brand.pack(fill="x", padx=20, pady=(18, 22))
        logo = tk.Canvas(brand, width=28, height=28, bg=C["crust"], highlightthickness=0)
        round_rect(logo, 0, 0, 28, 28, 7, fill=C["accent"], outline="")
        logo.create_rectangle(8, 8, 20, 16, outline=C["on_accent"], width=1.6)
        logo.create_line(11, 21, 17, 21, fill=C["on_accent"], width=1.6)
        logo.create_line(14, 16, 14, 21, fill=C["on_accent"], width=1.6)
        logo.pack(side="left")
        names = tk.Frame(brand, bg=C["crust"])
        names.pack(side="left", padx=(10, 0))
        tk.Label(names, text="SPICE Manager", bg=C["crust"], fg=C["text"],
                 font=(FONT, 11, "bold")).pack(anchor="w")
        version = self._get_app_version()
        tk.Label(names, text=f"for Proxmox VE · v{version}",
                 bg=C["crust"], fg=C["subtext0"], font=(FONT, 8)).pack(anchor="w")
        links = tk.Frame(names, bg=C["crust"])
        links.pack(anchor="w", pady=(2, 0))
        for i, (text, url) in enumerate((
                ("GitHub", REPO_URL),
                ("Release notes", f"{REPO_URL}/releases/tag/v{version}"))):
            if i:
                tk.Label(links, text=" · ", bg=C["crust"], fg=C["overlay1"],
                         font=(FONT, 8)).pack(side="left")
            link = tk.Label(links, text=text, bg=C["crust"], fg=C["accent"],
                            font=(FONT, 8), cursor="hand2")
            link.pack(side="left")
            link.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
            link.bind("<Enter>", lambda e: e.widget.config(font=(FONT, 8, "underline")))
            link.bind("<Leave>", lambda e: e.widget.config(font=(FONT, 8)))

        bottom = tk.Frame(sidebar, bg=C["crust"])
        bottom.pack(side="bottom", fill="x", padx=(12, 8), pady=(0, 10))
        tk.Frame(bottom, bg=C["surface1"], height=1).pack(fill="x", padx=8, pady=(0, 6))
        nav = {"bg": C["crust"], "border": C["crust"], "hover_bg": C["surface0"], "pady": 5}
        ActionButton(bottom, "Add cluster", self._add_cluster, icon="+", **nav).pack(fill="x")
        row = tk.Frame(bottom, bg=C["crust"])
        row.pack(fill="x")
        self._appearance_btn = self._build_appearance_button(row)
        self._appearance_btn.pack(side="right", padx=(4, 0))
        self._settings_btn = ActionButton(row, "Settings", self._open_settings, icon="⚙", **nav)
        self._settings_btn.pack(side="left", fill="x", expand=True)

        tk.Label(sidebar, text="Clusters", bg=C["crust"], fg=C["subtext0"],
                 font=(FONT, 9)).pack(anchor="w", padx=22, pady=(0, 6))
        self._cluster_frame = tk.Frame(sidebar, bg=C["crust"])
        self._cluster_frame.pack(fill="both", expand=True, padx=(12, 8))

    def _build_appearance_button(self, parent):
        """Quick switch: the current accent over the current theme, and a chevron."""
        bg = C["surface0"]
        canvas = tk.Canvas(parent, width=48, height=28, bg=bg, cursor="hand2",
                           highlightthickness=1, highlightbackground=C["surface1"])
        canvas.create_oval(9, 9, 19, 19, fill=C["accent"], outline="")
        canvas.create_oval(16, 9, 26, 19, fill=C["base"], outline=C["surface2"])
        canvas.create_line(31, 12, 35, 16, 39, 12, fill=C["subtext1"], width=1.4)
        canvas.bind("<Button-1>", lambda e: self._open_appearance())
        canvas.bind("<Enter>", lambda e: canvas.config(bg=C["surface1"]))
        canvas.bind("<Leave>", lambda e: canvas.config(bg=bg))
        return canvas

    # ── VM list ──────────────────────────────────────────────────────────────
    def _build_list(self, main):
        header = tk.Frame(main, bg=C["base"])
        header.pack(fill="x", pady=(0, 2))

        tools = tk.Frame(header, bg=C["base"])
        tools.pack(side="right", anchor="n", pady=(4, 0))
        search = tk.Frame(tools, bg=C["mantle"], highlightthickness=1,
                          highlightbackground=C["surface1"])
        search.pack(side="left", padx=(0, 8))
        tk.Label(search, text="⚲", bg=C["mantle"], fg=C["overlay1"],
                 font=(FONT, 11)).pack(side="left", padx=(8, 0))
        self._search_key = KeyCap(search, "/", C["mantle"])
        self._search_key.pack(side="right", padx=(0, 8))
        self.search_entry = tk.Entry(
            search, textvariable=self.search_var, bg=C["mantle"], fg=C["text"],
            insertbackground=C["text"], relief="flat", width=20, font=(FONT, 10),
            highlightthickness=0, bd=0,
        )
        self.search_entry.pack(side="left", padx=(6, 6), pady=6)
        self._search_hint = tk.Label(search, text="Search VMs", bg=C["mantle"],
                                     fg=C["overlay1"], font=(FONT, 10))
        self._search_hint.bind("<Button-1>", lambda e: self.search_entry.focus_set())
        self.search_entry.bind("<FocusIn>", lambda e: self._update_search_hint())
        self.search_entry.bind("<FocusOut>", lambda e: self._update_search_hint())
        self._update_search_hint()
        ActionButton(tools, "Refresh", self._refresh_vms, icon="⟳", key="F5",
                     pady=4).pack(side="left")

        titles = tk.Frame(header, bg=C["base"])
        titles.pack(side="left", fill="x", expand=True)
        self.cluster_title = tk.Label(
            titles, text=self.current_cluster["name"] if self.current_cluster else "No cluster",
            bg=C["base"], fg=C["text"], font=(FONT, 20, "bold"), anchor="w",
        )
        self.cluster_title.pack(fill="x")
        self.status_label = tk.Label(
            main, text="" if self.config_data.get("clusters") else "Add a cluster to get started",
            bg=C["base"], fg=C["subtext0"], font=(FONT, 10), anchor="w",
        )
        self.status_label.pack(fill="x", pady=(0, 14), after=header)

        chips = tk.Frame(main, bg=C["base"])
        chips.pack(fill="x", pady=(0, 8))
        self._chips = {}
        for key in ("all", "running", "stopped"):
            chip = tk.Label(chips, padx=12, pady=3, font=(FONT, 10), cursor="hand2",
                            highlightthickness=1)
            chip.pack(side="left", padx=(0, 6))
            chip.bind("<Button-1>", lambda e, k=key: self._set_vm_filter(k))
            self._chips[key] = chip
        self._group_chip = tk.Label(chips, padx=12, pady=3, font=(FONT, 10), cursor="hand2",
                                    highlightthickness=1)
        self._group_chip.pack(side="right")
        self._group_chip.bind("<Button-1>", lambda e: self._toggle_grouping())
        self._ipv6_chip = tk.Label(chips, text="IPv6", padx=12, pady=3, font=(FONT, 10),
                                   cursor="hand2", highlightthickness=1)
        self._ipv6_chip.pack(side="right", padx=(0, 6))
        self._ipv6_chip.bind("<Button-1>", lambda e: self._toggle_ipv6())

        table = tk.Frame(main, bg=C["base"])
        table.pack(fill="both", expand=True)
        columns = ("os", "name", "vmid", "ip", "node", "pool", "snaps", "status", "notes")
        tree = ttk.Treeview(table, columns=columns, show="headings",
                            selectmode="extended", style="Vm.Treeview")
        for col in columns:
            tree.column(col, width=self.FIXED_WIDTHS.get(col, 120), minwidth=40,
                        stretch=False, anchor="w")
            if col != "os":
                tree.heading(col, anchor="w", command=lambda c=col: self._sort_by(c))
        # Node headings: a shaded band, so they read as sections, not as VMs
        tree.tag_configure("group", foreground=C["accent"], background=C["surface1"],
                           font=(FONT, 11, "bold"))
        tree.tag_configure("running", foreground=C["text"])
        tree.tag_configure("stopped", foreground=C["overlay1"])
        scrollbar = ttk.Scrollbar(table, orient="vertical", command=tree.yview)

        def autohide(first, last):
            # Only show the scrollbar when the list doesn't fit
            if float(first) <= 0 and float(last) >= 1:
                scrollbar.pack_forget()
            elif not scrollbar.winfo_ismapped():
                scrollbar.pack(side="right", fill="y", before=tree)
            scrollbar.set(first, last)

        tree.configure(yscrollcommand=autohide)
        tree.pack(side="left", fill="both", expand=True)
        tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        tree.bind("<Button-1>", self._on_tree_click)
        tree.bind("<Configure>", lambda e: self._fit_columns())
        tree.bind("<Double-1>", self._on_vm_double_click)
        self.vm_tree = tree
        self._update_headings()
        self._empty_label = tk.Label(table, bg=C["base"], fg=C["overlay1"], font=(FONT, 10))

    def _update_search_hint(self):
        if not hasattr(self, "_search_hint"):
            return
        empty = not self.search_var.get()
        if empty and self.focus_get() is not self.search_entry:
            self._search_hint.place(in_=self.search_entry, x=0, rely=0.5, anchor="w")
        else:
            self._search_hint.place_forget()
        if empty:
            self._search_key.pack(side="right", padx=(0, 8))
        else:
            self._search_key.pack_forget()

    def _on_search_changed(self, *_):
        self._update_search_hint()
        if hasattr(self, "vm_tree"):
            self._render_vms()

    def _set_vm_filter(self, key):
        self._vm_filter = key
        self._render_vms()

    def _update_chips(self):
        running = sum(1 for vm in self._vms if vm["status"] == "running")
        counts = {"all": len(self._vms), "running": running,
                  "stopped": len(self._vms) - running}
        labels = {"all": "All", "running": "Running", "stopped": "Stopped"}
        for key, chip in self._chips.items():
            on = key == self._vm_filter
            chip.config(
                text=f"{labels[key]}  {counts[key]}",
                bg=C["accent"] if on else C["surface0"],
                fg=C["on_accent"] if on else C["text"],
                highlightbackground=C["accent"] if on else C["surface1"],
                font=(FONT, 10, "bold") if on else (FONT, 10),
            )
        for chip, label, on in ((self._group_chip, "Group by node", self._group_by_node),
                                (self._ipv6_chip, "IPv6", self._show_ipv6)):
            chip.config(
                text=f"✓ {label}" if on else label,
                bg=C["surface1"] if on else C["surface0"], fg=C["text"],
                highlightbackground=C["surface2"] if on else C["surface1"],
            )

    def _vm_matches(self, vm, query):
        running = vm["status"] == "running"
        if self._vm_filter == "running" and not running:
            return False
        if self._vm_filter == "stopped" and running:
            return False
        if not query:
            return True
        fields = (vm["name"], str(vm["vmid"]), vm["node"], vm["pool"], vm["note"],
                  vm.get("pve_note", ""), os_label(vm["ostype"]), *(ip for _, ip in vm_ips(vm, self._show_ipv6)))
        return any(query in f.lower() for f in fields)

    def _render_vms(self, keep=None):
        """Redraw the table from self._vms, grouped by node, keeping the selection."""
        tree = self.vm_tree
        if keep is None:
            keep = {vm["vmid"] for vm in self._get_selected_vms()}
        tree.delete(*tree.get_children())
        self._iid_to_vm = {}
        query = self.search_var.get().strip().lower()
        visible = sorted((vm for vm in self._vms if self._vm_matches(vm, query)),
                         key=lambda v: vm_sort_key(v, self._sort_col, self._show_ipv6), reverse=self._sort_desc)
        self._fit_columns()
        if self._group_by_node:
            for node in sorted({vm["node"] for vm in visible}):
                vms = [vm for vm in visible if vm["node"] == node]
                running = sum(1 for vm in vms if vm["status"] == "running")
                is_open = node not in self._collapsed_nodes
                group = f"node:{node}"
                tree.insert("", "end", iid=group, open=is_open, tags=("group",), values=(
                    "", self._node_heading(node, is_open, running, len(vms)),
                    "", "", "", "", "", "", ""))
                for vm in vms:
                    self._insert_vm(group, vm)
        else:
            for vm in visible:
                self._insert_vm("", vm)
        self._update_chips()

        if visible:
            self._empty_label.place_forget()
        else:
            if self._vms:
                text = "No VMs match the filter"
            elif self.current_cluster:
                text = "No SPICE VMs loaded"
            else:
                text = "Add a cluster to see its VMs"
            self._empty_label.config(text=text)
            self._empty_label.place(relx=0.5, rely=0.4, anchor="center")

        # A VM inside a folded node stays unselected: see() would unfold it again,
        # and keys shouldn't act on a VM that isn't on screen
        shown = self._shown_vm_iids()
        selection = [f"vm:{vmid}" for vmid in keep if f"vm:{vmid}" in shown]
        if not selection and shown:
            selection = shown[:1]
        if selection:
            tree.selection_set(selection)
            tree.focus(selection[0])
            tree.see(selection[0])
        self._update_inspector()

    def _insert_vm(self, parent, vm):
        iid = f"vm:{vm['vmid']}"
        is_running = vm["status"] == "running"
        status = "● Running" if is_running else f"○ {vm['status'].title() or 'Unknown'}"
        self.vm_tree.insert(parent, "end", iid=iid, tags=("running" if is_running else "stopped",),
                            values=(os_badge(vm["ostype"]), vm["name"], vm["vmid"],
                                    self._address_cell(vm), vm["node"], vm["pool"] or "—",
                                    vm["snaps"], status, notes_cell(vm)))
        self._iid_to_vm[iid] = vm

    def _show_addresses(self, vm):
        """Inspector: each adapter's name, dimmed, over its addresses."""
        frame = self._detail["ip"]
        for child in frame.winfo_children():
            child.destroy()
        bg = frame["bg"]
        by_adapter = {}
        for adapter, ip in vm_ips(vm, self._show_ipv6):
            by_adapter.setdefault(adapter or "Adapter", []).append(ip)
        if not by_adapter:
            tk.Label(frame, text=vm["ip_note"] or "—", bg=bg, fg=C["text"],
                     font=(FONT, 10)).pack(anchor="w")
        for i, (adapter, ips) in enumerate(by_adapter.items()):
            tk.Label(frame, text=adapter, bg=bg, fg=C["subtext0"],
                     font=(FONT, 9)).pack(anchor="w", pady=(6 if i else 0, 0))
            for ip in ips:
                tk.Label(frame, text=ip, bg=bg, fg=C["text"], font=(MONO, 9)).pack(anchor="w")

    def _address_cell(self, vm):
        """Every address that fits the column, "+N" for the rest, or why there is none."""
        ips = [ip for _, ip in vm_ips(vm, self._show_ipv6)]
        if not ips:
            return vm["ip_note"] or "—"
        width = int(self.vm_tree.column("ip", "width")) - self.CELL_PADDING
        return fit_addresses(ips, width, self._row_font.measure)

    # Name, address and notes share what the fixed columns leave; Tk won't size
    # them itself. The address width here is its minimum.
    FIXED_WIDTHS = {"os": 40, "vmid": 48, "ip": 118, "node": 70, "pool": 78,
                    "snaps": 72, "status": 88}
    # Dropped first when the list is too narrow, so status and notes stay on screen
    OPTIONAL_COLUMNS = ("pool", "snaps", "node", "vmid", "ip")
    MIN_NAME, MIN_NOTES = 106, 80
    CELL_PADDING = 12

    def _fit_columns(self):
        tree = self.vm_tree
        shown = [c for c in tree["columns"] if c != "node" or not self._group_by_node]
        width = tree.winfo_width() - 4
        min_name = self._min_name_width()
        for col in self.OPTIONAL_COLUMNS:
            fixed = sum(self.FIXED_WIDTHS.get(c, 0) for c in shown)
            if fixed + min_name + self.MIN_NOTES <= width:
                break
            if col in shown and col != self._sort_col:
                shown.remove(col)
        tree["displaycolumns"] = shown
        spare = width - sum(self.FIXED_WIDTHS.get(c, 0) for c in shown)
        if "ip" in shown:
            # A wider window shows more of each VM's addresses, up to all of them
            needed = max((self._row_font.measure(", ".join(ip for _, ip in vm_ips(vm, self._show_ipv6)))
                          for vm in self._vms), default=0) + self.CELL_PADDING
            free = spare - min_name - self.MIN_NOTES
            extra = max(0, min(needed - self.FIXED_WIDTHS["ip"], int(free * 0.5)))
            tree.column("ip", width=self.FIXED_WIDTHS["ip"] + extra)
            spare -= extra
        name = max(min_name, min(int(spare * 0.65), spare - self.MIN_NOTES))
        tree.column("name", width=name)
        tree.column("notes", width=max(self.MIN_NOTES, spare - name))
        for iid, vm in self._iid_to_vm.items():
            tree.set(iid, "ip", self._address_cell(vm))

    def _update_headings(self):
        for col, label in SORT_LABELS.items():
            # Every heading carries a sort mark so it reads as clickable
            text = "SNAPS" if col == "snaps" else label.upper()
            if col == self._sort_col:
                text += " ▼" if self._sort_desc else " ▲"
            else:
                text += " ↕"
            self.vm_tree.heading(col, text=text)

    def _sort_by(self, column):
        """Heading click: sort by that column; clicking it again reverses."""
        if column == self._sort_col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col, self._sort_desc = column, False
        self.config_data["vm_sort"] = self._sort_col
        self.config_data["vm_sort_desc"] = self._sort_desc
        self._save_config()
        self._update_headings()
        self._render_vms()

    def _toggle_grouping(self):
        self._group_by_node = not self._group_by_node
        self.config_data["group_by_node"] = self._group_by_node
        self._save_config()
        self._render_vms()

    def _on_tree_click(self, event):
        """A click on a node heading folds or unfolds it and leaves the selection alone."""
        iid = self.vm_tree.identify_row(event.y)
        if not iid.startswith("node:"):
            return None
        node = iid[len("node:"):]
        if node in self._collapsed_nodes:
            self._collapsed_nodes.discard(node)
        else:
            self._collapsed_nodes.add(node)
        self._render_vms()
        return "break"

    @staticmethod
    def _node_heading(node, is_open, running, total):
        return f"{'▾' if is_open else '▸'}  {node}  ·  {running}/{total} running"

    def _min_name_width(self):
        """Name column minimum; when grouped, wide enough for every node heading."""
        if not self._group_by_node:
            return self.MIN_NAME
        widest = max((self._heading_font.measure(self._node_heading(vm["node"], True, 99, 99))
                      for vm in self._vms), default=0)
        return max(self.MIN_NAME, widest + self.CELL_PADDING)

    def _shown_vm_iids(self):
        """VM rows on screen, in list order: not inside a folded node heading."""
        tree = self.vm_tree
        return [iid for iid in self._iid_to_vm
                if not tree.parent(iid) or tree.item(tree.parent(iid), "open")]

    def _focus_tree(self):
        tree = self.vm_tree
        shown = self._shown_vm_iids()
        if not tree.selection() and shown:
            tree.selection_set(shown[0])
            tree.focus(shown[0])
        tree.focus_set()

    def _select_all_vms(self):
        shown = self._shown_vm_iids()
        if shown:
            self.vm_tree.selection_set(shown)

    # ── Selection ────────────────────────────────────────────────────────────
    def _get_selected_vms(self):
        if not hasattr(self, "vm_tree"):
            return []
        return [self._iid_to_vm[iid] for iid in self.vm_tree.selection()
                if iid in self._iid_to_vm]

    def _get_selected_vm(self):
        vms = self._get_selected_vms()
        if len(vms) == 1:
            return vms[0]
        messagebox.showinfo(
            "Single Selection",
            "Select a VM first." if not vms else "Select a single VM.",
            parent=self,
        )
        return None

    def _on_tree_select(self, event=None):
        tree = self.vm_tree
        groups = [iid for iid in tree.selection() if iid not in self._iid_to_vm]
        if groups:
            # Node headings aren't VMs. Arrow keys can still land on one: step
            # onto its first VM instead of leaving nothing selected.
            tree.selection_remove(groups)
            if not tree.selection():
                target = self._vm_beside_heading(groups[0])
                if target:
                    tree.selection_set(target)
                    tree.focus(target)
            return
        selected = tree.selection()
        if selected:
            self._last_vm_iid = selected[-1]
        self._update_inspector()

    def _vm_beside_heading(self, heading):
        """The VM next to a node heading, in the direction the arrow keys came from."""
        order = list(self._iid_to_vm)  # display order
        children = [c for c in self.vm_tree.get_children(heading) if c in self._iid_to_vm] \
            if self.vm_tree.item(heading, "open") else []
        # The first VM shown after this heading, whatever group it's in
        after = children[0] if children else None
        if after is None:
            later = self.vm_tree.next(heading)
            while later and not after:
                kids = self.vm_tree.get_children(later) if self.vm_tree.item(later, "open") else ()
                after = kids[0] if kids else None
                later = self.vm_tree.next(later)
        last = getattr(self, "_last_vm_iid", None)
        if last in order and after in order and order.index(last) >= order.index(after):
            # Coming up from below: stop on the VM just above the heading
            idx = order.index(after) - 1
            return order[idx] if idx >= 0 else last
        return after or last

    def _on_vm_double_click(self, event):
        iid = self.vm_tree.identify_row(event.y)
        if iid not in self._iid_to_vm:
            return "break"  # a node heading; the single click already folded it
        self.vm_tree.selection_set(iid)
        self._launch_spice()
        return "break"

    # ── Inspector ────────────────────────────────────────────────────────────
    def _build_inspector(self, parent):
        bg = C["mantle"]
        self._insp_empty = tk.Label(
            parent, text="Select a VM to see its\ndetails and actions.",
            bg=bg, fg=C["overlay1"], font=(FONT, 10), justify="center",
        )
        insp = tk.Frame(parent, bg=bg)
        self._insp = insp
        body = tk.Frame(insp, bg=bg)
        body.pack(fill="both", expand=True, padx=20, pady=(22, 18))

        self._insp_caption = tk.Label(body, text="Selected", bg=bg, fg=C["subtext0"],
                                      font=(FONT, 9), anchor="w")
        self._insp_caption.pack(fill="x")
        self._insp_name = tk.Label(body, bg=bg, fg=C["text"], font=(FONT, 16, "bold"),
                                   anchor="w")
        self._insp_name.pack(fill="x", pady=(2, 0))
        sub = tk.Frame(body, bg=bg)
        sub.pack(fill="x")
        self._insp_os = tk.Label(sub, bg=bg, fg=C["subtext0"], font=(FONT, 10))
        self._insp_os.pack(side="left")
        tk.Label(sub, text=" · ", bg=bg, fg=C["subtext0"], font=(FONT, 10)).pack(side="left")
        self._insp_state = tk.Label(sub, bg=bg, fg=C["green"], font=(FONT, 10))
        self._insp_state.pack(side="left")

        self._console_btn = ActionButton(
            body, "Open SPICE console", self._launch_spice, key="Enter",
            bg=C["accent"], fg=C["on_accent"], border=C["accent"],
            hover_bg=mix(C["accent"], C["mantle"], 0.15), bold=True, pady=8,
        )
        self._console_btn.pack(fill="x", pady=(16, 0))

        details = tk.Frame(body, bg=bg)
        details.pack(fill="x", pady=(16, 0))
        self._details = details
        details.columnconfigure(1, weight=1)
        self._detail = {}
        for row, (key, label) in enumerate((("vmid", "VM ID"), ("ip", "Address"),
                                            ("node", "Node"), ("pool", "Pool"))):
            tk.Label(details, text=label, bg=bg, fg=C["subtext0"], font=(FONT, 10),
                     anchor="w").grid(row=row, column=0, sticky="nw", pady=(0, 6))
            if key == "ip":
                value = tk.Frame(details, bg=bg)  # filled per VM by _show_addresses
            else:
                value = tk.Label(details, bg=bg, fg=C["text"], anchor="w", font=(FONT, 10))
            value.grid(row=row, column=1, sticky="nw", padx=(12, 0), pady=(0, 6))
            self._detail[key] = value
        # The VM's own Notes from Proxmox, read-only; hidden when it has none
        self._pve_notes_label = tk.Label(details, text="Proxmox", bg=bg, fg=C["subtext0"],
                                         font=(FONT, 10), anchor="w")
        self._pve_notes_label.grid(row=4, column=0, sticky="nw", pady=(0, 6))
        self._pve_notes = tk.Label(details, bg=bg, fg=C["text"], font=(FONT, 10), anchor="w",
                                   justify="left", wraplength=170)
        self._pve_notes.grid(row=4, column=1, sticky="nw", padx=(12, 0), pady=(0, 8))
        tk.Label(details, text="Notes", bg=bg, fg=C["subtext0"], font=(FONT, 10),
                 anchor="w").grid(row=5, column=0, sticky="w")
        notes = tk.Frame(details, bg=C["base"], highlightthickness=1,
                         highlightbackground=C["surface1"])
        notes.grid(row=5, column=1, sticky="ew", padx=(12, 0))
        self._notes_menu_btn = tk.Label(notes, text="▾", bg=C["base"], fg=C["subtext1"],
                                        font=(FONT, 10), padx=6, cursor="hand2")
        self._notes_menu_btn.pack(side="right")
        self._notes_menu_btn.bind("<Button-1>", lambda e: self._open_notes_menu())
        self.notes_entry = tk.Entry(
            notes, textvariable=self.notes_var, bg=C["base"], fg=C["text"],
            insertbackground=C["text"], relief="flat", font=(FONT, 10),
            highlightthickness=0, bd=0, width=10,
        )
        self.notes_entry.pack(side="left", fill="x", expand=True, padx=(6, 0), pady=4)
        self.notes_entry.bind("<Return>", self._on_notes_return)
        self.notes_entry.bind("<Escape>", self._on_notes_escape)
        self.notes_entry.bind("<FocusOut>", lambda e: self._commit_note())

        tk.Label(body, text="Actions", bg=bg, fg=C["subtext0"], font=(FONT, 9),
                 anchor="w").pack(fill="x", pady=(20, 6))
        self._action_btns = {}
        for key, icon, text, hint, command in (
            ("start", "▶", "Start", "S", self._start_vm),
            ("shutdown", "↓", "Shut down", "Shift+S", self._shutdown_vm),
            ("reboot", "↻", "Reboot", "R", self._reboot_vm),
            ("snapshots", "◉", "Snapshots", "P", self._show_snapshots),
            ("rollback", "↺", "Roll back to latest snapshot", "", self._quick_rollback),
        ):
            btn = ActionButton(body, text, command, icon=icon, key=hint, pady=5)
            btn.pack(fill="x", pady=(0, 5))
            self._action_btns[key] = btn

        ActionButton(
            body, "Force stop", self._stop_vm, icon="■", key="Ctrl+.", fg=C["red"], pady=5,
        ).pack(side="bottom", fill="x")

    def _update_inspector(self):
        # Save an edit in progress to the VM it was typed for, before the panel moves on
        self._commit_note()
        if not hasattr(self, "_insp"):
            return
        vms = self._get_selected_vms()
        if not vms:
            self._notes_vm = None
            self._insp.pack_forget()
            self._insp_empty.place(relx=0.5, rely=0.45, anchor="center")
            return
        self._insp_empty.place_forget()
        self._insp.pack(fill="both", expand=True)

        running = sum(1 for vm in vms if vm["status"] == "running")
        single = vms[0] if len(vms) == 1 else None
        self._console_btn.set_enabled(running > 0)
        self._action_btns["snapshots"].set_enabled(single is not None)
        self._action_btns["rollback"].set_enabled(single is not None and single["snaps"] > 0)

        if single:
            self._insp_caption.config(text="Selected")
            self._insp_name.config(text=single["name"])
            self._insp_os.config(text=os_label(single["ostype"]))
            is_running = single["status"] == "running"
            self._insp_state.config(text=single["status"].title() or "Unknown",
                                    fg=C["green"] if is_running else C["overlay1"])
            self._console_btn.set_text("Open SPICE console")
            self._detail["vmid"].config(text=single["vmid"])
            self._show_addresses(single)
            pve_note = "\n".join(note_lines(single.get("pve_note", ""))[:4])
            self._pve_notes.config(text=pve_note)
            for widget in (self._pve_notes_label, self._pve_notes):
                if pve_note:
                    widget.grid()
                else:
                    widget.grid_remove()
            self._detail["node"].config(text=single["node"])
            self._detail["pool"].config(text=single["pool"] or "—")
            self._details.pack(fill="x", pady=(16, 0), after=self._console_btn)
            self.notes_var.set(single["note"])
            self._notes_vm = single
        else:
            self._insp_caption.config(text="Selection")
            self._insp_name.config(text=f"{len(vms)} VMs")
            self._insp_os.config(text=f"{running} running")
            self._insp_state.config(text=f"{len(vms) - running} stopped", fg=C["subtext0"])
            self._console_btn.set_text("Open 1 console" if running == 1
                                       else f"Open {running} consoles")
            self._details.pack_forget()
            self._notes_vm = None

    # ── Notes ────────────────────────────────────────────────────────────────
    def _commit_note(self):
        vm = getattr(self, "_notes_vm", None)
        if vm is None:
            return
        val = self.notes_var.get().strip()
        if val == vm["note"]:
            return
        vm["note"] = val
        if val and val not in self.config_data.get("note_options", []):
            self.config_data.setdefault("note_options", []).append(val)
        vm_notes = self.config_data.setdefault("vm_notes", {})
        key = self._vm_note_key(vm["vmid"])
        vm_notes.pop(str(vm["vmid"]), None)
        if val:
            vm_notes[key] = val
        else:
            vm_notes.pop(key, None)
        self._save_config()
        iid = f"vm:{vm['vmid']}"
        if hasattr(self, "vm_tree") and self.vm_tree.exists(iid):
            self.vm_tree.set(iid, "notes", notes_cell(vm))

    def _on_notes_return(self, event=None):
        self._commit_note()
        self._focus_tree()
        return "break"

    def _on_notes_escape(self, event=None):
        if self._notes_vm is not None:
            self.notes_var.set(self._notes_vm["note"])
        self._focus_tree()
        return "break"

    def _set_note(self, text):
        self.notes_var.set(text)
        self._commit_note()

    def _open_notes_menu(self):
        if self._notes_vm is None:
            return
        entries = [(opt, lambda o=opt: self._set_note(o))
                   for opt in self.config_data.get("note_options", [])]
        if entries:
            entries.append(None)
        entries.append(("Clear note", lambda: self._set_note(""), bool(self.notes_var.get())))
        entries.append(("Edit saved notes…", self._manage_note_options))
        self._show_menu(self._notes_menu_btn, entries, above=False)

    # ── Popups: menus and the appearance flyout ──────────────────────────────
    def _close_popup(self, event=None):
        popup = getattr(self, "_popup", None)
        if popup is not None and popup.winfo_exists():
            popup.destroy()
        self._popup = None
        self._popup_anchor = None

    def _on_global_click(self, event):
        popup = self._popup
        if popup is None:
            return
        widget = str(event.widget)
        inside = widget.startswith(str(popup))
        on_anchor = self._popup_anchor is not None and widget.startswith(str(self._popup_anchor))
        if not inside and not on_anchor:
            self._close_popup()

    def _open_popup(self, anchor, build, above=True, x=None):
        """Show a borderless popup next to anchor; clicking the anchor again closes it."""
        if self._popup is not None and self._popup_anchor is anchor:
            self._close_popup()
            return
        self._close_popup()
        popup = tk.Toplevel(self)
        popup.wm_overrideredirect(True)
        popup.configure(bg=C["mantle"], highlightthickness=1,
                        highlightbackground=C["surface1"])
        build(popup)
        popup.update_idletasks()
        if x is None:
            x = anchor.winfo_rootx()
        if above:
            y = anchor.winfo_rooty() - popup.winfo_reqheight() - 6
        else:
            y = anchor.winfo_rooty() + anchor.winfo_height() + 4
        popup.geometry(f"+{x}+{max(y, 0)}")
        popup.lift()
        popup.bind("<Escape>", self._close_popup)
        popup.focus_set()
        self._popup = popup
        self._popup_anchor = anchor

    def _show_menu(self, anchor, entries, above=True):
        """entries: (label, action[, enabled]) tuples; None draws a separator."""
        def build(popup):
            frame = tk.Frame(popup, bg=C["mantle"])
            frame.pack(padx=6, pady=6)
            tk.Frame(frame, bg=C["mantle"], width=220, height=0).pack()
            for entry in entries:
                if entry is None:
                    tk.Frame(frame, bg=C["surface1"], height=1).pack(fill="x", padx=4, pady=5)
                    continue
                label, action = entry[0], entry[1]
                enabled = entry[2] if len(entry) > 2 else True
                row = tk.Label(frame, text=label, bg=C["mantle"], anchor="w",
                               fg=C["text"] if enabled else C["overlay0"],
                               font=(FONT, 10), padx=10, pady=5,
                               cursor="hand2" if enabled else "arrow")
                row.pack(fill="x")
                if enabled:
                    row.bind("<Enter>", lambda e, r=row: r.config(bg=C["surface0"]))
                    row.bind("<Leave>", lambda e, r=row: r.config(bg=C["mantle"]))
                    row.bind("<Button-1>", lambda e, a=action: (self._close_popup(), a()))
        self._open_popup(anchor, build, above=above)

    def _open_settings(self):
        result = self._get_selected_cluster()
        name = result[1]["name"] if result else "cluster"
        entries = [
            (f"Edit {name}…", self._edit_cluster, result is not None),
            (f"Remove {name}…", self._remove_cluster, result is not None),
            None,
            ("Import clusters…", self._import_config),
            ("Export clusters…", self._export_config),
            None,
            ("Debug log: on" if DebugLogger.enabled else "Debug log: off",
             self._toggle_debug_log),
            ("Open debug log", self._open_debug_log, DebugLogger.enabled),
            ("Check prerequisites", self._recheck_prereqs),
        ]
        entries += self._platform_menu_entries()
        self._show_menu(self._settings_btn, entries)

    def _open_appearance(self):
        theme = self.config_data.get("theme", DEFAULT_THEME)
        accent = self.config_data.get("accent", DEFAULT_ACCENT)

        def build(popup):
            bg = C["mantle"]
            body = tk.Frame(popup, bg=bg)
            body.pack(padx=14, pady=12)
            tk.Frame(body, bg=bg, width=290, height=0).pack()
            tk.Label(body, text="Appearance", bg=bg, fg=C["text"],
                     font=(FONT, 11, "bold"), anchor="w").pack(fill="x")
            tk.Label(body, text="Theme", bg=bg, fg=C["subtext0"], font=(FONT, 9),
                     anchor="w").pack(fill="x", pady=(10, 4))
            for name, pal in THEMES.items():
                selected = name == theme
                row_bg = C["surface0"] if selected else bg
                row = tk.Frame(body, bg=row_bg, cursor="hand2")
                row.pack(fill="x", pady=1)
                # Miniature of the theme: page, card, a line of text, the accent
                mini = tk.Canvas(row, width=46, height=28, bg=row_bg, highlightthickness=0)
                mini.create_rectangle(0, 0, 45, 27, fill=pal["crust"], outline=pal["surface1"])
                mini.create_rectangle(12, 4, 41, 22, fill=pal["base"], outline="")
                mini.create_rectangle(15, 8, 31, 10, fill=pal["subtext0"], outline="")
                mini.create_rectangle(15, 14, 25, 17, fill=pal[ACCENTS[accent]], outline="")
                mini.create_rectangle(3, 5, 9, 6, fill=pal["surface1"], outline="")
                mini.create_rectangle(3, 9, 9, 10, fill=pal["surface1"], outline="")
                mini.pack(side="left", padx=6, pady=4)
                parts = [row, mini, tk.Label(row, text=name, bg=row_bg, fg=C["text"],
                                             font=(FONT, 10))]
                parts[-1].pack(side="left", padx=(4, 0))
                if selected:
                    parts.append(tk.Label(row, text="✓", bg=row_bg, fg=C["accent"],
                                          font=(FONT, 11, "bold")))
                    parts[-1].pack(side="right", padx=8)
                for part in parts:
                    part.bind("<Button-1>", lambda e, n=name: self._apply_appearance(theme=n))
                    if not selected:
                        part.bind("<Enter>", lambda e, ps=parts: [p.config(bg=C["surface0"]) for p in ps])
                        part.bind("<Leave>", lambda e, ps=parts: [p.config(bg=bg) for p in ps])

            head = tk.Frame(body, bg=bg)
            head.pack(fill="x", pady=(12, 6))
            tk.Label(head, text="Accent", bg=bg, fg=C["subtext0"], font=(FONT, 9)).pack(side="left")
            tk.Label(head, text=f"{accent} (default)" if accent == DEFAULT_ACCENT else accent,
                     bg=bg, fg=C["subtext0"], font=(FONT, 9)).pack(side="right")
            swatches = tk.Frame(body, bg=bg)
            swatches.pack(fill="x")
            for name, slot in ACCENTS.items():
                swatch = tk.Canvas(swatches, width=34, height=34, bg=bg,
                                   highlightthickness=0, cursor="hand2")
                if name == accent:
                    swatch.create_oval(2, 2, 32, 32, outline=C["text"], width=2)
                swatch.create_oval(6, 6, 28, 28, fill=C[slot], outline="")
                swatch.pack(side="left", padx=(0, 4))
                swatch.bind("<Button-1>", lambda e, n=name: self._apply_appearance(accent=n))

        # Line the flyout up with the sidebar rather than with the small button
        self._open_popup(self._appearance_btn, build, above=True, x=self.winfo_rootx() + 12)

    def _apply_appearance(self, theme=None, accent=None):
        theme = theme or self.config_data.get("theme", DEFAULT_THEME)
        accent = accent or self.config_data.get("accent", DEFAULT_ACCENT)
        self.config_data["theme"] = theme
        self.config_data["accent"] = accent
        self._save_config()
        apply_theme(theme, accent)
        keep = {vm["vmid"] for vm in self._get_selected_vms()}
        self._build_ui()
        self._render_vms(keep)
        if self._loaded_cluster:
            self._show_summary()
        # Keep the flyout open so themes and accents can be compared
        self.after(50, self._open_appearance)

    # ── Keyboard ─────────────────────────────────────────────────────────────
    def _on_key(self, event):
        focus = self.focus_get()
        key = event.keysym
        ctrl = bool(event.state & 0x4)
        if key == "F5":
            self._refresh_vms()
            return "break"
        if isinstance(focus, (tk.Entry, ttk.Entry, tk.Text)):
            if focus is getattr(self, "search_entry", None) and key in (
                    "Escape", "Return", "KP_Enter", "Down"):
                if key == "Escape":
                    self.search_var.set("")
                self._focus_tree()
                return "break"
            return None
        if self._popup is not None:
            if key == "Escape":
                self._close_popup()
                return "break"
            return None
        actions = {
            "slash": lambda: self.search_entry.focus_set(),
            "Return": self._launch_spice,
            "KP_Enter": self._launch_spice,
            "s": self._start_vm,
            "S": self._shutdown_vm,
            "r": self._reboot_vm,
            "p": self._show_snapshots,
        }
        if ctrl:
            if key == "period":
                self._stop_vm()
                return "break"
            if key in ("a", "A"):
                self._select_all_vms()
                return "break"
            return None
        action = actions.get(key)
        if action is None:
            return None
        action()
        return "break"

    # ── Clusters ─────────────────────────────────────────────────────────────
    def _populate_clusters(self):
        if not hasattr(self, "_cluster_frame"):
            return
        for widget in self._cluster_frame.winfo_children():
            widget.destroy()
        for idx, cluster in enumerate(self.config_data.get("clusters", [])):
            selected = idx == self._cluster_idx
            bg = C["surface0"] if selected else C["crust"]
            row = tk.Frame(self._cluster_frame, bg=bg, cursor="hand2")
            row.pack(fill="x", pady=1)
            tk.Frame(row, bg=C["accent"] if selected else bg, width=3).pack(
                side="left", fill="y", pady=8)
            online = self._cluster_status.get(cluster["name"])
            if online is None:
                dot_color, count = C["surface2"], ""
            elif online[0]:
                dot_color, count = C["green"], str(online[1])
            else:
                dot_color, count = C["overlay0"], "offline"
            dot = tk.Canvas(row, width=8, height=8, bg=bg, highlightthickness=0)
            dot.create_oval(0, 0, 7, 7, fill=dot_color, outline="")
            dot.pack(side="left", padx=(8, 10))
            count_label = tk.Label(row, text=count, bg=bg, fg=C["subtext0"], font=(FONT, 9))
            count_label.pack(side="right", padx=10)
            name = tk.Label(row, text=cluster["name"], bg=bg, fg=C["text"],
                            font=(FONT, 10), anchor="w")
            name.pack(side="left", fill="x", expand=True, pady=8)
            parts = (row, dot, count_label, name)
            for part in parts:
                part.bind("<Button-1>", lambda e, i=idx: self._select_cluster(i))
                part.bind("<Double-Button-1>", lambda e: self._edit_cluster())
                if not selected:
                    part.bind("<Enter>", lambda e, ps=parts: [p.config(bg=C["mantle"]) for p in ps])
                    part.bind("<Leave>", lambda e, ps=parts: [p.config(bg=C["crust"]) for p in ps])

    def _get_selected_cluster(self):
        clusters = self.config_data.get("clusters", [])
        if 0 <= self._cluster_idx < len(clusters):
            return self._cluster_idx, clusters[self._cluster_idx]
        return None

    def _select_cluster(self, idx):
        clusters = self.config_data.get("clusters", [])
        if not 0 <= idx < len(clusters):
            return
        if idx == self._cluster_idx and clusters[idx] is self.current_cluster \
                and self._loaded_cluster == clusters[idx]["name"]:
            # Already showing it. Rebuilding the rows here would also swallow
            # the second click of a double-click (edit); F5 refreshes.
            return
        self._cluster_idx = idx
        self.current_cluster = clusters[idx]
        self._populate_clusters()
        self._refresh_vms()

    def _add_cluster(self):
        dlg = ClusterDialog(self, get_secret_fn=self._platform_get_secret)
        if dlg.result:
            self.config_data.setdefault("clusters", []).append(dlg.result)
            self._save_config()
            if dlg._pending_secret:
                self._platform_save_secret(dlg.result["name"], dlg._pending_secret)
            self._select_cluster(len(self.config_data["clusters"]) - 1)

    def _edit_cluster(self):
        result = self._get_selected_cluster()
        if not result:
            messagebox.showinfo("No Selection", "Select a cluster to edit.", parent=self)
            return
        idx, cluster = result
        dlg = ClusterDialog(self, cluster, get_secret_fn=self._platform_get_secret)
        if dlg.result:
            if cluster.get("name") != dlg.result["name"]:
                self._platform_delete_secret(cluster["name"])
            self.auth_cache.pop(cluster["name"], None)
            self._cluster_status.pop(cluster["name"], None)
            self.config_data["clusters"][idx] = dlg.result
            self._save_config()
            if dlg._pending_secret:
                self._platform_save_secret(dlg.result["name"], dlg._pending_secret)
            self._select_cluster(idx)

    def _remove_cluster(self):
        result = self._get_selected_cluster()
        if not result:
            return
        idx, cluster = result
        if messagebox.askyesno("Confirm", f"Remove cluster '{cluster['name']}'?", parent=self):
            self._platform_delete_secret(cluster["name"])
            self.auth_cache.pop(cluster["name"], None)
            self._cluster_status.pop(cluster["name"], None)
            self.config_data["clusters"].pop(idx)
            self._save_config()
            self._vms = []
            self._loaded_cluster = None
            remaining = len(self.config_data["clusters"])
            if remaining:
                self._select_cluster(min(idx, remaining - 1))
            else:
                self._cluster_idx = -1
                self.current_cluster = None
                self.cluster_title.config(text="No cluster")
                self.status_label.config(text="Add a cluster to get started", fg=C["subtext0"])
                self._populate_clusters()
                self._render_vms()

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
        export_data["version"] = self._get_app_version()
        for cluster in export_data.get("clusters", []):
            if cluster.get("auth_method") == "token":
                secret = self._platform_get_secret(cluster["name"])
                if secret:
                    cluster["token_secret"] = secret
            cluster.pop("token_secret_enc", None)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2)
            self._platform_set_file_permissions(path)
            messagebox.showinfo(
                "Exported",
                f"Saved to:\n{path}\n\n"
                "This file contains plaintext secrets.\n"
                "Delete it after importing on another machine.",
                parent=self,
            )
        except Exception as e:
            messagebox.showerror("Export Failed", str(e), parent=self)

    def _platform_set_file_permissions(self, path):
        pass

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

        imported_version = imported.get("version", "Legacy")
        if imported_version != self._get_app_version():
            if not messagebox.askyesno(
                "Version Mismatch",
                f"File version: {imported_version}\n"
                f"App version: {self._get_app_version()}\n\n"
                "The file was created with a different version.\n"
                "Import anyway?",
                parent=self,
            ):
                return

        new_clusters = imported.get("clusters", [])
        if not new_clusters:
            messagebox.showinfo("Empty", "No clusters in file.", parent=self)
            return

        existing = [c["name"] for c in self.config_data.get("clusters", [])]
        for cluster in new_clusters:
            secret = cluster.pop("token_secret", None)
            cluster.pop("token_secret_enc", None)
            if cluster["name"] in existing:
                cluster["name"] = f"{cluster['name']} (Imported)"
            self.config_data.setdefault("clusters", []).append(cluster)
            if secret:
                self._platform_save_secret(cluster["name"], secret)

        self._save_config()
        self._populate_clusters()
        messagebox.showinfo("Imported", f"Imported {len(new_clusters)} cluster(s).", parent=self)

    # ── Auth ─────────────────────────────────────────────────────────────────
    def _get_auth(self, cluster):
        name = cluster["name"]
        skip_tls = cluster.get("skip_tls_verify", False)

        if cluster["auth_method"] == "token":
            token_id = cluster.get("token_id")
            token_secret = self._platform_get_secret(name)
            if token_id and token_secret:
                return {"token_id": token_id, "token_secret": token_secret,
                        "skip_tls_verify": skip_tls}
            messagebox.showerror(
                "Auth Error",
                "Token secret not found or could not be decrypted.",
                parent=self,
            )
            return None

        if name in self.auth_cache:
            return self.auth_cache[name]

        prompt = PasswordPrompt(
            self, cluster.get("username", "root@pam"), cluster["host"]
        )
        if not prompt.result:
            return None

        auth = authenticate_password(
            cluster["host"], cluster.get("username", "root@pam"), prompt.result,
            skip_tls_verify=skip_tls,
        )
        if auth:
            auth["skip_tls_verify"] = skip_tls
            self.auth_cache[name] = auth
            return auth

        messagebox.showerror("Auth Failed", "Could not authenticate.", parent=self)
        return None

    # ── VM Refresh ───────────────────────────────────────────────────────────
    def _show_summary(self):
        """Subtitle under the cluster name: VM and node counts, host, TLS state."""
        cluster = self.current_cluster
        if not cluster:
            return
        nodes = len({vm["node"] for vm in self._vms})
        parts = [
            "1 SPICE VM" if len(self._vms) == 1 else f"{len(self._vms)} SPICE VMs",
            "1 node" if nodes == 1 else f"{nodes} nodes",
        ]
        host = urllib.parse.urlparse(cluster.get("host", "")).hostname
        if host:
            parts.append(host)
        tls_off = cluster.get("skip_tls_verify", False)
        if tls_off:
            parts.append("⚠ TLS verification off")
        self.status_label.config(text=" · ".join(parts),
                                 fg=C["yellow"] if tls_off else C["subtext0"])

    def _set_cluster_offline(self, cluster, message):
        self._cluster_status[cluster["name"]] = (False, None)
        self._populate_clusters()
        self.status_label.config(text=message, fg=C["red"])

    def _refresh_vms(self):
        if not self.current_cluster:
            return
        cluster = self.current_cluster
        self.cluster_title.config(text=cluster["name"])
        if self._loaded_cluster != cluster["name"]:
            # Don't leave another cluster's VMs on screen under this cluster's name
            self._vms = []
            self._loaded_cluster = None
            self._render_vms()
        DebugLogger.log(f"[Refresh] Starting refresh for {cluster.get('name', '?')}")
        auth = self._get_auth(cluster)
        if not auth:
            DebugLogger.log("[Refresh] Auth failed — aborting refresh")
            self._set_cluster_offline(cluster, "Auth failed")
            return
        self.status_label.config(text=f"Loading VMs from {cluster['name']}...", fg=C["yellow"])
        self.update_idletasks()

        def fetch():
            data = api_request(
                cluster["host"],
                "/api2/json/cluster/resources?type=vm", auth=auth,
            )
            if "error" in data:
                self.after(0, lambda d=data: self._set_cluster_offline(
                    cluster, f"Error: {d['error']}"))
                return

            all_vms = data.get("data", [])
            if not all_vms:
                self.after(0, lambda: update_ui([], 0))
                return

            qemu_vms = [v for v in all_vms if v.get("type") == "qemu"]

            spice_vms = []
            for vm in qemu_vms:
                config = api_request(
                    cluster["host"],
                    f"/api2/json/nodes/{vm.get('node')}"
                    f"/qemu/{vm.get('vmid')}/config",
                    auth=auth,
                )
                if "error" in config:
                    continue
                vm["_ostype"] = str(config.get("data", {}).get("ostype", ""))
                vm["_has_agent"] = agent_has_agent(config.get("data", {}).get("agent"))
                vm["_description"] = str(config.get("data", {}).get("description", ""))
                vga = str(config.get("data", {}).get("vga", "")).lower()
                if "qxl" in vga or "spice" in vga:
                    snap_data = api_request(
                        cluster["host"],
                        f"/api2/json/nodes/{vm.get('node')}"
                        f"/qemu/{vm.get('vmid')}/snapshot",
                        auth=auth,
                    )
                    snaps = (
                        snap_data.get("data", [])
                        if "error" not in snap_data else []
                    )
                    vm["_snap_count"] = len(
                        [s for s in snaps if s.get("name") != "current"]
                    )
                    vm["_ips"], vm["_ip_note"] = [], "" if vm["_has_agent"] else "no agent"
                    if vm.get("status") == "running" and vm["_has_agent"]:
                        agent_data = api_request(
                            cluster["host"],
                            f"/api2/json/nodes/{vm.get('node')}"
                            f"/qemu/{vm.get('vmid')}/agent/network-get-interfaces",
                            auth=auth,
                        )
                        if "error" in agent_data:
                            vm["_ip_note"] = "agent error"
                        else:
                            vm["_ips"] = agent_ips(agent_data.get("data", {}).get("result"))
                    spice_vms.append(vm)

            self.after(0, lambda: update_ui(spice_vms, len(qemu_vms)))

        def update_ui(spice_vms, qemu_count):
            if self.current_cluster is not cluster or self._closing:
                return  # the user moved on to another cluster meanwhile
            keep = {vm["vmid"] for vm in self._get_selected_vms()}
            self._vms = [{
                "vmid": int(vm.get("vmid", 0)),
                "name": vm.get("name", "unnamed"),
                "node": vm.get("node", "?"),
                "pool": vm.get("pool", ""),
                "snaps": vm.get("_snap_count", 0),
                "status": vm.get("status", ""),
                "ips": vm.get("_ips", []),
                "ip_note": vm.get("_ip_note", ""),
                "pve_note": vm.get("_description", ""),
                "ostype": vm.get("_ostype", ""),
                "note": self._lookup_vm_note(vm.get("vmid", "")),
            } for vm in spice_vms]
            self._loaded_cluster = cluster["name"]
            self._cluster_status[cluster["name"]] = (True, len(self._vms))
            self._populate_clusters()
            self._render_vms(keep)
            DebugLogger.log(f"[Refresh] {len(spice_vms)} SPICE VMs found "
                            f"(of {qemu_count} QEMU VMs)")
            self._show_summary()

        threading.Thread(target=fetch, daemon=True).start()

    def _manage_note_options(self):
        dlg = tk.Toplevel(self)
        dlg.title("Manage Note Options")
        dlg.geometry("300x350")
        dlg.configure(bg=C["base"])
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(
            dlg, text="Note Options", bg=C["base"], fg=C["text"],
            font=(FONT, 12, "bold"),
        ).pack(pady=(12, 8))

        list_frame = tk.Frame(dlg, bg=C["base"])
        list_frame.pack(fill="both", expand=True, padx=16)

        listbox = tk.Listbox(
            list_frame, bg=C["surface0"], fg=C["text"],
            selectbackground=C["surface2"], selectforeground=C["text"],
            font=(FONT, 10), relief="flat", borderwidth=0,
        )
        listbox.pack(fill="both", expand=True)

        for opt in self.config_data.get("note_options", []):
            listbox.insert("end", opt)

        btn_frame = tk.Frame(dlg, bg=C["base"])
        btn_frame.pack(fill="x", padx=16, pady=(8, 4))

        add_var = tk.StringVar()
        add_entry = tk.Entry(
            btn_frame, textvariable=add_var, bg=C["surface0"],
            fg=C["text"], insertbackground=C["text"], relief="flat",
            font=(FONT, 10),
        )
        add_entry.pack(side="left", fill="x", expand=True, ipady=4)

        def add_option():
            val = add_var.get().strip()
            if val and val not in self.config_data.get("note_options", []):
                self.config_data.setdefault("note_options", []).append(val)
                listbox.insert("end", val)
                self._save_config()
            add_var.set("")

        def delete_selected():
            sel = listbox.curselection()
            if not sel:
                return
            val = listbox.get(sel[0])
            listbox.delete(sel[0])
            opts = self.config_data.get("note_options", [])
            if val in opts:
                opts.remove(val)
                self._save_config()

        HoverButton(
            btn_frame, text=" Add ", command=add_option,
            bg=C["green"], fg=C["crust"], relief="flat", padx=8, pady=4,
            hover_bg=C["teal"], hover_fg=C["crust"], font=(FONT, 10),
        ).pack(side="left", padx=(4, 0))

        add_entry.bind("<Return>", lambda e: add_option())

        bottom_frame = tk.Frame(dlg, bg=C["base"])
        bottom_frame.pack(fill="x", padx=16, pady=(4, 12))

        HoverButton(
            bottom_frame, text=" Delete Selected ", command=delete_selected,
            bg=C["red"], fg=C["crust"], relief="flat", padx=8, pady=4,
            hover_bg=C["red"], hover_fg=C["crust"], font=(FONT, 10),
        ).pack(side="left")

        HoverButton(
            bottom_frame, text=" Close ", command=dlg.destroy,
            bg=C["surface1"], fg=C["text"], relief="flat", padx=8, pady=4,
            hover_bg=C["surface2"], font=(FONT, 10),
        ).pack(side="right")

    # ── SPICE Launch ─────────────────────────────────────────────────────────
    def _launch_spice(self):
        vms = self._get_selected_vms()
        if not vms:
            messagebox.showinfo("No Selection", "Select a VM to launch.", parent=self)
            return
        running = [vm for vm in vms if vm["status"] == "running"]
        if not running:
            self.status_label.config(
                text=f"{vms[0]['name']} is not running. Start it first (S)." if len(vms) == 1
                else "None of the selected VMs are running.",
                fg=C["red"],
            )
            return
        cluster = self.current_cluster
        auth = self._get_auth(cluster)
        if not auth:
            return
        for vm in running:
            self._launch_one(cluster, auth, vm)

    def _launch_one(self, cluster, auth, vm):
        DebugLogger.log(f"[SPICE] Launching VM {vm['vmid']} ({vm['name']}) "
                        f"on {cluster.get('name', '?')}")
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

            viewer = self._platform_find_viewer()
            if not viewer:
                self.after(0, lambda: (
                    self.status_label.config(text="remote-viewer not found", fg=C["red"]),
                    messagebox.showerror(
                        "Missing", "remote-viewer not found.\nCheck prerequisites.",
                        parent=self,
                    ),
                ))
                return

            vv_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", prefix="proxmox-spice-", suffix=".vv",
                    delete=False, encoding="utf-8",
                ) as f:
                    vv_path = f.name
                    f.write("[virt-viewer]\n")
                    for key in ("type", "host", "port", "tls-port", "password",
                                "proxy", "host-subject", "ca"):
                        f.write(f"{key}={spice_data.get(key, '')}\n")
                    f.write(
                        "toggle-fullscreen=shift+f11\n"
                        "release-cursor=shift+f12\n"
                        "secure-attention=ctrl+alt+end\n"
                        "delete-this-file=1\n"
                    )

                self._platform_set_vv_permissions(vv_path)
                self._platform_launch_viewer(viewer, vv_path)

                self.after(0, lambda: self.status_label.config(
                    text=f"Connected to {vm['name']} ({vm['vmid']})", fg=C["green"]
                ))
            except Exception as e:
                if vv_path:
                    try:
                        os.unlink(vv_path)
                    except OSError:
                        pass
                # Bind now: Python unbinds `e` when the except block ends,
                # before the deferred callback runs.
                err = str(e)
                self.after(0, lambda: messagebox.showerror(
                    "Launch Error", err, parent=self
                ))

        threading.Thread(target=connect, daemon=True).start()

    # ── Power Actions ────────────────────────────────────────────────────────
    def _vm_power_action(self, action, action_label):
        vms = self._get_selected_vms()
        if not vms:
            messagebox.showinfo("No Selection", "Select one or more VMs.", parent=self)
            return

        if action == "start":
            valid = [v for v in vms if v["status"] != "running"]
        else:
            valid = [v for v in vms if v["status"] == "running"]

        if not valid:
            messagebox.showinfo("No Action", "All selected VMs are already in the target state.", parent=self)
            return

        names = ", ".join(f"{v['name']} ({v['vmid']})" for v in valid)
        if action == "stop" and not messagebox.askyesno("Force Stop", f"Force stop?\n\n{names}\n\nUnsaved data may be lost.", parent=self):
            return
        if action == "shutdown" and not messagebox.askyesno("Shutdown", f"Shutdown?\n\n{names}", parent=self):
            return
        if action == "reboot" and not messagebox.askyesno("Reboot", f"Reboot?\n\n{names}", parent=self):
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
                data = api_request(
                    cluster["host"],
                    f"/api2/json/nodes/{vm['node']}/qemu/{vm['vmid']}/status/{action}",
                    method="POST", auth=auth,
                )
                err = data.get("error")
                if err and "already" not in str(err).lower():
                    errors.append(f"{vm['name']}: {err}")

            expected = {
                str(vm["vmid"]): ("running" if action in ("start", "reboot") else "stopped")
                for vm in valid
            }

            def on_done():
                if errors:
                    self.status_label.config(text="Some actions failed", fg=C["red"])
                    messagebox.showerror("Errors", "\n".join(errors), parent=self)
                else:
                    self.status_label.config(
                        text=f"{action_label} sent to {len(valid)} VM(s)", fg=C["green"]
                    )

            self.after(0, on_done)
            self.after(0, lambda: self._poll_until_changed(expected, auth=poll_auth))

        threading.Thread(target=do_action, daemon=True).start()

    def _start_vm(self):
        self._vm_power_action("start", "Starting")

    def _shutdown_vm(self):
        self._vm_power_action("shutdown", "Shutting down")

    def _stop_vm(self):
        self._vm_power_action("stop", "Force stopping")

    def _reboot_vm(self):
        self._vm_power_action("reboot", "Rebooting")

    # ── Quick Rollback ───────────────────────────────────────────────────────
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
            data = api_request(
                cluster["host"],
                f"/api2/json/nodes/{vm['node']}/qemu/{vm['vmid']}/snapshot",
                auth=saved_auth,
            )
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
                    rb = api_request(
                        cluster["host"],
                        f"/api2/json/nodes/{vm['node']}/qemu/{vm['vmid']}"
                        f"/snapshot/{urllib.parse.quote(snap_name, safe='')}/rollback",
                        method="POST", auth=saved_auth,
                    )
                    if "error" in rb:
                        self.after(0, lambda: messagebox.showerror("Failed", rb["error"], parent=self))
                    else:
                        self.after(0, lambda: self.status_label.config(
                            text=f"Rolled back to '{snap_name}'", fg=C["green"]
                        ))
                        self.after(0, lambda: self._poll_until_changed(
                            {str(vm["vmid"]): "stopped"}, auth=saved_auth
                        ))

                threading.Thread(target=do_rb, daemon=True).start()

            self.after(0, confirm)

        threading.Thread(target=fetch, daemon=True).start()

    # ── Polling ──────────────────────────────────────────────────────────────
    def _poll_until_changed(self, expected, auth=None, attempts=0, max_attempts=12):
        if self._closing:
            return
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
            data = api_request(
                cluster["host"], "/api2/json/cluster/resources?type=vm",
                auth=saved_auth,
            )
            if "error" in data:
                return
            vms = data.get("data", [])
            all_ok = all(
                next((v for v in vms if str(v.get("vmid")) == vmid), {}).get("status") == exp
                for vmid, exp in expected.items()
            )
            if all_ok:
                self.after(0, self._refresh_vms)
            else:
                self.after(0, lambda: self.after(
                    10000, lambda: self._poll_until_changed(
                        expected, auth=saved_auth, attempts=attempts + 1
                    )
                ))

        threading.Thread(target=check, daemon=True).start()

    def _poll_snap_changed(self, vmid, node, old_count, auth=None, attempts=0, max_attempts=12):
        if self._closing:
            return
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
            snap_data = api_request(
                cluster["host"],
                f"/api2/json/nodes/{node}/qemu/{vmid}/snapshot",
                auth=saved_auth,
            )
            if "error" in snap_data:
                return
            current = len([
                s for s in snap_data.get("data", []) if s.get("name") != "current"
            ])
            if current != old_count:
                self.after(0, self._refresh_vms)
            else:
                self.after(0, lambda: self.after(
                    10000, lambda: self._poll_snap_changed(
                        vmid, node, old_count, auth=saved_auth, attempts=attempts + 1
                    )
                ))

        threading.Thread(target=check, daemon=True).start()

    # ── Snapshots ────────────────────────────────────────────────────────────
    def _show_snapshots(self):
        vm = self._get_selected_vm()
        if not vm:
            return
        auth = self._get_auth(self.current_cluster)
        if not auth:
            return
        saved_auth = auth
        SnapshotDialog(
            self, vm, self.current_cluster, auth,
            on_change=lambda vmid, node, old_count:
                self._poll_snap_changed(vmid, node, old_count, auth=saved_auth),
        )


CONFIG_DIR = Path.home() / ".config" / "proxmox-spice"
CONFIG_FILE = CONFIG_DIR / "connections.json"
APP_ID = "proxmox-spice-manager"

_BASE_DIR = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent
ICON_PATH = _BASE_DIR / "icon.png"


# ─── Dependency Definitions ───────────────────────────────────────────────────
REQUIRED_DEPS = {
    "virt-viewer": {
        "cmd": "remote-viewer",
        "desc": "SPICE client (virt-viewer)",
        "pkg_dnf": "virt-viewer",
        "pkg_apt": "virt-viewer",
    },
    "python3-keyring": {
        "module": "keyring",
        "desc": "OS Keyring integration for secure passwords",
        "pkg_dnf": "python3-keyring",
        "pkg_apt": "python3-keyring",
    },
}


# ─── System Helpers ───────────────────────────────────────────────────────────
def _can_sudo():
    if not shutil.which("sudo"):
        return False
    try:
        result = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=5)
        if result.returncode == 0:
            return True
        groups = subprocess.run(
            ["groups"], capture_output=True, text=True, timeout=5
        ).stdout
        return "sudo" in groups or "wheel" in groups
    except Exception:
        return False


def _elevate_prefix():
    return "sudo" if _can_sudo() else "su -c"


def detect_pkg_manager():
    if shutil.which("dnf"):
        return "dnf"
    if shutil.which("apt"):
        return "apt"
    return None


def get_install_cmd(dep_info, fallback_name):
    mgr = detect_pkg_manager()
    if not mgr:
        return f"# Install '{fallback_name}' using your package manager"
    pkg = dep_info.get(f"pkg_{mgr}", fallback_name)
    elev = _elevate_prefix()
    if elev == "sudo":
        return f"sudo {mgr} install {pkg}"
    return f"su -c '{mgr} install {pkg}'"


def check_deps():
    results = {}
    all_ok = True
    for name, info in REQUIRED_DEPS.items():
        if "cmd" in info:
            found = shutil.which(info["cmd"]) is not None
        elif "module" in info:
            try:
                importlib.import_module(info["module"])
                found = True
            except ImportError:
                found = False
        else:
            found = False
        results[name] = found
        if not found:
            all_ok = False
    return all_ok, results


# ─── Keyring Secret Management ──────────────────────────────────────────────
def save_secret(cluster_name, secret):
    try:
        import keyring
        keyring.set_password(APP_ID, cluster_name, secret)
        return True
    except Exception as e:
        print(f"[debug] save_secret failed: {type(e).__name__}", file=sys.stderr)
        return False


def get_secret(cluster_name):
    try:
        import keyring
        return keyring.get_password(APP_ID, cluster_name)
    except Exception as e:
        print(f"[debug] get_secret failed: {type(e).__name__}", file=sys.stderr)
        return None


def delete_secret(cluster_name):
    try:
        import keyring
        keyring.delete_password(APP_ID, cluster_name)
    except Exception as e:
        print(f"[debug] delete_secret failed: {type(e).__name__}", file=sys.stderr)


def save_config(config):
    config["version"] = APP_VERSION
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, 0o700)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    os.chmod(CONFIG_FILE, 0o600)


def migrate_secrets(config):
    try:
        import keyring
    except ImportError:
        return

    changed = False
    for cluster in config.get("clusters", []):
        if "token_secret" in cluster:
            secret = cluster["token_secret"]
            if secret:
                try:
                    keyring.set_password(APP_ID, cluster["name"], secret)
                    del cluster["token_secret"]
                    changed = True
                except Exception as e:
                    print(f"[warn] Could not migrate secret for "
                          f"'{cluster['name']}' to keyring: {e} — "
                          "secret remains in config file", file=sys.stderr)
            else:
                del cluster["token_secret"]
                changed = True
    if changed:
        save_config(config)


# ─── Icon Picker Dialog ─────────────────────────────────────────────────────
class IconPickerDialog(tk.Toplevel):
    SYSTEM_ICONS = [
        ("preferences-system-network", "Network Settings"),
        ("computer", "Computer"),
        ("network-server", "Server"),
        ("preferences-desktop-remote-desktop", "Remote Desktop"),
        ("utilities-terminal", "Terminal"),
        ("monitor", "Monitor"),
        ("network-workgroup", "Workgroup"),
        ("preferences-system", "System"),
        ("applications-internet", "Internet"),
        ("virtual-machine", "Virtual Machine"),
    ]

    def __init__(self, parent):
        super().__init__(parent)
        self.result = None
        self.title("Choose App Icon")
        self.geometry("460x520")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self.configure(bg=C["base"])

        tk.Frame(self, bg=C["mauve"], height=3).pack(fill="x")

        main = tk.Frame(self, bg=C["base"], padx=24, pady=16)
        main.pack(fill="both", expand=True)

        lbl = {"bg": C["base"], "fg": C["subtext0"], "font": ("sans-serif", 9)}
        tk.Label(main, text="SYSTEM ICONS", **lbl).pack(anchor="w", pady=(0, 8))

        icon_grid = tk.Frame(main, bg=C["base"])
        icon_grid.pack(fill="x", pady=(0, 16))

        self.icon_var = tk.StringVar(value="preferences-system-network")
        for i, (icon_name, label) in enumerate(self.SYSTEM_ICONS):
            row, col = divmod(i, 2)
            frame = tk.Frame(icon_grid, bg=C["base"])
            frame.grid(row=row, column=col, sticky="w", padx=(0, 16), pady=2)
            tk.Radiobutton(
                frame, text=f"  {label}", variable=self.icon_var,
                value=icon_name, bg=C["base"], fg=C["text"],
                selectcolor=C["surface0"], activebackground=C["base"],
                activeforeground=C["text"], font=("sans-serif", 10), anchor="w",
            ).pack(side="left")
        icon_grid.columnconfigure(0, weight=1)
        icon_grid.columnconfigure(1, weight=1)

        tk.Frame(main, bg=C["surface0"], height=1).pack(fill="x", pady=(4, 16))
        tk.Label(main, text="CUSTOM ICON", **lbl).pack(anchor="w", pady=(0, 8))

        custom_frame = tk.Frame(main, bg=C["base"])
        custom_frame.pack(fill="x", pady=(0, 8))

        self.custom_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            custom_frame, text="  Use custom icon file",
            variable=self.custom_var, bg=C["base"], fg=C["text"],
            selectcolor=C["surface0"], activebackground=C["base"],
            activeforeground=C["text"], font=("sans-serif", 10),
            command=self._toggle_custom,
        ).pack(side="left")

        self.custom_path_frame = tk.Frame(main, bg=C["base"])
        entry_cfg = {
            "bg": C["surface0"], "fg": C["text"], "insertbackground": C["text"],
            "relief": "flat", "font": ("monospace", 10), "highlightthickness": 1,
            "highlightcolor": C["blue"], "highlightbackground": C["surface1"],
        }

        path_row = tk.Frame(self.custom_path_frame, bg=C["base"])
        path_row.pack(fill="x", pady=(4, 4))
        self.icon_path_entry = tk.Entry(path_row, **entry_cfg)
        self.icon_path_entry.pack(
            side="left", fill="x", expand=True, ipady=6, padx=(0, 8)
        )
        HoverButton(
            path_row, text=" Browse ", command=self._browse_icon,
            bg=C["surface0"], fg=C["subtext0"], relief="flat", padx=12, pady=4,
            hover_bg=C["surface1"], hover_fg=C["text"], font=("sans-serif", 9),
        ).pack(side="right")

        tk.Label(
            self.custom_path_frame, text="PNG, SVG, or ICO file",
            bg=C["base"], fg=C["overlay0"], font=("sans-serif", 8),
        ).pack(anchor="w")
        self.preview_label = tk.Label(
            self.custom_path_frame, text="", bg=C["base"],
            fg=C["overlay0"], font=("sans-serif", 9),
        )
        self.preview_label.pack(anchor="w", pady=(4, 0))

        btn_frame = tk.Frame(main, bg=C["base"])
        btn_frame.pack(side="bottom", anchor="e", pady=(16, 0))
        HoverButton(
            btn_frame, text="Cancel", command=self._cancel,
            bg=C["surface1"], fg=C["text"], relief="flat", padx=18, pady=6,
            hover_bg=C["surface2"], font=("sans-serif", 10),
        ).pack(side="right", padx=(8, 0))
        HoverButton(
            btn_frame, text="  Install  ", command=self._confirm,
            bg=C["green"], fg=C["crust"], relief="flat", padx=18, pady=6,
            hover_bg=C["teal"], hover_fg=C["crust"],
            font=("sans-serif", 10, "bold"),
        ).pack(side="right")

        self.wait_window()

    def _toggle_custom(self):
        if self.custom_var.get():
            self.custom_path_frame.pack(fill="x", pady=(0, 8))
        else:
            self.custom_path_frame.pack_forget()

    def _browse_icon(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            parent=self, title="Select Icon File",
            filetypes=[("Image files", "*.png *.svg *.ico *.xpm"),
                       ("All files", "*.*")],
        )
        if path:
            self.icon_path_entry.delete(0, "end")
            self.icon_path_entry.insert(0, path)
            self.preview_label.config(text=f"Selected: {Path(path).name}")

    def _confirm(self):
        if self.custom_var.get():
            path = self.icon_path_entry.get().strip()
            if not path:
                messagebox.showwarning(
                    "No Icon", "Enter a path or browse for an icon file.",
                    parent=self,
                )
                return
            if not os.path.isfile(path):
                messagebox.showwarning(
                    "File Not Found", f"Could not find:\n{path}", parent=self
                )
                return
            self.result = path
        else:
            self.result = self.icon_var.get()
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ─── Prereq Dialog ────────────────────────────────────────────────────────────
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
            bg=C["base"], fg=C["text"], font=("sans-serif", 13, "bold"),
        ).pack(anchor="w", pady=(0, 4))
        tk.Label(
            main,
            text="Some required tools are missing. Install them to continue.",
            bg=C["base"], fg=C["subtext0"], font=("sans-serif", 10),
        ).pack(anchor="w", pady=(0, 20))

        tk.Label(
            main, text="DEPENDENCIES", bg=C["base"], fg=C["overlay0"],
            font=("sans-serif", 8, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        mgr = detect_pkg_manager()
        missing_pkgs = []

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
                fg=status_color, font=("sans-serif", 12, "bold"),
            ).pack(side="left", padx=(0, 8))
            tk.Label(
                header_row, text=name, bg=C["surface0"], fg=C["text"],
                font=("sans-serif", 10, "bold"),
            ).pack(side="left")

            status_text = "Installed" if found else "Not found"
            tk.Label(
                header_row, text=f"  —  {status_text}", bg=C["surface0"],
                fg=status_color, font=("sans-serif", 9),
            ).pack(side="left")

            tk.Label(
                left, text=info["desc"], bg=C["surface0"], fg=C["subtext0"],
                font=("sans-serif", 9),
            ).pack(anchor="w", padx=(28, 0))

            if not found:
                pkg = info.get(f"pkg_{mgr}", name) if mgr else name
                missing_pkgs.append(pkg)

                install_frame = tk.Frame(left, bg=C["surface0"])
                install_frame.pack(anchor="w", padx=(28, 0), pady=(4, 0))
                install_cmd = get_install_cmd(info, name)

                HoverButton(
                    install_frame, text=f"  ⬇  Install {pkg}  ",
                    command=lambda p=[pkg]: self._install_pkg(p),
                    bg=C["peach"], fg=C["crust"], relief="flat", padx=10, pady=3,
                    hover_bg=C["yellow"], hover_fg=C["crust"],
                    font=("sans-serif", 9, "bold"),
                ).pack(side="left")

                tk.Label(
                    install_frame, text=f"  {install_cmd}",
                    bg=C["surface0"], fg=C["overlay0"], font=("monospace", 8),
                ).pack(side="left", padx=(8, 0))

        if len(missing_pkgs) > 1:
            tk.Frame(main, bg=C["surface0"], height=1).pack(
                fill="x", pady=(12, 12)
            )
            HoverButton(
                main,
                text=f"  ⬇  Install All Missing ({len(missing_pkgs)})  ",
                command=lambda p=list(missing_pkgs): self._install_pkg(p),
                bg=C["peach"], fg=C["crust"], relief="flat", padx=14, pady=8,
                hover_bg=C["yellow"], hover_fg=C["crust"],
                font=("sans-serif", 10, "bold"),
            ).pack(fill="x", pady=(0, 4))

        prereq_btn_frame = tk.Frame(main, bg=C["base"])
        prereq_btn_frame.pack(side="bottom", fill="x", pady=(12, 0))

        HoverButton(
            prereq_btn_frame, text="Quit", command=self._cancel,
            bg=C["surface1"], fg=C["text"], relief="flat", padx=18, pady=6,
            hover_bg=C["surface2"], font=("sans-serif", 10),
        ).pack(side="right", padx=(8, 0))
        HoverButton(
            prereq_btn_frame, text="  Re-check  ",
            command=self._recheck,
            bg=C["blue"], fg=C["crust"], relief="flat", padx=18, pady=6,
            hover_bg=C["sapphire"], hover_fg=C["crust"],
            font=("sans-serif", 10, "bold"),
        ).pack(side="right")

        self.wait_window()

    def _launch_terminal(self, cmd):
        terminals = [
            ["konsole", "-e"], ["gnome-terminal", "--"],
            ["xfce4-terminal", "-e"], ["x-terminal-emulator", "-e"],
            ["xterm", "-e"],
        ]
        run_args = ["bash", "-c", cmd] if isinstance(cmd, str) else cmd
        for term_cmd in terminals:
            if shutil.which(term_cmd[0]):
                try:
                    subprocess.Popen(term_cmd + run_args)
                    return True
                except Exception:
                    continue
        return False

    def _install_pkg(self, packages):
        mgr = detect_pkg_manager()
        if not mgr:
            messagebox.showwarning(
                "Unknown Package Manager",
                f"Could not detect dnf or apt.\n\n"
                f"Manually install: {' '.join(packages)}",
                parent=self,
            )
            return

        safe_pkgs = " ".join(shlex.quote(p) for p in packages)
        elev = _elevate_prefix()
        if elev == "sudo":
            cmd_str = (
                f"sudo {shlex.quote(mgr)} install {safe_pkgs}; "
                "echo; echo 'Press Enter to close...'; read"
            )
            if not self._launch_terminal(cmd_str):
                messagebox.showwarning(
                    "No Terminal Found",
                    f"Run manually:\n  sudo {mgr} install {safe_pkgs}",
                    parent=self,
                )
                return
        else:
            fd, script_path = tempfile.mkstemp(
                suffix=".sh", prefix="proxmox-spice-install-"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write("#!/bin/bash\n")
                f.write(f"trap 'rm -f {shlex.quote(script_path)}' EXIT\n")
                f.write("echo ''\necho 'Enter root password:'\necho ''\n")
                f.write(f"su -c {shlex.quote(mgr + ' install ' + safe_pkgs)}\n")
                f.write("echo ''\necho 'Press Enter...'\nread\n")
            os.chmod(script_path, 0o700)

            if not self._launch_terminal(script_path):
                os.unlink(script_path)
                return

        messagebox.showinfo(
            "Installing",
            "A terminal window has opened.\n"
            "Enter the root password and approve the install.\n\n"
            "Click Re-check when it's done.",
            parent=self,
        )

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
        return APP_VERSION

    def _get_config_file(self):
        return CONFIG_FILE

    def _platform_set_icon(self):
        try:
            _icon_img = tk.PhotoImage(file=str(ICON_PATH))
            self.iconphoto(True, _icon_img)
        except Exception:
            pass

    def _platform_save_config(self, config):
        save_config(config)

    def _platform_get_secret(self, cluster_name):
        return get_secret(cluster_name)

    def _platform_save_secret(self, cluster_name, secret):
        save_secret(cluster_name, secret)

    def _platform_delete_secret(self, cluster_name):
        delete_secret(cluster_name)

    def _platform_migrate_secrets(self):
        migrate_secrets(self.config_data)

    def _platform_find_viewer(self):
        return shutil.which("remote-viewer")

    def _platform_set_vv_permissions(self, vv_path):
        os.chmod(vv_path, 0o600)

    def _platform_set_file_permissions(self, path):
        os.chmod(path, 0o600)

    def _platform_launch_viewer(self, viewer, vv_path):
        proc = subprocess.Popen([viewer, vv_path])
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

    def _platform_menu_entries(self):
        return [
            ("Install to app menu…", self._install_to_app_menu),
            ("Export .desktop for selected VM…", self._export_desktop),
        ]

    def _export_desktop(self):
        vm = self._get_selected_vm()
        if not vm:
            return

        desktop_dir = Path.home() / ".local" / "share" / "applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)
        filepath = desktop_dir / f"spice-vm{vm['vmid']}.desktop"
        script_path = Path.home() / "proxmox-spice-manager.py"

        content = (
            "[Desktop Entry]\n"
            f"Name={vm['name']} (VM {vm['vmid']})\n"
            f"Exec=/usr/bin/python3 \"{script_path}\"\n"
            "Icon=computer\n"
            "Type=Application\n"
            "Terminal=false\n"
            "Categories=System;\n"
        )
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(filepath, 0o755)
        messagebox.showinfo(
            "Exported", f"Desktop launcher saved:\n{filepath}", parent=self
        )

    def _install_to_app_menu(self):
        icon_dlg = IconPickerDialog(self)
        if icon_dlg.result is None:
            return

        icon_value = icon_dlg.result
        script_name = "proxmox-spice-manager.py"
        installed_script = Path.home() / script_name
        desktop_dir = Path.home() / ".local" / "share" / "applications"
        desktop_file = desktop_dir / "proxmox-spice-manager.desktop"

        if icon_value and os.path.isfile(icon_value):
            icon_dir = CONFIG_DIR / "icons"
            icon_dir.mkdir(parents=True, exist_ok=True)
            ext = Path(icon_value).suffix or ".png"
            dest_icon = icon_dir / f"app-icon{ext}"
            try:
                shutil.copy2(icon_value, dest_icon)
                icon_value = str(dest_icon)
            except Exception as e:
                messagebox.showerror(
                    "Icon Error", f"Could not copy icon:\n{e}", parent=self
                )
                return

        current_script = Path(os.path.abspath(__file__))
        try:
            if current_script.resolve() != installed_script.resolve():
                shutil.copy2(current_script, installed_script)
            os.chmod(installed_script, 0o755)
        except Exception as e:
            messagebox.showerror(
                "Install Failed", f"Could not copy script:\n{e}", parent=self
            )
            return

        desktop_dir.mkdir(parents=True, exist_ok=True)
        content = (
            "[Desktop Entry]\n"
            "Name=Proxmox SPICE Manager\n"
            f"Exec=/usr/bin/python3 \"{installed_script}\"\n"
            f"Icon={icon_value}\n"
            "Type=Application\n"
            "Terminal=false\n"
            "Categories=System;Network;\n"
            "Comment=Manage and launch SPICE console sessions "
            "to Proxmox VMs\n"
        )
        try:
            with open(desktop_file, "w", encoding="utf-8") as f:
                f.write(content)
            os.chmod(desktop_file, 0o755)
        except Exception as e:
            messagebox.showerror(
                "Install Failed",
                f"Could not create desktop entry:\n{e}",
                parent=self,
            )
            return

        messagebox.showinfo(
            "Installed",
            f"App installed!\n\nScript: ~/{script_name}\n"
            f"Icon: {icon_value}\nMenu entry created.\n\n"
            "It should appear in your app menu shortly.",
            parent=self,
        )


if __name__ == "__main__":
    if not _acquire_instance_lock():
        root = tk.Tk()
        root.withdraw()
        messagebox.showwarning(
            "Already Running",
            "Proxmox SPICE Manager is already running.",
        )
        root.destroy()
        sys.exit(1)
    app = ProxmoxSpiceManager()
    app.mainloop()
