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
from __future__ import annotations

import copy
import fcntl
import hashlib
import http.client
import importlib
import ipaddress
import json
import logging
import logging.handlers
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import ssl
import urllib.parse
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter import font as tkfont

APP_ID = "proxmox-spice-manager"
APP_VERSION = "3.0.0"
REPO_URL = "https://github.com/darthrater78/proxmoxspicemanager"

Json = Dict[str, Any]  # a Proxmox API answer, a cluster or the config


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


def on_accent(hex_color: str) -> str:
    """Near-black or white, whichever contrasts more with the accent."""
    def lin(c):
        v = c / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    dark_lum = 0.0103  # relative luminance of #1a1a1a
    return "#1a1a1a" if (lum + 0.05) / (dark_lum + 0.05) >= 1.05 / (lum + 0.05) else "#ffffff"


def apply_theme(theme: str, accent: str) -> None:
    """Load a theme and accent into C, the palette every widget reads."""
    C.update(THEMES.get(theme, THEMES[DEFAULT_THEME]))
    C["accent"] = C[ACCENTS.get(accent, ACCENTS[DEFAULT_ACCENT])]
    C["on_accent"] = on_accent(C["accent"])


C = {}
apply_theme(DEFAULT_THEME, DEFAULT_ACCENT)

# Font constants — overridden by platform scripts before UI is built
FONT = "sans-serif"
MONO = "monospace"




# Proxmox tickets last 2 hours. A cached one is renewed after an hour (the ticket works as
# the password for that), and one this close to expiring is dropped and the password asked.
TICKET_RENEW_AFTER = 60 * 60
TICKET_MAX_AGE = 110 * 60

# Every Windows DPAPI blob starts with this (base64): an encrypted secret this app can't read
DPAPI_PREFIX = "AQAAANCMnd8BFdERjHoAwE/Cl+"


# ─── Proxmox API Helpers ─────────────────────────────────────────────────────
class TlsUntrusted(Exception):
    """The server's certificate isn't trusted: not signed by a CA this system
    trusts, and not the one pinned for the cluster. Raised before anything
    (token, password, ticket) is sent."""

    def __init__(self, fingerprint, changed):
        super().__init__("certificate changed" if changed else "certificate not trusted")
        self.fingerprint = fingerprint
        self.changed = changed  # a pin exists and this certificate doesn't match it


def cert_fingerprint(der: bytes) -> str:
    """SHA-256 of a DER certificate, as Proxmox shows it: AB:CD:…"""
    return ":".join(f"{b:02X}" for b in hashlib.sha256(der).digest())


def _fetch_fingerprint(hostname: str, port: int, timeout: float) -> str:
    """The certificate a server presents, read without trusting it (only to show the user)."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with socket.create_connection((hostname, port), timeout=timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=hostname) as tls:
            return cert_fingerprint(tls.getpeercert(binary_form=True))


def _connect(host: str, pin: str | None, timeout: float) -> http.client.HTTPSConnection:
    """An HTTPS connection whose certificate is already checked, before any request is
    sent: CA-verified as usual, or, when the cluster has a pinned fingerprint, exactly
    that certificate. Anything else raises TlsUntrusted."""
    url = urllib.parse.urlparse(host)
    hostname, port = url.hostname, url.port or 443
    ctx = ssl.create_default_context()
    if pin:
        # The pin replaces CA and hostname checks; the fingerprint check below is stricter
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    conn = http.client.HTTPSConnection(hostname, port, context=ctx, timeout=timeout)
    try:
        conn.connect()
    except ssl.SSLCertVerificationError:
        conn.close()
        raise TlsUntrusted(_fetch_fingerprint(hostname, port, timeout), changed=False) from None
    if pin:
        seen = cert_fingerprint(conn.sock.getpeercert(binary_form=True))
        if seen != pin:
            conn.close()
            raise TlsUntrusted(seen, changed=True)
    return conn


# Idle keep-alive connections per (host, port, pin), reused by GETs; each was checked
# by _connect when it was opened. Older than _POOL_IDLE seconds, the server has likely
# closed it.
_POOL_IDLE = 20
_POOL_SIZE = 8
_pool = {}
_pool_lock = threading.Lock()


def _pool_key(host: str, pin: str | None) -> tuple[str | None, int, str | None]:
    url = urllib.parse.urlparse(host)
    return url.hostname, url.port or 443, pin


def _pooled(key: tuple, timeout: float) -> http.client.HTTPSConnection | None:
    """An idle connection for `key`, or None. Also closes every cluster's expired ones,
    so a cluster no longer in use doesn't keep its sockets open."""
    now = time.monotonic()
    with _pool_lock:
        for pool_key in list(_pool):
            fresh = []
            for conn, used in _pool[pool_key]:
                if now - used < _POOL_IDLE and conn.sock is not None:
                    fresh.append((conn, used))
                else:
                    conn.close()
            _pool[pool_key] = fresh
        idle = _pool.get(key, [])
        if not idle:
            return None
        conn, _ = idle.pop()
    conn.sock.settimeout(timeout)
    return conn


def _release(key: tuple, conn: http.client.HTTPSConnection) -> None:
    with _pool_lock:
        idle = _pool.setdefault(key, [])
        if len(idle) < _POOL_SIZE:
            idle.append((conn, time.monotonic()))
            return
    conn.close()


def _send(host: str, pin: str | None, method: str, path: str, body: bytes | None,
          headers: dict[str, str], timeout: float) -> tuple[int, str, Any]:
    """(status, reason, parsed JSON or None) for one request over a checked connection.
    GETs reuse an idle connection to the same cluster; anything else gets a fresh one,
    so an action is never sent twice over a connection the server had already closed."""
    key = _pool_key(host, pin)
    reuse = method == "GET"
    conn = _pooled(key, timeout) if reuse else None
    while True:
        reused = conn is not None
        if conn is None:
            conn = _connect(host, pin, timeout)
        try:
            conn.request(method, path, body=body, headers=headers)
            response = conn.getresponse()
            raw = response.read()
        except (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError):
            conn.close()
            if not reused:
                raise
            conn = None  # the server closed the idle connection: once more on a new one
            continue
        except BaseException:
            conn.close()
            raise
        break
    if reuse and not response.will_close:
        _release(key, conn)
    else:
        conn.close()
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        parsed = None
    return response.status, response.reason, parsed


def api_request(host: str, endpoint: str, method: str = "GET", auth: Json | None = None,
                data: bytes | None = None, timeout: float = 15) -> Json:
    if not host.startswith("https://"):
        return {"error": "Host must use https://"}
    base = urllib.parse.urlparse(host).path.rstrip("/")
    headers = {}
    if auth:
        if auth.get("token_id") and auth.get("token_secret"):
            headers["Authorization"] = f"PVEAPIToken={auth['token_id']}={auth['token_secret']}"
        elif auth.get("ticket"):
            headers["Cookie"] = f"PVEAuthCookie={auth['ticket']}"
            if auth.get("csrf"):
                headers["CSRFPreventionToken"] = auth["csrf"]
    if method in ("POST", "DELETE", "PUT"):
        data = data if data is not None else b""
        headers["Content-Type"] = "application/x-www-form-urlencoded"

    try:
        status, reason, body = _send(host, (auth or {}).get("tls_fingerprint"), method,
                                     base + endpoint, data, headers, timeout)
    except TlsUntrusted as e:
        return {"error": f"TLS {e}", "tls_untrusted": e.fingerprint, "tls_changed": e.changed}
    except (OSError, http.client.HTTPException) as e:
        return {"error": f"Connection failed: {e}"}
    if status >= 400:
        if isinstance(body, dict):
            if "message" in body and "error" not in body:
                body["error"] = body["message"]
            if "error" in body:
                return body
        return {"error": f"HTTP {status}: {reason}"}
    return body if isinstance(body, dict) else {"error": "Invalid response"}


def authenticate_password(host: str, username: str, password: str,
                          pin: str | None = None) -> dict[str, str] | None:
    """A ticket for username/password, or None. Raises TlsUntrusted before the password
    leaves this machine when the server's certificate isn't trusted."""
    # Never send a password over plain HTTP (an imported or hand-edited config
    # can bypass the check in ClusterDialog).
    if not host.lower().startswith("https://"):
        return None
    body = urllib.parse.urlencode({"username": username, "password": password}).encode("utf-8")
    base = urllib.parse.urlparse(host).path.rstrip("/")
    try:
        _, _, res = _send(host, pin, "POST", f"{base}/api2/json/access/ticket", body,
                          {"Content-Type": "application/x-www-form-urlencoded"}, 15)
    except (OSError, http.client.HTTPException) as e:
        print(f"[debug] authenticate_password failed: {type(e).__name__}", file=sys.stderr)
        return None
    data = (res or {}).get("data") or {}
    if data.get("ticket"):
        return {"ticket": data["ticket"], "csrf": data.get("CSRFPreventionToken", "")}
    return None


def wait_for_task(host: str, auth: Json, upid: Any, timeout: float = 180) -> str | None:
    """Block until the Proxmox task a POST started (its UPID) ends: None once it ended well,
    else why not. Start, shutdown, snapshots etc. run as tasks, so the POST returns first."""
    if not isinstance(upid, str) or not upid.startswith("UPID:"):
        return None  # nothing to wait for
    node = upid.split(":")[1]
    path = (f"/api2/json/nodes/{urllib.parse.quote(node, safe='')}"
            f"/tasks/{urllib.parse.quote(upid, safe='')}/status")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        task = api_request(host, path, auth=auth).get("data") or {}
        if task.get("status") == "stopped":
            exit_status = task.get("exitstatus", "")
            return None if exit_status == "OK" or exit_status.startswith("WARNINGS") \
                else exit_status or "task failed"
        time.sleep(1)
    return "still running after 3 minutes"


def write_vv_file(spice_data: Json) -> str:
    """A remote-viewer connection file from Proxmox's spiceproxy answer; returns its path.
    Created private (0600); remote-viewer deletes it once read (delete-this-file)."""
    with tempfile.NamedTemporaryFile(
        mode="w", prefix="proxmox-spice-", suffix=".vv", delete=False, encoding="utf-8",
    ) as f:
        try:
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
        except OSError:
            os.unlink(f.name)
            raise
    return f.name


# ─── Config Persistence ──────────────────────────────────────────────────────
def load_config(config_file: Path) -> Json:
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
        self._original_host = cluster.get("host") if cluster else None
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

        # A self-signed certificate is confirmed on first connect and pinned (no "skip TLS")
        self._pin = cluster.get("tls_fingerprint") if cluster else None
        cert_row = tk.Frame(main, bg=C["base"])
        cert_row.grid(row=4, column=0, sticky="ew", pady=(0, 12))
        self._cert_label = tk.Label(cert_row, bg=C["base"], fg=C["subtext0"], font=(FONT, 9),
                                    anchor="w", justify="left")
        self._cert_label.pack(side="left", fill="x", expand=True)
        self._forget_btn = HoverButton(
            cert_row, text="Forget", command=self._forget_pin,
            bg=C["surface0"], fg=C["text"], relief="flat", padx=10, pady=2,
            hover_bg=C["surface1"], font=(FONT, 9),
        )
        self._show_pin()

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

    def _show_pin(self):
        if self._pin:
            self._cert_label.config(text=f"Certificate pinned: {self._pin[:23]}…")
            self._forget_btn.pack(side="right")
        else:
            self._cert_label.config(
                text="Certificate: checked by this system. A self-signed one is\n"
                     "shown for you to confirm on first connect.")
            self._forget_btn.pack_forget()

    def _forget_pin(self):
        self._pin = None
        self._show_pin()

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
        }
        # A pin belongs to the host it was confirmed for
        if self._pin and (self.original_name is None or host == self._original_host):
            self.result["tls_fingerprint"] = self._pin
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

        self.status_label.config(text=f"{count} snapshot(s)", fg=C["overlay0"])

    def _finish_task(self, data, what, done):
        """Wait in the background for the task Proxmox started, then show how it ended,
        reload the list and let the main window refresh (on_change)."""
        self.status_label.config(text=f"{what}: waiting for Proxmox...", fg=C["yellow"])
        app = self.master

        def run():
            error = wait_for_task(self.cluster["host"], self.auth, data.get("data"))
            app._post(lambda: finish(error))

        def finish(error):
            if self.on_change:
                self.on_change()
            if not self.winfo_exists():
                return  # closed meanwhile
            self._load_snapshots()
            if error:
                self.status_label.config(text=f"{what} failed", fg=C["red"])
                messagebox.showerror(f"{what} Failed", error, parent=self)
            else:
                self.status_label.config(text=done, fg=C["green"])

        threading.Thread(target=run, daemon=True).start()

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
            self._finish_task(data, "Rollback", f"Rolled back to '{snap_name}'")

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
            self._finish_task(data, "Snapshot", f"Snapshot '{result['name']}' created")

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
            self._finish_task(data, "Delete", f"Snapshot '{snap_name}' deleted")


# ─── Base Application ────────────────────────────────────────────────────────
# ─── Main-window widgets ──────────────────────────────────────────────────────
def mix(c1: str, c2: str, t: float) -> str:
    """Blend two #rrggbb colours; t=0 gives c1, t=1 gives c2."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def round_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float, r: float,
               **kw: Any) -> int:
    points = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
              x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(points, smooth=True, **kw)


def os_badge(ostype: str) -> str:
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


def os_label(ostype: str) -> str:
    return OS_LABELS.get(ostype, ostype or "Unknown OS")


# Sort keys, shared names with the Windows app's `vm_sort` config value
SORT_LABELS = {
    "name": "Name", "vmid": "ID", "ip": "Address", "node": "Node",
    "pool": "Pool", "snaps": "Snapshots", "status": "Status", "notes": "Notes",
}


def agent_has_agent(value: Any) -> bool:
    """True when a VM config's `agent` value ("1", "enabled=1,fstrim_cloned_disks=1") turns it on."""
    value = str(value or "")
    return value.startswith("1") or "enabled=1" in value.split(",")


def agent_ips(interfaces: Any) -> list[tuple[str, str]]:
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


def vm_ips(vm: Json, ipv6: bool) -> list[tuple[str, str]]:
    """The VM's addresses to show: IPv6 only when that setting is on."""
    return [(a, ip) for a, ip in vm.get("ips", []) if ipv6 or ":" not in ip]


def note_lines(text: str) -> list[str]:
    """Proxmox notes as plain lines: no markdown heading or list markers, no blank lines."""
    lines = (line.strip().lstrip("#*->").strip() for line in (text or "").splitlines())
    return [line for line in lines if line]


def notes_cell(vm: Json) -> str:
    """The list's Notes column: the first line of the Proxmox notes, else this app's note."""
    return next(iter(note_lines(vm.get("pve_note", ""))), "") or vm["note"]


def fit_addresses(ips: list[str], width: int, measure: Callable[[str], int]) -> str:
    """As many addresses as fit in `width` pixels, then "+N" for the rest."""
    full = ", ".join(ips)
    if len(ips) <= 1 or measure(full) <= width:
        return full
    for shown in range(len(ips) - 1, 0, -1):
        text = f"{', '.join(ips[:shown])} +{len(ips) - shown}"
        if measure(text) <= width:
            return text
    return f"{ips[0]} +{len(ips) - 1}"


def _ip_key(vm: Json, ipv6: bool) -> tuple:
    """Numeric order by first address, IPv4 before IPv6; no address ("no agent") after them."""
    ips = vm_ips(vm, ipv6)
    if ips:
        ip = ipaddress.ip_address(ips[0][1])
        return (0, ip.version, int(ip), "")
    return (1, 0, 0, vm.get("ip_note", ""))


def vm_sort_key(vm: Json, column: str, ipv6: bool = False) -> Any:
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


# Line icons on a 16 px grid, the same shapes as the Windows app's Icon* geometries.
# Each op is ("line", points), ("poly", points), ("oval", box) or
# ("arc", box, start, extent), with angles counterclockwise from 3 o'clock.
LINE_ICONS = {
    "monitor": [("poly", (3, 4, 13, 4, 13, 10, 3, 10)), ("line", (6, 13, 10, 13)),
                ("line", (8, 10, 8, 13))],
    "play": [("poly", (5, 3, 12.5, 8, 5, 13))],
    "power": [("line", (8, 2, 8, 7.5)), ("arc", (3, 3.07, 13, 13.07), 132.8, 274.4)],
    "refresh": [("arc", (3, 3, 13, 13), 0, -315), ("line", (11.5, 1.8, 11.5, 4.6, 8.7, 4.6))],
    "camera": [("poly", (2.5, 5, 5, 5, 6.5, 3, 9.5, 3, 11, 5, 13.5, 5, 13.5, 12.5, 2.5, 12.5)),
               ("oval", (5.8, 6.8, 10.2, 11.2))],
    "undo": [("line", (3, 6.5, 10, 6.5)), ("arc", (7, 6.5, 13, 12.5), 90, -180),
             ("line", (10, 12.5, 6, 12.5)), ("line", (5.5, 4, 3, 6.5, 5.5, 9))],
    "stop": [("poly", (4, 4, 12, 4, 12, 12, 4, 12))],
    "plus": [("line", (8, 3, 8, 13)), ("line", (3, 8, 13, 8))],
    "gear": [("oval", (5.8, 5.8, 10.2, 10.2)), ("line", (8, 1.8, 8, 3.4)),
             ("line", (8, 12.6, 8, 14.2)), ("line", (1.8, 8, 3.4, 8)),
             ("line", (12.6, 8, 14.2, 8)), ("line", (3.6, 3.6, 4.7, 4.7)),
             ("line", (11.3, 11.3, 12.4, 12.4)), ("line", (3.6, 12.4, 4.7, 11.3)),
             ("line", (11.3, 4.7, 12.4, 3.6))],
    "search": [("oval", (2.5, 2.5, 11.5, 11.5)), ("line", (10.3, 10.3, 13.5, 13.5))],
}


class LineIcon(tk.Canvas):
    """A 16 px stroked icon from LINE_ICONS."""

    def __init__(self, master, name, bg, color):
        super().__init__(master, width=16, height=16, bg=bg, highlightthickness=0, bd=0)
        stroke = {"width": 1.4}
        for op, coords, *angles in LINE_ICONS[name]:
            if op == "line":
                self.create_line(*coords, fill=color, capstyle="round", joinstyle="round",
                                 tags="stroke", **stroke)
            elif op == "poly":
                self.create_polygon(*coords, fill="", outline=color, joinstyle="round",
                                    tags="outline", **stroke)
            elif op == "oval":
                self.create_oval(*coords, outline=color, tags="outline", **stroke)
            else:
                start, extent = angles
                self.create_arc(*coords, start=start, extent=extent, style="arc",
                                outline=color, tags="outline", **stroke)

    def set_color(self, color):
        self.itemconfig("stroke", fill=color)
        self.itemconfig("outline", outline=color)


class ActionButton(tk.Frame):
    """Flat button made of labels: icon, text and key hint, with hover and a
    disabled state. tk.Button can't hold a right-aligned key hint."""

    def __init__(self, master, text, command, icon="", key="", bg=None, fg=None,
                 hover_bg=None, border=None, bold=False, pady=6, padx=10, icon_fg=None, elide=False):
        bg = bg or C["surface0"]
        super().__init__(master, bg=bg, highlightthickness=1,
                         highlightbackground=border or C["surface1"], cursor="hand2")
        self._bg = bg
        self._hover_bg = hover_bg or C["surface1"]
        self._fg = fg or C["text"]
        # Icons are a step quieter than the text, as on Windows, unless the button is coloured
        self._icon_fg = icon_fg or fg or C["subtext1"]
        self._icon = None
        self._command = command
        self._enabled = True
        font = (FONT, 10, "bold") if bold else (FONT, 10)
        inner = tk.Frame(self, bg=bg)
        inner.pack(fill="x", padx=padx, pady=pady)
        self._parts = [self, inner]
        self._labels = []
        if key:
            cap = KeyCap(inner, key, bg, fg=None if fg is None else fg)
            cap.pack(side="right", padx=(6, 0))
            self._parts.append(cap)
        if icon in LINE_ICONS:
            self._icon = LineIcon(inner, icon, bg, self._icon_fg)
            self._icon.pack(side="left", padx=(0, 6))
            self._parts.append(self._icon)
        elif icon:
            glyph = tk.Label(inner, text=icon, bg=bg, fg=self._fg, font=font, width=2, anchor="w")
            glyph.pack(side="left")
            self._parts.append(glyph)
            self._labels.append(glyph)
        self._text = text
        self._font = tkfont.Font(font=font)
        self.label = tk.Label(inner, text=text, bg=bg, fg=self._fg, font=font, anchor="w")
        self.label.pack(side="left", fill="x", expand=True)
        self._parts.append(self.label)
        self._labels.append(self.label)
        # A button stretched to a fixed width (elide=True): text too long for it ends in
        # an ellipsis rather than mid-letter. Only there: a button sized by its own text
        # would shrink to the cut text and keep it.
        self._elide = elide
        if elide:
            self.label.bind("<Configure>", lambda e: self._fit_text())
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
        if self._icon is not None:
            self._icon.set_color(self._icon_fg if enabled else mix(self._icon_fg, self._bg, 0.6))
        self.config(cursor="hand2" if enabled else "arrow")

    def set_text(self, text):
        self._text = text
        self._fit_text()

    def _fit_text(self):
        width = self.label.winfo_width()
        if not self._elide or width <= 1:
            text = self._text
        else:
            text = elide(self._text, width - 2, self._font)
        if self.label.cget("text") != text:
            self.label.config(text=text)


class Chip(tk.Canvas):
    """A rounded pill: the filter chips, the IPv6 and grouping toggles, the Sort button."""

    def __init__(self, master, command, chevron=False):
        super().__init__(master, height=28, bg=master["bg"], highlightthickness=0,
                         cursor="hand2")
        self._command = command
        self._chevron = chevron
        self._fonts = {False: tkfont.Font(font=(FONT, 10)),
                       True: tkfont.Font(font=(FONT, 10, "bold"))}
        self._style = None
        self._hover = False
        self.bind("<Button-1>", lambda e: (self._command(), "break")[1])
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))

    def _set_hover(self, hover):
        self._hover = hover
        self._draw()

    def set(self, text, bg, fg, border, bold=False, hover_bg=None):
        self._style = (text, bg, fg, border, bold, hover_bg or C["surface1"])
        self._draw()

    def _draw(self):
        if self._style is None:
            return
        text, bg, fg, border, bold, hover_bg = self._style
        font = self._fonts[bold]
        width = font.measure(text) + 26 + (18 if self._chevron else 0)
        self.delete("all")
        self.config(width=width)
        fill = hover_bg if self._hover and bg != C["accent"] else bg
        round_rect(self, 1, 1, width - 1, 27, 13, fill=fill, outline=border)
        self.create_text(13, 14, text=text, anchor="w", fill=fg, font=font)
        if self._chevron:
            x = width - 20
            self.create_line(x, 12, x + 4, 16, x + 8, 12, fill=fg, width=1.4)


def elide(text: str, width: int, font: tkfont.Font) -> str:
    """Text cut to `width` pixels with an ellipsis, like WPF's CharacterEllipsis."""
    if width <= 0:
        return ""
    if font.measure(text) <= width:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.measure(text[:mid].rstrip() + "…") <= width:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo].rstrip() + "…" if lo else ""


class VmList(tk.Frame):
    """The VM list, drawn like the Windows app's: column headings over rounded
    rows, each with an OS badge, name and detail line, addresses, notes,
    snapshots, a coloured status and a Connect or Start button, under
    foldable node bands. ttk.Treeview can't colour one cell or hold a button.

    Rows are ("node", name, is_open, running, total) or ("vm", iid, vm, detail).
    """

    ROW_H, BAND_H, GAP, PAD = 46, 34, 4, 10
    FIXED = {"badge": 42, "snaps": 62, "status": 86, "button": 98}
    MIN_ADDRESS, MIN_NAME, MIN_NOTES = 118, 120, 60
    HEADINGS = (("name", "NAME"), ("ip", "ADDRESS"), ("notes", "NOTES"),
                ("snaps", "SNAPS"), ("status", "STATUS"))

    def __init__(self, master, app):
        super().__init__(master, bg=C["base"])
        self.app = app
        self._rows = []
        self._sel = []            # selected iids, in the order they were picked
        self._anchor = None       # where a Shift range starts
        self._cursor = None       # the row the arrow keys move from
        self._hits = []           # (y1, y2, kind, key) per drawn row
        self._items = {}          # key -> {"bg": id, "button": (id, kind), ...}
        self._hover = None        # (kind, key)
        self._hover_heading = None
        self._cols = {}
        self._address_need = 0
        self._name_font = tkfont.Font(font=(FONT, 10, "bold"))
        self._detail_font = tkfont.Font(font=(FONT, 8))
        self._cell_font = tkfont.Font(font=(FONT, 10))
        self._mono_font = tkfont.Font(font=(MONO, 9))
        self._band_font = tkfont.Font(font=(FONT, 11, "bold"))
        self._heading_font = tkfont.Font(font=(FONT, 8, "bold"))

        self.headings = tk.Canvas(self, height=26, bg=C["base"], highlightthickness=0)
        self.canvas = tk.Canvas(self, bg=C["base"], highlightthickness=0, takefocus=1)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.headings.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.canvas.configure(yscrollcommand=self._autohide)

        c = self.canvas
        c.bind("<Configure>", lambda e: self._draw())
        c.bind("<Button-1>", self._on_click)
        c.bind("<Double-Button-1>", self._on_double)
        c.bind("<Motion>", self._on_motion)
        c.bind("<Leave>", lambda e: self._set_hover(None))
        for seq, step in (("<Button-4>", -1), ("<Button-5>", 1)):
            c.bind(seq, lambda e, s=step: self._scroll(s))
        c.bind("<MouseWheel>", lambda e: self._scroll(-1 if e.delta > 0 else 1))
        for key in ("Up", "Down", "Home", "End", "Prior", "Next"):
            c.bind(f"<{key}>", lambda e, k=key: self._on_arrow(k, False))
            c.bind(f"<Shift-{key}>", lambda e, k=key: self._on_arrow(k, True))
        self.headings.bind("<Motion>", self._on_heading_motion)
        self.headings.bind("<Leave>", lambda e: self._set_heading_hover(None))
        self.headings.bind("<Button-1>", self._on_heading_click)

    # ── Data ─────────────────────────────────────────────────────────────────
    def set_rows(self, rows, address_need):
        self._rows = rows
        self._address_need = address_need
        shown = set(self.shown())
        self._sel = [iid for iid in self._sel if iid in shown]
        if self._cursor not in shown:
            self._cursor = self._sel[-1] if self._sel else None
        if self._anchor not in shown:
            self._anchor = self._cursor
        self._draw()

    def shown(self):
        """VM iids on screen, in list order (VMs in folded nodes aren't drawn)."""
        return [row[1] for row in self._rows if row[0] == "vm"]

    def selection(self):
        return list(self._sel)

    def selection_set(self, iids):
        shown = self.shown()
        self._sel = [iid for iid in iids if iid in shown]
        if self._sel:
            self._cursor = self._anchor = self._sel[0]
        self._restyle_all()
        self.app._on_list_select()

    def see(self, iid):
        for i, (y1, y2, kind, key) in enumerate(self._hits):
            if kind == "vm" and key == iid:
                if i and self._hits[i - 1][2] == "node":
                    y1 = self._hits[i - 1][0] - 6  # a node's first VM brings its band along
                top = self.canvas.canvasy(0)
                height = self.canvas.winfo_height()
                total = max(self._hits[-1][1] + self.GAP, 1)
                if y1 < top:
                    self.canvas.yview_moveto(y1 / total)
                elif y2 > top + height:
                    self.canvas.yview_moveto((y2 - height + self.GAP) / total)
                return

    def focus_list(self):
        self.canvas.focus_set()

    def update_notes(self, iid):
        if iid in self.shown():
            self._draw()

    # ── Layout ───────────────────────────────────────────────────────────────
    def _layout(self, width):
        """x and width of each column, the Windows grid's: fixed badge, snapshots,
        status and button; name and notes share 3:2 what the address leaves.
        Too narrow for all of them, notes go first, then snapshots, then address."""
        inner = width - 2 * (self.PAD + 1)
        cols = ["badge", "name", "ip", "notes", "snaps", "status", "button"]
        for drop in (None, "notes", "snaps", "ip"):
            if drop:
                cols.remove(drop)
            need = (sum(self.FIXED.get(c, 0) for c in cols) + self.MIN_NAME
                    + (self.MIN_ADDRESS if "ip" in cols else 0)
                    + (self.MIN_NOTES if "notes" in cols else 0))
            if need <= inner:
                break
        widths = {c: self.FIXED[c] for c in cols if c in self.FIXED}
        spare = inner - sum(widths.values())
        if "ip" in cols:
            # A wider window shows more of each VM's addresses, up to all of them
            free = spare - self.MIN_ADDRESS - self.MIN_NAME - (self.MIN_NOTES if "notes" in cols else 0)
            extra = max(0, min(self._address_need + 26 - self.MIN_ADDRESS, int(free * 0.5)))
            widths["ip"] = self.MIN_ADDRESS + extra
            spare -= widths["ip"]
        if "notes" in cols:
            widths["notes"] = max(self.MIN_NOTES, spare - max(self.MIN_NAME, spare * 3 // 5))
            spare -= widths["notes"]
        widths["name"] = max(self.MIN_NAME, spare)
        x, layout = self.PAD + 1, {}
        for col in cols:
            layout[col] = (x, widths[col])
            x += widths[col]
        return layout

    # ── Drawing ──────────────────────────────────────────────────────────────
    def _draw(self):
        c = self.canvas
        c.delete("all")
        self._hits, self._items, self._hover = [], {}, None
        width = c.winfo_width()
        if width <= 1:
            return
        self._cols = self._layout(width - 1)
        y = 0
        for row in self._rows:
            if row[0] == "node":
                y += 6
                self._draw_band(y, width - 1, *row[1:])
                self._hits.append((y, y + self.BAND_H, "node", row[1]))
                y += self.BAND_H + self.GAP
            else:
                self._draw_vm(y, width - 1, row[1], row[2], row[3])
                self._hits.append((y, y + self.ROW_H, "vm", row[1]))
                y += self.ROW_H + self.GAP
        c.configure(scrollregion=(0, 0, width, max(y, 1)))
        self._restyle_all()
        self._draw_headings()

    def _draw_band(self, y, x2, node, is_open, running, total):
        c = self.canvas
        bg = round_rect(c, 0, y, x2, y + self.BAND_H, 6, fill=C["surface1"], outline="")
        bar = round_rect(c, 0, y, 10, y + self.BAND_H, 6, fill=C["accent"], outline="")
        patch = c.create_rectangle(4, y, 11, y + self.BAND_H, fill=C["surface1"], outline="")
        mid = y + self.BAND_H // 2
        if is_open:
            c.create_line(13, mid - 2, 17, mid + 2, 21, mid - 2, fill=C["text"], width=1.5)
        else:
            c.create_line(15, mid - 4, 19, mid, 15, mid + 4, fill=C["text"], width=1.5)
        c.create_text(30, mid, text=node, anchor="w", fill=C["text"], font=self._band_font)
        c.create_text(x2 - 14, mid, text=f"{running}/{total} running", anchor="e",
                      fill=C["subtext1"], font=self._detail_font)
        self._items[("node", node)] = {"bg": bg, "patch": patch, "bar": bar}

    def _draw_vm(self, y, x2, iid, vm, detail):
        c = self.canvas
        cols = self._cols
        running = vm["status"] == "running"
        mid = y + self.ROW_H // 2
        items = {"bg": round_rect(c, 0, y, x2, y + self.ROW_H, 6, fill=C["surface0"],
                                  outline=C["surface0"])}
        x, _ = cols["badge"]
        round_rect(c, x, mid - 11, x + 32, mid + 11, 4, fill=C["surface1"], outline="")
        c.create_text(x + 16, mid, text=os_badge(vm["ostype"]), fill=C["subtext1"],
                      font=(FONT, 7, "bold"))
        x, w = cols["name"]
        c.create_text(x, mid - 8, text=elide(vm["name"], w - 8, self._name_font), anchor="w",
                      fill=C["text"] if running else C["subtext0"], font=self._name_font)
        c.create_text(x, mid + 9, text=elide(detail, w - 8, self._detail_font), anchor="w",
                      fill=C["subtext0"], font=self._detail_font)
        if "ip" in cols:
            x, w = cols["ip"]
            c.create_text(x, mid, text=self.app._address_cell(vm, w - 24), anchor="w",
                          fill=C["subtext1"], font=self._mono_font)
        if "notes" in cols:
            x, w = cols["notes"]
            c.create_text(x, mid, text=elide(notes_cell(vm), w - 10, self._cell_font),
                          anchor="w", fill=C["subtext1"], font=self._cell_font)
        if "snaps" in cols:
            x, _ = cols["snaps"]
            self._camera(x, mid)
            c.create_text(x + 21, mid, text=str(vm["snaps"]), anchor="w",
                          fill=C["subtext0"], font=self._cell_font)
        x, _ = cols["status"]
        color = C["green"] if running else C["overlay0"]
        c.create_oval(x, mid - 4, x + 8, mid + 4, fill=color, outline="")
        status = vm["status"].title() or "Unknown"
        c.create_text(x + 15, mid, text=status, anchor="w", font=self._cell_font,
                      fill=C["green"] if running else C["overlay1"])
        items["button"] = self._draw_button(*cols["button"], mid, running)
        self._items[("vm", iid)] = items

    def _draw_button(self, x, w, mid, running):
        """Connect for a running VM, Start for a stopped one; returns its hit box."""
        c = self.canvas
        kind = "connect" if running else "start"
        btn = round_rect(c, x, mid - 14, x + w, mid + 14, 5,
                         fill=C["accent"] if running else C["base"],
                         outline="" if running else C["surface1"])
        fg = C["on_accent"] if running else C["text"]
        label = "Connect" if running else "Start"
        text_w = self._cell_font.measure(label)
        gx = x + (w - text_w - 20) // 2
        if running:
            c.create_rectangle(gx, mid - 5, gx + 12, mid + 3, outline=fg, width=1.4)
            c.create_line(gx + 6, mid + 3, gx + 6, mid + 6, fill=fg, width=1.4)
            c.create_line(gx + 3, mid + 6, gx + 10, mid + 6, fill=fg, width=1.4)
        else:
            c.create_polygon(gx + 2, mid - 5, gx + 2, mid + 5, gx + 10, mid,
                             outline=fg, fill="", width=1.3)
        c.create_text(gx + 20, mid, text=label, anchor="w", fill=fg, font=self._cell_font)
        return (btn, kind, x, x + w, mid - 14, mid + 14)

    def _camera(self, x, mid):
        c, color = self.canvas, C["overlay1"]
        round_rect(c, x, mid - 4, x + 14, mid + 6, 2, fill="", outline=color, width=1.2)
        c.create_line(x + 4, mid - 4, x + 5, mid - 6, x + 9, mid - 6, x + 10, mid - 4,
                      fill=color, width=1.2)
        c.create_oval(x + 4, mid - 2, x + 10, mid + 4, outline=color, width=1.2)

    def _restyle(self, kind, key):
        items = self._items.get((kind, key))
        if not items:
            return
        hovered = self._hover is not None and self._hover[:2] == (kind, key)
        c = self.canvas
        if kind == "node":
            fill = C["surface2"] if hovered else C["surface1"]
            c.itemconfig(items["bg"], fill=fill)
            c.itemconfig(items["patch"], fill=fill)
            return
        selected = key in self._sel
        c.itemconfig(items["bg"], fill=C["surface1"] if selected else C["surface0"],
                     outline=C["accent"] if selected else (C["surface2"] if hovered else C["surface0"]))
        btn, btn_kind = items["button"][:2]
        on_button = hovered and self._hover[2]
        if btn_kind == "connect":
            c.itemconfig(btn, fill=mix(C["accent"], C["text"], 0.18) if on_button else C["accent"])
        else:
            c.itemconfig(btn, fill=C["surface1"] if on_button else C["base"])

    def _restyle_all(self):
        for kind, key in self._items:
            self._restyle(kind, key)

    def _draw_headings(self):
        h = self.headings
        h.delete("all")
        self._heading_hits = []
        sort, desc = self.app._sort_col, self.app._sort_desc
        for col, label in self.HEADINGS:
            if col not in self._cols:
                continue
            x, _ = self._cols[col]
            mark = ("▼" if desc else "▲") if col == sort else "↕"
            text = f"{label} {mark}"
            tw = self._heading_font.measure(text)
            hovered = self._hover_heading == col
            if hovered:
                round_rect(h, x - 7, 2, x + tw + 7, 24, 5, fill=C["surface1"], outline="")
            color = C["accent"] if col == sort else (C["text"] if hovered else C["subtext0"])
            h.create_text(x, 13, text=text, anchor="w", fill=color, font=self._heading_font)
            self._heading_hits.append((x - 7, x + tw + 7, col))

    # ── Mouse and keys ───────────────────────────────────────────────────────
    def _hit(self, event):
        y = self.canvas.canvasy(event.y)
        for y1, y2, kind, key in self._hits:
            if y1 <= y < y2:
                items = self._items.get((kind, key), {})
                button = items.get("button")
                on_button = bool(button and button[2] <= event.x < button[3]
                                 and button[4] <= y < button[5])
                return kind, key, on_button
        return None

    def _set_hover(self, hover):
        if hover == self._hover:
            return
        old, self._hover = self._hover, hover
        for h in (old, hover):
            if h:
                self._restyle(h[0], h[1])
        on_target = hover and (hover[0] == "node" or hover[2])
        self.canvas.config(cursor="hand2" if on_target else "")

    def _on_motion(self, event):
        self._set_hover(self._hit(event))

    def _on_click(self, event):
        self.canvas.focus_set()
        hit = self._hit(event)
        if hit is None:
            return "break"
        kind, key, on_button = hit
        if kind == "node":
            self.app._toggle_node(key)
            return "break"
        ctrl, shift = event.state & 0x4, event.state & 0x1
        if on_button:
            self.selection_set([key])
            kind = self._items[("vm", key)]["button"][1]
            (self.app._launch_spice if kind == "connect" else self.app._start_vm)()
        elif ctrl:
            self._sel = [i for i in self._sel if i != key] if key in self._sel else self._sel + [key]
            self._cursor = self._anchor = key
            self._changed()
        elif shift and self._anchor:
            self._select_range(key)
        else:
            self._sel = [key]
            self._cursor = self._anchor = key
            self._changed()
        return "break"

    def _on_double(self, event):
        hit = self._hit(event)
        if hit and hit[0] == "node":
            # Tk takes a second quick click as a double-click; it still folds, as on Windows
            self.app._toggle_node(hit[1])
        elif hit and hit[0] == "vm" and not hit[2]:
            self.selection_set([hit[1]])
            self.app._launch_spice()
        return "break"

    def _select_range(self, key):
        shown = self.shown()
        a, b = shown.index(self._anchor), shown.index(key)
        self._sel = shown[min(a, b):max(a, b) + 1]
        self._cursor = key
        self._changed()

    def _on_arrow(self, key, shift):
        shown = self.shown()
        if not shown:
            return "break"
        page = max(1, self.canvas.winfo_height() // (self.ROW_H + self.GAP) - 1)
        idx = shown.index(self._cursor) if self._cursor in shown else -1
        target = {"Up": idx - 1, "Down": idx + 1, "Home": 0, "End": len(shown) - 1,
                  "Prior": idx - page, "Next": idx + page}[key]
        if idx < 0:
            target = 0
        target = shown[max(0, min(target, len(shown) - 1))]
        if shift and self._anchor in shown:
            self._select_range(target)
        else:
            self._sel = [target]
            self._cursor = self._anchor = target
            self._changed()
        self.see(target)
        return "break"

    def _changed(self):
        self._restyle_all()
        self.app._on_list_select()

    def _scroll(self, step):
        if self.scrollbar.winfo_ismapped():
            self.canvas.yview_scroll(step * 3, "units")
        return "break"

    def _autohide(self, first, last):
        # Only show the scrollbar when the list doesn't fit
        if float(first) <= 0 and float(last) >= 1:
            self.scrollbar.grid_remove()
        else:
            self.scrollbar.grid(row=1, column=1, sticky="ns", padx=(6, 0))
        self.scrollbar.set(first, last)

    def _heading_at(self, x):
        return next((col for x1, x2, col in getattr(self, "_heading_hits", []) if x1 <= x < x2), None)

    def _set_heading_hover(self, col):
        if col != self._hover_heading:
            self._hover_heading = col
            self.headings.config(cursor="hand2" if col else "")
            self._draw_headings()

    def _on_heading_motion(self, event):
        self._set_heading_hover(self._heading_at(event.x))

    def _on_heading_click(self, event):
        col = self._heading_at(event.x)
        if col:
            self.app._sort_by(col)


class ProxmoxSpiceManagerBase(tk.Tk):
    """Base class with all shared UI and logic. Subclasses must implement
    the platform-specific methods listed below."""

    # ── Platform hooks (override in subclass) ────────────────────────────────
    def _platform_save_config(self, config):
        raise NotImplementedError

    def _platform_get_secret(self, cluster_name):
        raise NotImplementedError

    def _platform_save_secret(self, cluster_name, secret):
        """None once stored, else the reason it wasn't."""
        raise NotImplementedError

    def _store_secrets(self, secrets):
        """Save {cluster name: secret}; say which couldn't be saved instead of failing silently."""
        failed = {}
        for name, secret in secrets.items():
            error = self._platform_save_secret(name, secret)
            if error:
                failed[name] = error
        if failed:
            details = "\n".join(f"{name}: {error}" for name, error in failed.items())
            messagebox.showerror(
                "Keyring",
                "The token secret couldn't be saved in the system keyring:\n\n"
                f"{details}\n\nThe cluster is saved without it, so it can't log in yet. Check "
                "that a keyring (GNOME Keyring or KWallet) is running and unlocked, then edit "
                "the cluster and enter the secret again.",
                parent=self,
            )
        return not failed

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
        self._offline_nodes = []       # named in the summary; their VMs aren't listed
        self._agent_errors = 0
        self._iid_to_vm = {}
        self._vm_filter = "all"
        self._group_by_node = self.config_data.get("group_by_node", True)
        self._sort_col = self.config_data.get("vm_sort", "vmid")
        if self._sort_col not in SORT_LABELS:
            self._sort_col = "vmid"
        self._sort_desc = self.config_data.get("vm_sort_desc", False)
        self._collapsed_nodes = set()
        self._show_ipv6 = bool(self.config_data.get("show_ipv6", False))
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
    def _post(self, callback: Callable[[], Any]) -> None:
        """Run `callback` on the Tk thread; for background threads. Dropped once the
        window is closing: Tk raises if a thread schedules work on a destroyed window."""
        if self._closing:
            return
        try:
            self.after(0, callback)
        except (RuntimeError, tk.TclError):
            pass  # closed between the check and the call

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
        ActionButton(bottom, "Add cluster", self._add_cluster, icon="plus", **nav).pack(fill="x")
        row = tk.Frame(bottom, bg=C["crust"])
        row.pack(fill="x")
        self._appearance_btn = self._build_appearance_button(row)
        self._appearance_btn.pack(side="right", padx=(4, 0))
        self._settings_btn = ActionButton(row, "Settings", self._open_settings, icon="gear", **nav)
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
        header.bind("<Configure>", lambda e: self._fit_header())
        self._header = header

        tools = tk.Frame(header, bg=C["base"])
        tools.pack(side="right", anchor="n", pady=(4, 0))
        search = tk.Frame(tools, bg=C["mantle"], highlightthickness=1,
                          highlightbackground=C["surface1"])
        search.pack(side="left", padx=(0, 8))
        LineIcon(search, "search", C["mantle"], C["overlay1"]).pack(side="left", padx=(8, 0))
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
        self._refresh_btn = ActionButton(tools, "Refresh", self._refresh_vms, icon="refresh",
                                         key="F5", pady=4)
        self._refresh_btn.pack(side="left")
        self._header_tools = tools

        titles = tk.Frame(header, bg=C["base"])
        titles.pack(side="left", fill="x", expand=True)
        self.cluster_title = tk.Label(titles, bg=C["base"], fg=C["text"],
                                      font=(FONT, 20, "bold"), anchor="w")
        self.cluster_title.pack(fill="x")
        self._set_title(self.current_cluster["name"] if self.current_cluster else "No cluster")
        self.status_label = tk.Label(
            main, text="" if self.config_data.get("clusters") else "Add a cluster to get started",
            bg=C["base"], fg=C["subtext0"], font=(FONT, 10), anchor="w",
        )
        self.status_label.pack(fill="x", pady=(0, 14), after=header)

        # Filters on the left, view options on the right; the options move to a second
        # row when both don't fit
        chips = tk.Frame(main, bg=C["base"])
        chips.pack(fill="x", pady=(0, 6))
        chips.bind("<Configure>", lambda e: self._fit_chips())
        self._chip_rows = (chips, tk.Frame(chips, bg=C["base"]), tk.Frame(chips, bg=C["base"]))
        _, filters, options = self._chip_rows
        self._chips_wrapped = None
        self._chips = {}
        for key in ("all", "running", "stopped"):
            chip = Chip(filters, lambda k=key: self._set_vm_filter(k))
            chip.pack(side="left", padx=(0, 6))
            self._chips[key] = chip
        self._ipv6_chip = Chip(options, self._toggle_ipv6)
        self._ipv6_chip.pack(side="left", padx=(0, 6))
        self._group_chip = Chip(options, self._toggle_grouping)
        self._group_chip.pack(side="left", padx=(0, 6))
        self._sort_chip = Chip(options, self._open_sort_menu, chevron=True)
        self._sort_chip.pack(side="left")

        table = tk.Frame(main, bg=C["base"])
        table.pack(fill="both", expand=True)
        self.vm_list = VmList(table, self)
        self.vm_list.pack(fill="both", expand=True)
        self._empty_label = tk.Label(table, bg=C["base"], fg=C["overlay1"], font=(FONT, 10))

    def _set_title(self, text):
        self._title_text = text
        self._fit_header()

    def _fit_header(self):
        """The search box gives up width (down to 12 characters), then Refresh its label,
        before the title does; a title that still doesn't fit is cut with an ellipsis."""
        header = getattr(self, "_header", None)
        if header is None or not header.winfo_exists():
            return
        title_font = tkfont.Font(font=self.cluster_title.cget("font"))
        entry_font = tkfont.Font(font=self.search_entry.cget("font"))
        width = header.winfo_width()
        if width <= 1:  # not laid out yet; <Configure> calls again
            self.cluster_title.config(text=self._title_text)
            return
        char = entry_font.measure("0")
        label = self._refresh_btn.label
        label_width = label.winfo_reqwidth() if label.winfo_manager() else 0
        other = (self._header_tools.winfo_reqwidth() - label_width
                 - int(self.search_entry.cget("width")) * char)
        title = title_font.measure(self._title_text)
        full_label = self._refresh_btn._font.measure("Refresh") + 4
        show_label = width - other - full_label - 12 * char - title - 16 >= 0
        if show_label != bool(label.winfo_manager()):
            if show_label:
                label.pack(side="left", fill="x", expand=True)
            else:
                label.pack_forget()
        if show_label:
            other += full_label
        spare = width - other - title - 16
        fit = max(12, min(20, spare // char))
        if fit != int(self.search_entry.cget("width")):
            self.search_entry.config(width=fit)
        room = width - other - fit * char - 16
        self.cluster_title.config(text=elide(self._title_text, room, title_font))

    def _fit_chips(self):
        row, filters, options = self._chip_rows
        if not row.winfo_exists():
            return
        wrap = filters.winfo_reqwidth() + options.winfo_reqwidth() + 12 > row.winfo_width()
        if wrap == self._chips_wrapped:
            return
        self._chips_wrapped = wrap
        filters.pack_forget()
        options.pack_forget()
        if wrap:
            filters.pack(side="top", anchor="w")
            options.pack(side="top", anchor="w", pady=(6, 0))
        else:
            filters.pack(side="left")
            options.pack(side="right")

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
        if hasattr(self, "vm_list"):
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
            chip.set(f"{labels[key]}  {counts[key]}",
                     bg=C["accent"] if on else C["surface0"],
                     fg=C["on_accent"] if on else C["text"],
                     border=C["accent"] if on else C["surface1"], bold=on)
        for chip, label, on in ((self._group_chip, "Group by node", self._group_by_node),
                                (self._ipv6_chip, "IPv6", self._show_ipv6)):
            chip.set(f"✓ {label}" if on else label,
                     bg=C["surface1"] if on else C["surface0"], fg=C["text"],
                     border=C["surface2"] if on else C["surface1"],
                     hover_bg=C["surface2"] if on else C["surface1"])
        self._sort_chip.set(f"Sort: {SORT_LABELS[self._sort_col]} {'▼' if self._sort_desc else '▲'}",
                            bg=C["surface0"], fg=C["text"], border=C["surface1"])
        self._chips_wrapped = None  # labels changed width: decide again
        self.after_idle(self._fit_chips)

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
        """Redraw the list from self._vms, grouped by node, keeping the selection."""
        if keep is None:
            keep = {vm["vmid"] for vm in self._get_selected_vms()}
        query = self.search_var.get().strip().lower()
        visible = sorted((vm for vm in self._vms if self._vm_matches(vm, query)),
                         key=lambda v: vm_sort_key(v, self._sort_col, self._show_ipv6), reverse=self._sort_desc)
        self._iid_to_vm = {f"vm:{vm['vmid']}": vm for vm in visible}
        rows = []
        if self._group_by_node:
            for node in sorted({vm["node"] for vm in visible}):
                vms = [vm for vm in visible if vm["node"] == node]
                running = sum(1 for vm in vms if vm["status"] == "running")
                is_open = node not in self._collapsed_nodes
                rows.append(("node", node, is_open, running, len(vms)))
                if is_open:
                    rows += [self._vm_row(vm) for vm in vms]
        else:
            rows = [self._vm_row(vm) for vm in visible]
        measure = self.vm_list._mono_font.measure
        address_need = max((measure(", ".join(ip for _, ip in vm_ips(vm, self._show_ipv6)))
                            for vm in visible), default=0)
        self.vm_list.set_rows(rows, address_need)
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

        # A VM inside a folded node stays unselected, and keys don't act on a
        # VM that isn't on screen
        shown = self._shown_vm_iids()
        selection = [f"vm:{vmid}" for vmid in keep if f"vm:{vmid}" in shown]
        if not selection and shown:
            selection = shown[:1]
        self.vm_list.selection_set(selection)
        if selection:
            self.vm_list.see(selection[0])

    def _vm_row(self, vm):
        # Second line of a row: "101 · desktops", led by the node when ungrouped
        parts = ("" if self._group_by_node else vm["node"], str(vm["vmid"]), vm["pool"])
        return ("vm", f"vm:{vm['vmid']}", vm, " · ".join(p for p in parts if p))

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
        self._bind_wheel(frame, self._insp_wheel)

    def _address_cell(self, vm, width):
        """Every address that fits in `width` pixels, "+N" for the rest, or why there is none."""
        ips = [ip for _, ip in vm_ips(vm, self._show_ipv6)]
        if not ips:
            return vm["ip_note"] or "—"
        return fit_addresses(ips, width, self.vm_list._mono_font.measure)

    def _open_sort_menu(self):
        # Picking the current key again reverses the order, like a column heading
        mark = "▼" if self._sort_desc else "▲"
        entries = [(f"✓  {label}  {mark}" if key == self._sort_col else f"     {label}",
                    lambda k=key: self._sort_by(k)) for key, label in SORT_LABELS.items()]
        self._show_menu(self._sort_chip, entries, above=False)

    def _sort_by(self, column):
        """Heading click or Sort menu: sort by that column; picking it again reverses."""
        if column == self._sort_col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col, self._sort_desc = column, False
        self.config_data["vm_sort"] = self._sort_col
        self.config_data["vm_sort_desc"] = self._sort_desc
        self._save_config()
        self._render_vms()

    def _toggle_grouping(self):
        self._group_by_node = not self._group_by_node
        self.config_data["group_by_node"] = self._group_by_node
        self._save_config()
        self._render_vms()

    def _toggle_node(self, node):
        """A click on a node band folds or unfolds it and leaves the selection alone."""
        if node in self._collapsed_nodes:
            self._collapsed_nodes.discard(node)
        else:
            self._collapsed_nodes.add(node)
        self._render_vms()

    def _shown_vm_iids(self):
        """VM rows on screen, in list order: not inside a folded node."""
        return self.vm_list.shown()

    def _focus_tree(self):
        shown = self._shown_vm_iids()
        if not self.vm_list.selection() and shown:
            self.vm_list.selection_set(shown[:1])
        self.vm_list.focus_list()

    def _select_all_vms(self):
        shown = self._shown_vm_iids()
        if shown:
            self.vm_list.selection_set(shown)

    # ── Selection ────────────────────────────────────────────────────────────
    def _get_selected_vms(self):
        if not hasattr(self, "vm_list"):
            return []
        return [self._iid_to_vm[iid] for iid in self.vm_list.selection()
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

    def _on_list_select(self):
        self._update_inspector()

    # ── Inspector ────────────────────────────────────────────────────────────
    def _build_inspector(self, parent):
        bg = C["mantle"]
        self._insp_empty = tk.Label(
            parent, text="Select a VM to see its\ndetails and actions.",
            bg=bg, fg=C["overlay1"], font=(FONT, 10), justify="center",
        )
        insp = tk.Frame(parent, bg=bg)
        self._insp = insp
        ActionButton(
            insp, "Force stop", self._stop_vm, icon="stop", key="Ctrl+.", fg=C["red"], pady=5,
            elide=True,
        ).pack(side="bottom", fill="x", padx=20, pady=(8, 18))
        # Everything above Force stop scrolls when the window is too short for it
        scroll = tk.Frame(insp, bg=bg)
        scroll.pack(fill="both", expand=True, pady=(22, 0))
        canvas = tk.Canvas(scroll, bg=bg, highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(scroll, orient="vertical", command=canvas.yview)
        canvas.pack(side="left", fill="both", expand=True)
        body = tk.Frame(canvas, bg=bg)
        window = canvas.create_window(20, 0, window=body, anchor="nw")

        def fit(event=None):
            scrolls = body.winfo_reqheight() > canvas.winfo_height()
            if scrolls != bar.winfo_ismapped():
                if scrolls:
                    bar.pack(side="right", fill="y", before=canvas)
                else:
                    bar.pack_forget()
                    canvas.yview_moveto(0)
            # The scrollbar takes the place of the right-hand padding
            canvas.itemconfig(window, width=max(canvas.winfo_width() - (22 if scrolls else 40), 1))
            canvas.configure(scrollregion=(0, 0, 1, body.winfo_reqheight()))

        def wheel(step):
            if bar.winfo_ismapped():
                canvas.yview_scroll(step * 3, "units")
            return "break"

        canvas.configure(yscrollcommand=bar.set, yscrollincrement=10)
        canvas.bind("<Configure>", fit)
        body.bind("<Configure>", fit)
        self._insp_wheel = wheel

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
            body, "Open SPICE console", self._launch_spice, icon="monitor", key="Enter",
            bg=C["accent"], fg=C["on_accent"], border=C["accent"],
            hover_bg=mix(C["accent"], C["mantle"], 0.15), bold=True, pady=8, padx=8, elide=True,
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
            ("start", "play", "Start", "S", self._start_vm),
            ("shutdown", "power", "Shut down", "Shift+S", self._shutdown_vm),
            ("reboot", "refresh", "Reboot", "R", self._reboot_vm),
            ("snapshots", "camera", "Snapshots", "P", self._show_snapshots),
            ("rollback", "undo", "Roll back to latest snapshot", "", self._quick_rollback),
        ):
            btn = ActionButton(body, text, command, icon=icon, key=hint, pady=5, elide=True)
            btn.pack(fill="x", pady=(0, 5))
            self._action_btns[key] = btn

        self._bind_wheel(insp, wheel)

    def _bind_wheel(self, widget, wheel):
        """Wheel scrolling over a widget and everything inside it."""
        for seq, step in (("<Button-4>", -1), ("<Button-5>", 1)):
            widget.bind(seq, lambda e, s=step: wheel(s))
        widget.bind("<MouseWheel>", lambda e: wheel(-1 if e.delta > 0 else 1))
        for child in widget.winfo_children():
            self._bind_wheel(child, wheel)

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
        if hasattr(self, "vm_list"):
            self.vm_list.update_notes(f"vm:{vm['vmid']}")

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
                self._store_secrets({dlg.result["name"]: dlg._pending_secret})
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
                self._store_secrets({dlg.result["name"]: dlg._pending_secret})
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
                self._set_title("No cluster")
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
        except (OSError, ValueError, TypeError) as e:
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
        except (OSError, ValueError) as e:
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
        need_secret, secrets = [], {}
        for cluster in new_clusters:
            secret = cluster.pop("token_secret", None)
            enc = cluster.pop("token_secret_enc", None)
            if not secret and enc and not enc.startswith(DPAPI_PREFIX):
                secret = enc  # Windows exports before 3.0.0 put the plaintext secret here
            if cluster["name"] in existing:
                cluster["name"] = f"{cluster['name']} (Imported)"
            self.config_data.setdefault("clusters", []).append(cluster)
            if secret:
                secrets[cluster["name"]] = secret
            elif cluster.get("auth_method") == "token":
                need_secret.append(cluster["name"])

        self._save_config()
        self._populate_clusters()
        messagebox.showinfo("Imported", f"Imported {len(new_clusters)} cluster(s).", parent=self)
        self._store_secrets(secrets)
        if need_secret:
            # An encrypted Windows secret (DPAPI) only opens for that Windows user
            messagebox.showwarning(
                "Import",
                "The file has no usable token secret for:\n\n" + "\n".join(need_secret)
                + "\n\nEdit each of them and enter the secret again.",
                parent=self,
            )

    # ── Auth ─────────────────────────────────────────────────────────────────
    def _get_auth(self, cluster):
        name = cluster["name"]
        pin = cluster.get("tls_fingerprint")

        if cluster["auth_method"] == "token":
            token_id = cluster.get("token_id")
            token_secret = self._platform_get_secret(name)
            if token_id and token_secret:
                return {"token_id": token_id, "token_secret": token_secret,
                        "tls_fingerprint": pin}
            messagebox.showerror(
                "Auth Error",
                "Token secret not found or could not be decrypted.",
                parent=self,
            )
            return None

        cached = self.auth_cache.get(name)
        if cached:
            age = time.monotonic() - cached["issued"]
            if age < TICKET_RENEW_AFTER:
                return cached
            if age < TICKET_MAX_AGE:
                renewed = self._password_login(cluster, cached["ticket"])
                if renewed:
                    DebugLogger.log(f"[Auth] Ticket for {name} renewed")
                    return renewed
            del self.auth_cache[name]

        prompt = PasswordPrompt(
            self, cluster.get("username", "root@pam"), cluster["host"]
        )
        if not prompt.result:
            return None
        auth = self._password_login(cluster, prompt.result)
        if auth:
            return auth
        messagebox.showerror("Auth Failed", "Could not authenticate.", parent=self)
        return None

    def _password_login(self, cluster, password):
        """A ticket for the cluster's user, cached, from a password or the current ticket; or None."""
        while True:
            try:
                auth = authenticate_password(
                    cluster["host"], cluster.get("username", "root@pam"), password,
                    pin=cluster.get("tls_fingerprint"),
                )
                break
            except TlsUntrusted as e:
                # Nothing was sent yet: confirm the certificate, then log in
                if not self._trust_certificate(cluster, e.fingerprint, e.changed):
                    return None
        if not auth:
            return None
        auth["tls_fingerprint"] = cluster.get("tls_fingerprint")
        auth["issued"] = time.monotonic()
        self.auth_cache[cluster["name"]] = auth
        return auth

    def _trust_certificate(self, cluster, fingerprint, changed):
        """Show a certificate this system doesn't trust and pin it on yes (like SSH's
        host keys). Called before any token or password was sent to that server."""
        host = urllib.parse.urlparse(cluster["host"]).hostname
        where = "Compare it with Proxmox: Node → System → Certificates → Fingerprint."
        if changed:
            ok = messagebox.askyesno(
                "Certificate changed",
                f"The certificate of {cluster['name']} ({host}) is not the one you trusted.\n\n"
                "That is expected after the certificate is renewed. It is also what "
                "someone intercepting the connection would look like.\n\n"
                f"New SHA-256 fingerprint:\n{fingerprint}\n\n{where}\n\n"
                "Trust the new certificate?",
                icon="warning", default="no", parent=self,
            )
        else:
            ok = messagebox.askyesno(
                "Trust this certificate?",
                f"{host} presents a certificate this computer doesn't trust. "
                "Proxmox's own certificate is self-signed, so this is normal the first time.\n\n"
                f"SHA-256 fingerprint:\n{fingerprint}\n\n{where}\n\n"
                f"Trust it for {cluster['name']}? Nothing has been sent to the server yet.",
                parent=self,
            )
        if not ok:
            return False
        cluster["tls_fingerprint"] = fingerprint
        cluster.pop("skip_tls_verify", None)
        if cluster["name"] in self.auth_cache:
            self.auth_cache[cluster["name"]]["tls_fingerprint"] = fingerprint
        self._save_config()
        return True

    def _certificate_refused(self, cluster, data):
        """A refresh stopped at an untrusted certificate: ask, then reload or stay offline."""
        if self.current_cluster is not cluster or self._closing:
            return
        if self._trust_certificate(cluster, data["tls_untrusted"], data["tls_changed"]):
            self._refresh_vms()
        else:
            self._set_cluster_offline(cluster, "Certificate not trusted")

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
        offline = self._offline_nodes
        if offline:
            parts.append(f"1 node offline ({offline[0]})" if len(offline) == 1
                         else f"{len(offline)} nodes offline ({', '.join(offline)})")
        if self._agent_errors:
            parts.append(f"{self._agent_errors} agent error(s)")
        self.status_label.config(text=" · ".join(parts), fg=C["subtext0"])

    def _set_cluster_offline(self, cluster, message):
        self._cluster_status[cluster["name"]] = (False, None)
        self._populate_clusters()
        self.status_label.config(text=message, fg=C["red"])

    def _refresh_vms(self):
        if not self.current_cluster:
            return
        cluster = self.current_cluster
        self._set_title(cluster["name"])
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

        def get(endpoint, timeout=15):
            return api_request(cluster["host"], endpoint, auth=auth, timeout=timeout)

        def fetch():
            with ThreadPoolExecutor(max_workers=16) as pool:
                resources, nodes = pool.map(get, ("/api2/json/cluster/resources?type=vm",
                                                  "/api2/json/nodes"))
                untrusted = next((r for r in (resources, nodes) if "tls_untrusted" in r), None)
                if untrusted:
                    self._post(lambda: self._certificate_refused(cluster, untrusted))
                    return
                error = resources.get("error") or nodes.get("error")
                if error:
                    self._post(lambda: self._set_cluster_offline(cluster, f"Error: {error}"))
                    return
                # A request for a VM on an offline node waits seconds for Proxmox to
                # give up (595), so those VMs are skipped and the node is named instead
                online = {n.get("node") for n in nodes.get("data", []) if n.get("status") == "online"}
                offline = sorted(n.get("node", "") for n in nodes.get("data", [])
                                 if n.get("node") not in online)
                qemu = [v for v in resources.get("data", [])
                        if v.get("type") == "qemu" and v.get("node") in online]
                DebugLogger.log(f"[Refresh] {len(qemu)} VMs on {len(online)} online nodes"
                                + (f"; offline: {', '.join(offline)}" if offline else ""))

                base = [f"/api2/json/nodes/{v.get('node')}/qemu/{v.get('vmid')}" for v in qemu]
                configs = list(pool.map(get, [f"{b}/config" for b in base]))
                spice = []
                for vm, path, config in zip(qemu, base, configs):
                    cfg = config.get("data", {}) if "error" not in config else None
                    vga = str((cfg or {}).get("vga", "")).lower()
                    if cfg is None or not ("qxl" in vga or "spice" in vga):
                        continue
                    vm["_path"] = path
                    vm["_ostype"] = str(cfg.get("ostype", ""))
                    vm["_has_agent"] = agent_has_agent(cfg.get("agent"))
                    vm["_description"] = str(cfg.get("description", ""))
                    spice.append(vm)
                snaps = pool.map(get, [f"{vm['_path']}/snapshot" for vm in spice])
                for vm, snap_data in zip(spice, snaps):
                    vm["_snap_count"] = len([s for s in snap_data.get("data", [])
                                             if s.get("name") != "current"]) if "error" not in snap_data else 0
                    vm["_ips"], vm["_ip_note"] = [], "" if vm["_has_agent"] else "no agent"
            self._post(lambda: update_ui(spice, len(qemu), offline))

        def update_ui(spice_vms, qemu_count, offline):
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
                "_path": vm["_path"], "_has_agent": vm["_has_agent"],
            } for vm in spice_vms]
            self._offline_nodes = offline
            self._agent_errors = 0
            self._loaded_cluster = cluster["name"]
            self._cluster_status[cluster["name"]] = (True, len(self._vms))
            self._populate_clusters()
            self._render_vms(keep)
            DebugLogger.log(f"[Refresh] {len(spice_vms)} SPICE VMs found "
                            f"(of {qemu_count} QEMU VMs)")
            self._show_summary()
            self._fetch_addresses(cluster, auth, self._vms)

        threading.Thread(target=fetch, daemon=True).start()

    def _fetch_addresses(self, cluster, auth, vms):
        """Guest-agent addresses, after the list is on screen; each row fills in as its answer arrives."""
        wanted = [vm for vm in vms if vm["status"] == "running" and vm["_has_agent"]]
        if not wanted:
            return

        def one(vm):
            data = api_request(cluster["host"], f"{vm['_path']}/agent/network-get-interfaces",
                               auth=auth, timeout=3)
            self._post(lambda: show(vm, data))

        def show(vm, data):
            if self._vms is not vms or self._closing:
                return  # a newer refresh replaced these rows
            if "error" in data:
                vm["ip_note"] = "agent error"
                self._agent_errors += 1
                self._show_summary()
            else:
                vm["ips"] = agent_ips(data.get("data", {}).get("result"))
            self._render_vms()

        def run():
            with ThreadPoolExecutor(max_workers=16) as pool:
                list(pool.map(one, wanted))

        threading.Thread(target=run, daemon=True).start()

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

            if "error" in data or not isinstance(spice_data, dict) or not spice_data.get("type"):
                err = data.get("error", "Unknown Error")
                self._post(lambda: (
                    self.status_label.config(text="Connection failed", fg=C["red"]),
                    messagebox.showerror("SPICE Error", err, parent=self),
                ))
                return

            viewer = self._platform_find_viewer()
            if not viewer:
                self._post(lambda: (
                    self.status_label.config(text="remote-viewer not found", fg=C["red"]),
                    messagebox.showerror(
                        "Missing", "remote-viewer not found.\nCheck prerequisites.",
                        parent=self,
                    ),
                ))
                return

            vv_path = None
            try:
                vv_path = write_vv_file(spice_data)
                self._platform_set_vv_permissions(vv_path)
                self._platform_launch_viewer(viewer, vv_path)

                self._post(lambda: self.status_label.config(
                    text=f"Connected to {vm['name']} ({vm['vmid']})", fg=C["green"]
                ))
            except (OSError, ValueError, subprocess.SubprocessError) as e:
                if vv_path:
                    try:
                        os.unlink(vv_path)
                    except OSError:
                        pass
                # Bind now: Python unbinds `e` when the except block ends,
                # before the deferred callback runs.
                err = str(e)
                self._post(lambda: messagebox.showerror(
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

        def do_action():
            errors, tasks = [], []
            for vm in valid:
                data = api_request(
                    cluster["host"],
                    f"/api2/json/nodes/{vm['node']}/qemu/{vm['vmid']}/status/{action}",
                    method="POST", auth=auth,
                )
                err = data.get("error")
                if err and "already" not in str(err).lower():
                    errors.append(f"{vm['name']}: {err}")
                elif not err:
                    tasks.append((vm, data.get("data")))
            # Refresh once Proxmox has finished, not after a guess
            for vm, upid in tasks:
                err = wait_for_task(cluster["host"], auth, upid)
                if err:
                    errors.append(f"{vm['name']}: {err}")

            def on_done():
                if errors:
                    self.status_label.config(text="Some actions failed", fg=C["red"])
                    messagebox.showerror("Errors", "\n".join(errors), parent=self)
                else:
                    self.status_label.config(
                        text=f"{action_label} sent to {len(valid)} VM(s)", fg=C["green"]
                    )

            self._post(on_done)
            self._post(self._refresh_vms)

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
                self._post(lambda: messagebox.showerror("Error", data["error"], parent=self))
                return
            snaps = [s for s in data.get("data", []) if s.get("name") != "current"]
            if not snaps:
                self._post(lambda: messagebox.showinfo("No Snapshots", "No snapshots found.", parent=self))
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
                    error = rb.get("error") or wait_for_task(cluster["host"], saved_auth, rb.get("data"))
                    self._post(lambda: done(error))

                def done(error):
                    self._refresh_vms()
                    if error:
                        self.status_label.config(text="Rollback failed", fg=C["red"])
                        messagebox.showerror("Rollback Failed", error, parent=self)
                    else:
                        self.status_label.config(text=f"Rolled back to '{snap_name}'", fg=C["green"])

                threading.Thread(target=do_rb, daemon=True).start()

            self._post(confirm)

        threading.Thread(target=fetch, daemon=True).start()

    # ── Snapshots ────────────────────────────────────────────────────────────
    def _show_snapshots(self):
        vm = self._get_selected_vm()
        if not vm:
            return
        auth = self._get_auth(self.current_cluster)
        if not auth:
            return
        SnapshotDialog(self, vm, self.current_cluster, auth, on_change=self._refresh_vms)


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
def _can_sudo() -> bool:
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
    except (OSError, subprocess.SubprocessError):
        return False


def _elevate_prefix() -> str:
    return "sudo" if _can_sudo() else "su -c"


def detect_pkg_manager() -> str | None:
    if shutil.which("dnf"):
        return "dnf"
    if shutil.which("apt"):
        return "apt"
    return None


def get_install_cmd(dep_info: dict[str, str], fallback_name: str) -> str:
    mgr = detect_pkg_manager()
    if not mgr:
        return f"# Install '{fallback_name}' using your package manager"
    pkg = dep_info.get(f"pkg_{mgr}", fallback_name)
    elev = _elevate_prefix()
    if elev == "sudo":
        return f"sudo {mgr} install {pkg}"
    return f"su -c '{mgr} install {pkg}'"


def check_deps() -> tuple[bool, dict[str, bool]]:
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
def save_secret(cluster_name: str, secret: str) -> str | None:
    """None once stored, else why not: the keyring's error (it never contains the secret)."""
    try:
        import keyring
        keyring.set_password(APP_ID, cluster_name, secret)
        return None
    # Broad on purpose: keyring backends (SecretService, D-Bus, KWallet) raise their
    # own exception types, and a missing keyring module is ImportError
    except Exception as e:
        print(f"[debug] save_secret failed: {type(e).__name__}", file=sys.stderr)
        return f"{type(e).__name__}: {e}" if str(e) else type(e).__name__


def get_secret(cluster_name: str) -> str | None:
    try:
        import keyring
        return keyring.get_password(APP_ID, cluster_name)
    except Exception as e:  # any keyring backend's error, as in save_secret
        print(f"[debug] get_secret failed: {type(e).__name__}", file=sys.stderr)
        return None


def delete_secret(cluster_name: str) -> None:
    try:
        import keyring
        keyring.delete_password(APP_ID, cluster_name)
    except Exception as e:  # any keyring backend's error, as in save_secret
        print(f"[debug] delete_secret failed: {type(e).__name__}", file=sys.stderr)


def save_config(config: Json) -> None:
    config["version"] = APP_VERSION
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, 0o700)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    os.chmod(CONFIG_FILE, 0o600)


def migrate_secrets(config: Json) -> None:
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
                except Exception as e:  # any keyring backend's error, as in save_secret
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
                except (OSError, ValueError):
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
        except tk.TclError:
            pass

    def _platform_save_config(self, config):
        save_config(config)

    def _platform_get_secret(self, cluster_name):
        return get_secret(cluster_name)

    def _platform_save_secret(self, cluster_name, secret):
        return save_secret(cluster_name, secret)

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
        """A menu launcher that opens the selected VM's console (--connect), not the manager."""
        vm = self._get_selected_vm()
        if not vm:
            return
        cluster = self.current_cluster["name"]
        desktop_dir = Path.home() / ".local" / "share" / "applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)
        slug = re.sub(r"[^A-Za-z0-9]+", "-", cluster).strip("-").lower() or "cluster"
        filepath = desktop_dir / f"spice-{slug}-vm{vm['vmid']}.desktop"
        command = [*launcher_command(), "--connect", cluster, str(vm["vmid"])]
        name = desktop_value(f"{vm['name']} (VM {vm['vmid']})")
        comment = desktop_value(f"SPICE console on {cluster}")
        content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={name}\n"
            f"Comment={comment}\n"
            f"Exec={' '.join(desktop_exec_arg(arg) for arg in command)}\n"
            "Icon=computer\n"
            "Terminal=false\n"
            "Categories=System;\n"
        )
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(filepath, 0o755)
        messagebox.showinfo(
            "Exported", f"Desktop launcher saved:\n{filepath}\n\n"
            "It opens this VM's console directly, starting the VM first if you agree.",
            parent=self,
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
            except OSError as e:
                messagebox.showerror(
                    "Icon Error", f"Could not copy icon:\n{e}", parent=self
                )
                return

        current_script = Path(os.path.abspath(__file__))
        try:
            if current_script.resolve() != installed_script.resolve():
                shutil.copy2(current_script, installed_script)
            os.chmod(installed_script, 0o755)
        except OSError as e:
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
        except OSError as e:
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


# ─── Launchers: --connect ────────────────────────────────────────────────────
def launcher_command() -> list[str]:
    """How to run this app again: the frozen binary, or this interpreter and this script."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, str(Path(__file__).resolve())]


def desktop_value(text: str) -> str:
    """A .desktop string value: one line, backslashes escaped."""
    return " ".join(text.split()).replace("\\", "\\\\")


def desktop_exec_arg(arg: str) -> str:
    """One Exec argument, quoted by the Desktop Entry rules: \\ " ` $ escaped inside the
    quotes, then the general string escape for backslashes, and % doubled."""
    inner = re.sub(r'([\\"`$])', r"\\\1", arg)
    return f'"{inner}"'.replace("\\", "\\\\").replace("%", "%%")


class _LaunchStop(Exception):
    """Ends --connect: args[0] is the message to show, or None when the user cancelled."""


_UNTRUSTED_FOR_LAUNCHER = (
    "The server's certificate isn't the one confirmed in Proxmox SPICE Manager. "
    "Open the manager and refresh the cluster to check it.")


def _launcher_auth(root: tk.Tk, cluster: Json) -> Json:
    """Log in as the manager does: the keyring token, or a password prompt."""
    name, host, pin = cluster["name"], cluster["host"], cluster.get("tls_fingerprint")
    if cluster.get("auth_method") == "token":
        secret = get_secret(name)
        if not secret:
            raise _LaunchStop(f"The token secret for {name} isn't in the keyring. "
                              "Edit the cluster in the manager and enter it again.")
        return {"token_id": cluster.get("token_id"), "token_secret": secret, "tls_fingerprint": pin}
    user = cluster.get("username", "root@pam")
    prompt = PasswordPrompt(root, user, host)
    if not prompt.result:
        raise _LaunchStop(None)
    try:
        auth = authenticate_password(host, user, prompt.result, pin=pin)
    except TlsUntrusted:
        raise _LaunchStop(_UNTRUSTED_FOR_LAUNCHER) from None
    if not auth:
        raise _LaunchStop("Could not authenticate.")
    auth["tls_fingerprint"] = pin
    return auth


def _launcher_start(root: tk.Tk, call: Callable[..., Json], name: str, base: str) -> None:
    """Offer to start a stopped VM, then wait up to a minute for it to run."""
    if not messagebox.askyesno("Start VM?", f"{name} isn't running. Start it and open its console?",
                               parent=root):
        raise _LaunchStop(None)
    started = call(f"{base}/status/start", "POST")
    if "error" in started:
        raise _LaunchStop(f"Couldn't start {name}: {started['error']}")
    for _ in range(30):
        if call(f"{base}/status/current").get("data", {}).get("status") == "running":
            return
        time.sleep(2)
    raise _LaunchStop(f"{name} didn't start within a minute.")


def _launcher_open(root: tk.Tk, config: Json, cluster_name: str, vmid: int) -> None:
    cluster = next((c for c in config.get("clusters", []) if c.get("name") == cluster_name), None)
    if cluster is None:
        raise _LaunchStop(f"There is no cluster named \"{cluster_name}\" any more. It may have been "
                          "renamed or removed in the manager; export the launcher again.")
    auth = _launcher_auth(root, cluster)

    def call(endpoint, method="GET"):
        return api_request(cluster["host"], endpoint, method=method, auth=auth)

    data = call("/api2/json/cluster/resources?type=vm")
    if "tls_untrusted" in data:
        raise _LaunchStop(_UNTRUSTED_FOR_LAUNCHER)
    if "error" in data:
        raise _LaunchStop(f"Couldn't reach {cluster_name}: {data['error']}")
    vm = next((v for v in data.get("data", []) if v.get("type") == "qemu" and v.get("vmid") == vmid), None)
    if vm is None:
        raise _LaunchStop(f"VM {vmid} isn't on {cluster_name} any more.")
    name, base = vm.get("name", str(vmid)), f"/api2/json/nodes/{vm['node']}/qemu/{vmid}"
    if vm.get("status") != "running":
        _launcher_start(root, call, name, base)
    spice = call(f"{base}/spiceproxy", "POST")
    if "error" in spice or not (spice.get("data") or {}).get("type"):
        raise _LaunchStop(f"Couldn't open the console of {name}: {spice.get('error', 'no SPICE answer')}")
    viewer = shutil.which("remote-viewer")
    if not viewer:
        raise _LaunchStop("remote-viewer isn't installed (package virt-viewer).")
    # The viewer outlives this process; it deletes the .vv file once read
    subprocess.Popen([viewer, write_vv_file(spice["data"])], start_new_session=True)


def quick_connect(cluster_name: str, vmid: int) -> int:
    """--connect CLUSTER VMID: open one VM's SPICE console without the manager window, as
    the exported .desktop launchers do. Logs in like the manager (keyring token or a
    password prompt, pinned certificate), offers to start a stopped VM. Returns an exit code."""
    root = tk.Tk()
    root.withdraw()
    config = load_config(CONFIG_FILE)
    apply_theme(config.get("theme", DEFAULT_THEME), config.get("accent", DEFAULT_ACCENT))
    try:
        _launcher_open(root, config, cluster_name, vmid)
        return 0
    except _LaunchStop as stop:
        if stop.args[0]:
            messagebox.showerror("Proxmox SPICE Manager", stop.args[0], parent=root)
        return 1
    finally:
        root.destroy()


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--connect" and sys.argv[3].isdigit():
        # A launcher opening one console; it doesn't take the manager's single-instance lock
        sys.exit(quick_connect(sys.argv[2], int(sys.argv[3])))
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
