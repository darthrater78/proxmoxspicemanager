#!/usr/bin/env python3
"""
Proxmox SPICE Connection Manager
A GUI app to manage and launch SPICE console sessions to Proxmox VMs.
Connections are saved to ~/.config/proxmox-spice/connections.json

Dependencies: python3-tkinter, python3-keyring, remote-viewer (virt-viewer)

Install on Fedora:  sudo dnf install python3-tkinter python3-keyring virt-viewer
Install on Debian:  sudo apt install python3-tk python3-keyring virt-viewer

VERSION 2.2.0
"""

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import threading
import ssl
import urllib.request
import urllib.parse
import urllib.error
import importlib
import copy
from datetime import datetime
from pathlib import Path

# Verify absolute GUI requirement first.
try:
    import tkinter as tk
    from tkinter import ttk, messagebox, filedialog
except ModuleNotFoundError:
    import sys

    is_debian = shutil.which("apt") is not None
    is_fedora = shutil.which("dnf") is not None
    pkg_name = "python3-tk" if is_debian else "python3-tkinter"

    if sys.stdout.isatty():
        _groups = subprocess.run(["groups"], capture_output=True, text=True).stdout
        _has_sudo = "sudo" in _groups or "wheel" in _groups

        print(f"\n  Proxmox SPICE Manager requires {pkg_name}.\n")
        if is_fedora:
            print(f"  Install it with:  sudo dnf install {pkg_name}\n")
        elif is_debian:
            if _has_sudo:
                print(f"  Install it with:  sudo apt install {pkg_name}\n")
            else:
                print(f"  Install it with:  su -c 'apt install {pkg_name}'\n")
        else:
            print(f"  Install the {pkg_name} package for your distribution.\n")
    else:
        _terminals = [
            ["konsole", "-e"], ["gnome-terminal", "--"],
            ["xfce4-terminal", "-e"], ["x-terminal-emulator", "-e"], ["xterm", "-e"],
        ]
        _msg = (
            "echo ''; "
            f"echo '  Proxmox SPICE Manager requires {pkg_name}.'; "
            "echo '  Run this script from a terminal to see install instructions.'; "
            "echo ''; echo '  Press Enter to close...'; read"
        )
        for _term_cmd in _terminals:
            if shutil.which(_term_cmd[0]):
                try:
                    subprocess.Popen(_term_cmd + ["bash", "-c", _msg]).wait()
                    break
                except Exception:
                    continue
    sys.exit(1)

CONFIG_DIR = Path.home() / ".config" / "proxmox-spice"
CONFIG_FILE = CONFIG_DIR / "connections.json"
APP_ID = "proxmox-spice-manager"
APP_VERSION = "2.2.0"

# Resolve icon path — works both from source and when frozen by PyInstaller
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


# ─── Config & Keyring Persistence ────────────────────────────────────────────
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
    """Save configuration to disk with strict permissions (600)."""
    config["version"] = APP_VERSION
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CONFIG_DIR, 0o700)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
    os.chmod(CONFIG_FILE, 0o600)


def save_secret(cluster_name, secret):
    """Save a secret to the OS keyring. Returns True on success."""
    try:
        import keyring
        keyring.set_password(APP_ID, cluster_name, secret)
        return True
    except Exception as e:
        import sys
        print(f"[debug] save_secret failed: {type(e).__name__}", file=sys.stderr)
        return False


def get_secret(cluster_name):
    """Retrieve a secret from the OS keyring."""
    try:
        import keyring
        return keyring.get_password(APP_ID, cluster_name)
    except Exception as e:
        import sys
        print(f"[debug] get_secret failed: {type(e).__name__}", file=sys.stderr)
        return None


def delete_secret(cluster_name):
    """Remove a secret from the OS keyring."""
    try:
        import keyring
        keyring.delete_password(APP_ID, cluster_name)
    except Exception as e:
        print(f"[debug] delete_secret failed: {type(e).__name__}", file=sys.stderr)


def migrate_secrets(config):
    """Migrate legacy plain-text secrets from JSON to the OS keyring.
    Only removes from JSON after confirmed keyring write."""
    try:
        import keyring
    except ImportError:
        return  # Don't migrate without keyring available

    changed = False
    for cluster in config.get("clusters", []):
        if "token_secret" in cluster:
            secret = cluster["token_secret"]
            if secret:
                try:
                    keyring.set_password(APP_ID, cluster["name"], secret)
                    del cluster["token_secret"]
                    changed = True
                except Exception:
                    pass  # Leave in JSON if keyring write fails
            else:
                del cluster["token_secret"]
                changed = True
    if changed:
        save_config(config)


# ─── Proxmox API Helpers ─────────────────────────────────────────────────────
def _get_ssl_context(skip_tls_verify=False):
    """Create an SSL context. Verifies certs by default; pass skip_tls_verify=True
    for clusters using self-signed certificates."""
    ctx = ssl.create_default_context()
    if skip_tls_verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def api_request(host, endpoint, method="GET", auth=None, data=None):
    """Make a Proxmox API request via urllib.
    Returns dict with either response data or an 'error' key."""
    if not host.startswith("https://"):
        return {"error": "Host must use https://"}
    url = f"{host}{endpoint}"
    req = urllib.request.Request(url, method=method)

    if auth:
        if auth.get("token_id") and auth.get("token_secret"):
            req.add_header(
                "Authorization",
                f"PVEAPIToken={auth['token_id']}={auth['token_secret']}"
            )
        elif auth.get("ticket"):
            req.add_header("Cookie", f"PVEAuthCookie={auth['ticket']}")
            if auth.get("csrf"):
                req.add_header("CSRFPreventionToken", auth["csrf"])

    # Ensure POST/DELETE/PUT send a proper request body
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
            # Normalize: Proxmox returns errors in "message" or "errors"
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
    """Authenticate with username/password via POST body."""
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
        print(f"[debug] authenticate_password failed: {type(e).__name__}",
              file=sys.stderr)
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
    def __init__(self, parent, cluster=None):
        super().__init__(parent)
        self.result = None
        self.original_name = cluster.get("name") if cluster else None

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

        lbl = {"bg": C["base"], "fg": C["subtext0"], "font": ("sans-serif", 9)}
        entry_cfg = {
            "bg": C["surface0"], "fg": C["text"], "insertbackground": C["text"],
            "relief": "flat", "font": ("monospace", 10), "highlightthickness": 1,
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
            font=("sans-serif", 9),
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
            "font": ("sans-serif", 10), "command": self._toggle_auth,
        }
        tk.Radiobutton(
            auth_frame, text="API Token", variable=self.auth_var,
            value="token", **radio_cfg
        ).pack(side="left", padx=(0, 20))
        tk.Radiobutton(
            auth_frame, text="Password", variable=self.auth_var,
            value="password", **radio_cfg
        ).pack(side="left")

        self.token_frame = tk.Frame(main, bg=C["base"])
        self.token_frame.grid(row=7, column=0, sticky="ew")
        self.token_frame.columnconfigure(0, weight=1)

        tk.Label(self.token_frame, text="TOKEN ID  (user@realm!token)", **lbl).pack(
            anchor="w", pady=(0, 4)
        )
        self.token_id_entry = tk.Entry(self.token_frame, **entry_cfg)
        self.token_id_entry.pack(fill="x", pady=(0, 10), ipady=6)

        tk.Label(self.token_frame, text="TOKEN SECRET", **lbl).pack(
            anchor="w", pady=(0, 4)
        )
        self.token_secret_entry = tk.Entry(self.token_frame, **entry_cfg, show="•")
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
            hover_bg=C["surface2"], font=("sans-serif", 10),
        ).pack(side="right", padx=(8, 0))
        HoverButton(
            btn_frame, text="  Save  ", command=self._save,
            bg=C["blue"], fg=C["crust"], relief="flat", padx=18, pady=6,
            hover_bg=C["sapphire"], hover_fg=C["crust"],
            font=("sans-serif", 10, "bold"),
        ).pack(side="right")

        if cluster:
            self.name_entry.insert(0, cluster.get("name", ""))
            self.host_entry.insert(0, cluster.get("host", ""))
            self.skip_tls_var.set(cluster.get("skip_tls_verify", False))
            self.auth_var.set(cluster.get("auth_method", "token"))
            self.token_id_entry.insert(0, cluster.get("token_id", ""))
            secret = get_secret(self.original_name)
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
                "Missing Fields", "Name and Host URL are required.", parent=self
            )
            return

        auth_method = self.auth_var.get()
        secret = self.token_secret_entry.get().strip()

        if self.original_name and self.original_name != name:
            delete_secret(self.original_name)

        if auth_method == "token" and secret:
            if not save_secret(name, secret):
                messagebox.showwarning(
                    "Keyring Warning",
                    "Could not save secret to OS keyring.\n"
                    "The secret will need to be re-entered next time.",
                    parent=self,
                )

        self.result = {
            "name": name,
            "host": host,
            "auth_method": auth_method,
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
            "relief": "flat", "font": ("monospace", 10), "highlightthickness": 1,
            "highlightcolor": C["blue"], "highlightbackground": C["surface1"],
        }

        tk.Label(
            main, text=f"Password for {username}", bg=C["base"], fg=C["text"],
            font=("sans-serif", 10),
        ).pack(anchor="w", pady=(0, 2))
        tk.Label(
            main, text=host, bg=C["base"], fg=C["overlay0"],
            font=("sans-serif", 9),
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
            font=("sans-serif", 10, "bold"),
        ).pack(side="right")

        self.pw_entry.focus_set()
        self.wait_window()

    def _submit(self):
        self.result = self.pw_entry.get()
        self.destroy()


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
            fg=C["text"], font=("sans-serif", 12, "bold"),
        ).pack(side="left")

        HoverButton(
            header, text="  ↻ Refresh  ", command=self._load_snapshots,
            bg=C["surface0"], fg=C["subtext0"], relief="flat", padx=10, pady=3,
            hover_bg=C["surface1"], hover_fg=C["text"], font=("sans-serif", 9),
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
            font=("sans-serif", 10), borderwidth=0,
        )
        style.configure(
            "Snap.Treeview.Heading", background=C["surface1"],
            foreground=C["subtext0"], font=("sans-serif", 9, "bold"),
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
            font=("sans-serif", 9), anchor="w",
        )
        self.status_label.pack(fill="x", pady=(0, 8))

        btn_frame = tk.Frame(main, bg=C["base"])
        btn_frame.pack(fill="x")

        HoverButton(
            btn_frame, text="  Close  ", command=self.destroy,
            bg=C["surface1"], fg=C["text"], relief="flat", padx=16, pady=6,
            hover_bg=C["surface2"], font=("sans-serif", 10),
        ).pack(side="right")
        HoverButton(
            btn_frame, text="  ⏪  Rollback  ", command=self._rollback_snapshot,
            bg=C["peach"], fg=C["crust"], relief="flat", padx=16, pady=6,
            hover_bg=C["yellow"], hover_fg=C["crust"],
            font=("sans-serif", 10, "bold"),
        ).pack(side="right", padx=(0, 8))
        HoverButton(
            btn_frame, text="  🗑  Delete  ", command=self._delete_snapshot,
            bg=C["surface0"], fg=C["red"], relief="flat", padx=16, pady=6,
            hover_bg=C["surface1"], hover_fg=C["red"], font=("sans-serif", 10),
        ).pack(side="right", padx=(0, 8))
        HoverButton(
            btn_frame, text="  +  Create Snapshot  ",
            command=self._create_snapshot,
            bg=C["surface0"], fg=C["green"], relief="flat", padx=16, pady=6,
            hover_bg=C["surface1"], hover_fg=C["green"],
            font=("sans-serif", 10),
        ).pack(side="left")

        self._load_snapshots()
        self.wait_window()

    def _load_snapshots(self):
        self.status_label.config(text="⏳  Loading snapshots...", fg=C["yellow"])
        self.snap_tree.delete(*self.snap_tree.get_children())
        self.update_idletasks()

        data = api_request(
            self.cluster["host"],
            f"/api2/json/nodes/{self.vm['node']}/qemu/{self.vm['vmid']}/snapshot",
            auth=self.auth,
        )

        if "error" in data:
            self.status_label.config(text=f"✗ {data['error']}", fg=C["red"])
            return

        snapshots = data.get("data", [])
        real_snaps = [s for s in snapshots if s.get("name") != "current"]

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
                "No Selection", "Select a snapshot to rollback to.", parent=self
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
            text=f"⏳  Rolling back to '{snap_name}'...", fg=C["yellow"]
        )
        self.update_idletasks()

        data = api_request(
            self.cluster["host"],
            f"/api2/json/nodes/{self.vm['node']}/qemu/{self.vm['vmid']}"
            f"/snapshot/{urllib.parse.quote(snap_name, safe='')}/rollback",
            method="POST", auth=self.auth,
        )

        if "error" in data:
            self.status_label.config(text="✗  Rollback failed", fg=C["red"])
            messagebox.showerror(
                "Rollback Failed", data["error"], parent=self
            )
        else:
            self.status_label.config(
                text=f"✓  Rolled back to '{snap_name}'", fg=C["green"]
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
            "relief": "flat", "font": ("monospace", 10), "highlightthickness": 1,
            "highlightcolor": C["blue"], "highlightbackground": C["surface1"],
        }
        lbl = {"bg": C["base"], "fg": C["subtext0"], "font": ("sans-serif", 9)}

        tk.Label(main, text="SNAPSHOT NAME", **lbl).pack(
            anchor="w", pady=(0, 4)
        )
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
            font=("sans-serif", 10),
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
            hover_bg=C["surface2"], font=("sans-serif", 10),
        ).pack(side="right", padx=(8, 0))
        HoverButton(
            btn_frame, text="  Create  ", command=on_create,
            bg=C["green"], fg=C["crust"], relief="flat", padx=16, pady=5,
            hover_bg=C["teal"], hover_fg=C["crust"],
            font=("sans-serif", 10, "bold"),
        ).pack(side="right")

        name_entry.focus_set()
        dlg.wait_window()

        if not result["name"]:
            return

        self.status_label.config(
            text=f"⏳  Creating snapshot '{result['name']}'...", fg=C["yellow"]
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
            self.status_label.config(
                text="✗  Snapshot creation failed", fg=C["red"]
            )
            messagebox.showerror("Snapshot Failed", data["error"], parent=self)
        else:
            self.status_label.config(
                text=f"✓  Snapshot '{result['name']}' created", fg=C["green"]
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

        self.status_label.config(
            text=f"⏳  Deleting '{snap_name}'...", fg=C["yellow"]
        )
        self.update_idletasks()

        data = api_request(
            self.cluster["host"],
            f"/api2/json/nodes/{self.vm['node']}/qemu/{self.vm['vmid']}"
            f"/snapshot/{urllib.parse.quote(snap_name, safe='')}",
            method="DELETE", auth=self.auth,
        )

        if "error" in data:
            self.status_label.config(text="✗  Delete failed", fg=C["red"])
            messagebox.showerror("Delete Failed", data["error"], parent=self)
        else:
            self.status_label.config(
                text=f"✓  Snapshot '{snap_name}' deleted", fg=C["green"]
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
        try:
            _icon_img = tk.PhotoImage(file=str(ICON_PATH))
            self.iconphoto(True, _icon_img)
        except Exception:
            pass

        self.config_data = load_config()
        self.current_cluster = None
        self.auth_cache = {}
        self._closing = False
        self.protocol("WM_DELETE_WINDOW", self._on_close)

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

        # Migrate after prereqs so keyring is available
        migrate_secrets(self.config_data)

        self._build_ui()
        self._populate_clusters()

        if self.config_data.get("clusters"):
            self.cluster_listbox.select_set(0)
            self.current_cluster = self.config_data["clusters"][0]
            self.after(100, self._refresh_vms)

    # ── Prereqs ───────────────────────────────────────────────────────────────
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

    # ── UI Construction ───────────────────────────────────────────────────────
    def _on_close(self):
        self._closing = True
        if hasattr(self, "_notes_combo") and self._notes_combo:
            self._notes_combo.destroy()
            self._notes_combo = None
        for child in self.winfo_children():
            if isinstance(child, tk.Toplevel):
                child.destroy()
        self.quit()
        self.destroy()

    def _build_ui(self):
        for widget in self.winfo_children():
            widget.destroy()
        self.configure(bg=C["base"])

        # Header
        header = tk.Frame(self, bg=C["crust"], height=52)
        header.pack(fill="x")
        header.pack_propagate(False)

        title_frame = tk.Frame(header, bg=C["crust"])
        title_frame.pack(side="left", padx=16)
        tk.Label(
            title_frame, text="◈", bg=C["crust"], fg=C["mauve"],
            font=("sans-serif", 18),
        ).pack(side="left", padx=(0, 8))
        tk.Label(
            title_frame, text=f"Proxmox SPICE Manager v{APP_VERSION}",
            bg=C["crust"], fg=C["text"], font=("sans-serif", 12, "bold"),
        ).pack(side="left")

        hbtn = {
            "bg": C["crust"], "fg": C["subtext0"], "relief": "flat",
            "font": ("sans-serif", 9), "padx": 10, "pady": 4,
            "activebackground": C["mantle"], "activeforeground": C["text"],
        }
        HoverButton(
            header, text="⚙  Install to App Menu",
            command=self._install_to_app_menu,
            hover_bg=C["mantle"], hover_fg=C["text"], **hbtn,
        ).pack(side="right", padx=(0, 12))
        HoverButton(
            header, text="🔍  Check Prerequisites",
            command=self._recheck_prereqs,
            hover_bg=C["mantle"], hover_fg=C["text"], **hbtn,
        ).pack(side="right", padx=(0, 4))

        theme_frame = tk.Frame(header, bg=C["crust"])
        theme_frame.pack(side="right", padx=(0, 8))
        tk.Label(
            theme_frame, text="Theme:", bg=C["crust"], fg=C["overlay0"],
            font=("sans-serif", 9),
        ).pack(side="left", padx=(0, 6))

        self.theme_var = tk.StringVar(
            value=self.config_data.get("theme", "Catppuccin Mocha")
        )
        theme_menu = ttk.Combobox(
            theme_frame, textvariable=self.theme_var,
            values=list(THEMES.keys()), state="readonly", width=18,
            font=("sans-serif", 9),
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

        # Body
        body = tk.Frame(self, bg=C["base"])
        body.pack(fill="both", expand=True)

        # Sidebar
        sidebar = tk.Frame(body, bg=C["mantle"], width=200)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(
            sidebar, text="CLUSTERS", bg=C["mantle"], fg=C["overlay0"],
            font=("sans-serif", 8, "bold"), anchor="w",
        ).pack(fill="x", padx=14, pady=(14, 6))
        tk.Frame(sidebar, bg=C["surface0"], height=1).pack(
            fill="x", padx=12, pady=(0, 6)
        )

        self.cluster_listbox = tk.Listbox(
            sidebar, bg=C["mantle"], fg=C["text"],
            selectbackground=C["surface0"], selectforeground=C["blue"],
            relief="flat", font=("sans-serif", 10), highlightthickness=0,
            activestyle="none", borderwidth=0,
        )
        self.cluster_listbox.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.cluster_listbox.bind("<<ListboxSelect>>", self._on_cluster_select)

        tk.Frame(sidebar, bg=C["surface0"], height=1).pack(fill="x", padx=12)

        sb_btn = {
            "bg": C["surface0"], "fg": C["subtext0"], "relief": "flat",
            "padx": 10, "pady": 4, "font": ("sans-serif", 9),
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
            io_bar, text="⬇ Import", command=self._import_config,
            hover_bg=C["surface1"], hover_fg=C["text"], **sb_btn,
        ).pack(side="left", padx=(0, 4), expand=True, fill="x")
        HoverButton(
            io_bar, text="⬆ Export", command=self._export_config,
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
            fg=C["overlay0"], font=("sans-serif", 10), anchor="w",
        )
        self.status_label.pack(side="left")

        HoverButton(
            toolbar, text="↻  Refresh", command=self._refresh_vms,
            bg=C["surface0"], fg=C["subtext0"], relief="flat", padx=12, pady=4,
            hover_bg=C["surface1"], hover_fg=C["text"], font=("sans-serif", 9),
        ).pack(side="right")

        self._all_vm_rows = []
        self._checked_items = set()
        self._notes_combo = None

        # Filter row
        filter_row = tk.Frame(content, bg=C["surface1"])
        filter_row.pack(fill="x", padx=16, pady=(8, 0))

        fentry = {
            "bg": C["crust"], "fg": C["text"], "insertbackground": C["text"],
            "relief": "flat", "font": ("sans-serif", 9), "highlightthickness": 1,
            "highlightcolor": C["blue"], "highlightbackground": C["surface1"],
        }
        tk.Label(
            filter_row, text="🔍", bg=C["surface1"], fg=C["overlay0"],
            font=("sans-serif", 9),
        ).pack(side="left", padx=(4, 4))

        self._filter_vars = {}
        self._filter_entries = {}
        filter_defs = [
            ("vmid", "VMID"), ("name", "Name"), ("node", "Node"),
            ("pool", "Pool"), ("snaps", "Snaps"), ("status", "Status"),
            ("notes", "Notes"),
        ]

        for col_id, placeholder in filter_defs:
            var = tk.StringVar()
            var.trace_add("write", lambda *args: self._apply_filters())
            self._filter_vars[col_id] = var

            entry = tk.Entry(filter_row, textvariable=var, width=1, **fentry)
            entry.pack(side="left", fill="x", expand=True, ipady=3, padx=(0, 1))
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
            filter_row, text=" ✕ ", command=self._clear_filters,
            bg=C["surface1"], fg=C["overlay0"], relief="flat", padx=4, pady=1,
            hover_bg=C["surface2"], hover_fg=C["red"], font=("sans-serif", 9),
        ).pack(side="right", padx=(2, 2))

        # VM Table
        table_frame = tk.Frame(content, bg=C["base"])
        table_frame.pack(fill="both", expand=True, padx=16, pady=(10, 0))

        columns = ("check", "vmid", "name", "node", "pool", "snaps", "status", "notes")
        self.vm_tree = ttk.Treeview(
            table_frame, columns=columns, show="headings",
            selectmode="extended", height=12,
        )

        style.configure(
            "Treeview", background=C["surface0"], foreground=C["text"],
            fieldbackground=C["surface0"], rowheight=32,
            font=("sans-serif", 10), borderwidth=0,
        )
        style.configure(
            "Treeview.Heading", background=C["surface1"],
            foreground=C["subtext0"], font=("sans-serif", 9, "bold"),
            borderwidth=0, relief="flat",
        )
        style.map(
            "Treeview",
            background=[("selected", C["surface1"])],
            foreground=[("selected", C["blue"])],
        )
        style.map("Treeview.Heading", background=[("active", C["surface2"])])

        self.vm_tree.heading(
            "check", text="☐",
            command=self._toggle_all_checks,
        )
        self.vm_tree.column(
            "check", width=40, minwidth=40, anchor="center", stretch=False,
        )
        for col in columns:
            if col == "check":
                continue
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
        self.vm_tree.column("notes", width=120, minwidth=60)

        self._all_columns = list(columns)
        self._data_columns = [c for c in columns if c != "check"]
        if not hasattr(self, "_tree_sort_col"):
            self._tree_sort_col = None
            self._tree_sort_asc = True
        if not hasattr(self, "_display_columns"):
            self._display_columns = list(columns)
        else:
            if set(self._display_columns) != set(columns):
                self._display_columns = list(columns)
        self._drag_col = None
        self._drag_start_x = None

        self.vm_tree.bind("<ButtonPress-1>", self._on_heading_press)
        self.vm_tree.bind("<B1-Motion>", self._on_heading_drag)
        self.vm_tree.bind("<ButtonRelease-1>", self._on_heading_release)

        saved_order = self.config_data.get("column_order")
        if saved_order and set(saved_order) == set(self._data_columns):
            self._display_columns = ["check"] + saved_order
        self.vm_tree["displaycolumns"] = self._display_columns

        # Restore sort indicators on headings
        if self._tree_sort_col:
            for c in self._data_columns:
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
            bottom, text=" ▶ Launch SPICE ", command=self._launch_spice,
            bg=C["green"], fg=C["crust"], relief="flat", padx=16, pady=8,
            hover_bg=C["teal"], hover_fg=C["crust"],
            font=("sans-serif", 11, "bold"),
        ).pack(side="right")
        HoverButton(
            bottom, text=" Export .desktop ", command=self._export_desktop,
            bg=C["surface0"], fg=C["subtext0"], relief="flat", padx=12, pady=8,
            hover_bg=C["surface1"], hover_fg=C["text"], font=("sans-serif", 10),
        ).pack(side="right", padx=(0, 8))

        power_frame = tk.Frame(bottom, bg=C["base"])
        power_frame.pack(side="left")

        pbtn = {"relief": "flat", "padx": 10, "pady": 8, "font": ("sans-serif", 10)}
        HoverButton(
            power_frame, text=" ⏻ Start ", command=self._start_vm,
            bg=C["surface0"], fg=C["green"], hover_bg=C["surface1"],
            hover_fg=C["green"], **pbtn,
        ).pack(side="left", padx=(0, 4))
        HoverButton(
            power_frame, text=" ⏹ Shutdown ", command=self._shutdown_vm,
            bg=C["surface0"], fg=C["yellow"], hover_bg=C["surface1"],
            hover_fg=C["yellow"], **pbtn,
        ).pack(side="left", padx=(0, 4))
        HoverButton(
            power_frame, text=" ↻ Reboot ", command=self._reboot_vm,
            bg=C["surface0"], fg=C["peach"], hover_bg=C["surface1"],
            hover_fg=C["peach"], **pbtn,
        ).pack(side="left", padx=(0, 4))
        HoverButton(
            power_frame, text=" ⏼ Force Stop ", command=self._stop_vm,
            bg=C["surface0"], fg=C["red"], hover_bg=C["surface1"],
            hover_fg=C["red"], **pbtn,
        ).pack(side="left", padx=(0, 4))
        HoverButton(
            power_frame, text=" 📸 Snapshots ", command=self._show_snapshots,
            bg=C["surface0"], fg=C["lavender"], hover_bg=C["surface1"],
            hover_fg=C["lavender"], **pbtn,
        ).pack(side="left", padx=(0, 4))
        HoverButton(
            power_frame, text=" ⏪ Quick Rollback ",
            command=self._quick_rollback,
            bg=C["surface0"], fg=C["peach"], hover_bg=C["surface1"],
            hover_fg=C["peach"], **pbtn,
        ).pack(side="left", padx=(0, 4))
        HoverButton(
            power_frame, text=" Notes ⚙ ",
            command=self._manage_note_options,
            bg=C["surface0"], fg=C["subtext0"], hover_bg=C["surface1"],
            hover_fg=C["text"], **pbtn,
        ).pack(side="left")

        self._check_count_label = tk.Label(
            bottom, text="", bg=C["base"], fg=C["sapphire"],
            font=("sans-serif", 9),
        )
        self._check_count_label.pack(side="left", padx=(12, 0))

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

    # ── Cluster management ────────────────────────────────────────────────────
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
        dlg = ClusterDialog(self)
        if dlg.result:
            self.config_data.setdefault("clusters", []).append(dlg.result)
            save_config(self.config_data)
            self._populate_clusters()

    def _edit_cluster(self):
        result = self._get_selected_cluster()
        if not result:
            messagebox.showinfo(
                "No Selection", "Select a cluster to edit.", parent=self
            )
            return
        idx, cluster = result
        dlg = ClusterDialog(self, cluster)
        if dlg.result:
            self.config_data["clusters"][idx] = dlg.result
            save_config(self.config_data)
            self._populate_clusters()

    def _remove_cluster(self):
        result = self._get_selected_cluster()
        if not result:
            return
        idx, cluster = result
        if messagebox.askyesno(
            "Confirm", f"Remove cluster '{cluster['name']}'?", parent=self
        ):
            delete_secret(cluster["name"])
            self.config_data["clusters"].pop(idx)
            save_config(self.config_data)
            self._populate_clusters()
            self.vm_tree.delete(*self.vm_tree.get_children())
            self.current_cluster = None
            self.status_label.config(text="Select a cluster to view VMs")

    # ── Import / Export ───────────────────────────────────────────────────────
    def _export_config(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json")],
        )
        if not path:
            return

        if not messagebox.askyesno(
            "Export Clusters",
            "Security Warning:\n\n"
            "This export file will contain your API Token Secrets "
            "in plain text.\nKeep this file safe and delete it after "
            "importing on another machine.\n\nProceed with export?",
            parent=self,
        ):
            return

        export_data = copy.deepcopy(self.config_data)
        export_data["version"] = APP_VERSION

        for cluster in export_data.get("clusters", []):
            if cluster.get("auth_method") == "token":
                secret = get_secret(cluster["name"])
                if secret:
                    cluster["token_secret"] = secret

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, indent=2)
            os.chmod(path, 0o600)
            messagebox.showinfo(
                "Exported", f"Successfully exported to:\n{path}", parent=self
            )
        except Exception as e:
            messagebox.showerror("Export Failed", str(e), parent=self)

    def _import_config(self):
        path = filedialog.askopenfilename(
            filetypes=[("JSON files", "*.json")]
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                imported_data = json.load(f)
        except Exception as e:
            messagebox.showerror(
                "Import Failed", f"Could not read file:\n{e}", parent=self
            )
            return

        imported_version = imported_data.get("version", "Legacy")
        if imported_version != APP_VERSION:
            messagebox.showerror(
                "Version Mismatch",
                f"Cannot import.\n\nFile version: {imported_version}\n"
                f"App version: {APP_VERSION}\n\n"
                "You can only import files matching the current app version.",
                parent=self,
            )
            return

        new_clusters = imported_data.get("clusters", [])
        if not new_clusters:
            messagebox.showinfo(
                "Empty", "No clusters found in the selected file.", parent=self
            )
            return

        existing_names = [c["name"] for c in self.config_data.get("clusters", [])]

        for cluster in new_clusters:
            secret = cluster.pop("token_secret", None)
            if secret:
                save_secret(cluster["name"], secret)

            if cluster["name"] in existing_names:
                cluster["name"] = f"{cluster['name']} (Imported)"

            self.config_data.setdefault("clusters", []).append(cluster)

        save_config(self.config_data)
        self._populate_clusters()
        messagebox.showinfo(
            "Imported",
            f"Successfully imported {len(new_clusters)} cluster(s).",
            parent=self,
        )

    # ── Auth ──────────────────────────────────────────────────────────────────
    def _get_auth(self, cluster):
        name = cluster["name"]
        skip_tls = cluster.get("skip_tls_verify", False)

        if cluster["auth_method"] == "token":
            token_id = cluster.get("token_id")
            token_secret = get_secret(name)
            if token_id and token_secret:
                return {"token_id": token_id, "token_secret": token_secret,
                        "skip_tls_verify": skip_tls}
            messagebox.showerror(
                "Auth Error",
                "Token ID or Secret is missing/not found in keyring.",
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

        messagebox.showerror(
            "Auth Failed", "Could not authenticate. Check credentials.",
            parent=self,
        )
        return None

    # ── VM Refresh ────────────────────────────────────────────────────────────
    def _refresh_vms(self):
        if not self.current_cluster:
            return
        cluster = self.current_cluster
        auth = self._get_auth(cluster)
        if not auth:
            self.status_label.config(text="✗  Authentication failed", fg=C["red"])
            return
        self.status_label.config(text="⏳  Loading VMs...", fg=C["yellow"])
        self.update_idletasks()

        def fetch():

            data = api_request(
                cluster["host"],
                "/api2/json/cluster/resources?type=vm", auth=auth,
            )

            if "error" in data:
                self.after(0, lambda d=data: self.status_label.config(
                    text=f"✗ API Error: {d['error']}", fg=C["red"]
                ))
                return

            all_vms = data.get("data", [])
            if not all_vms:
                self.after(0, lambda: (
                    self.vm_tree.delete(*self.vm_tree.get_children()),
                    self.status_label.config(
                        text="✗  No VMs found (check permissions)",
                        fg=C["red"],
                    ),
                ))
                return

            qemu_vms = [v for v in all_vms if v.get("type") == "qemu"]
            self.after(0, lambda: self.status_label.config(
                text=f"⏳  Checking {len(qemu_vms)} VMs for SPICE...",
                fg=C["yellow"],
            ))

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
                    spice_vms.append(vm)

            def update_ui():
                self.vm_tree.delete(*self.vm_tree.get_children())
                if not spice_vms:
                    self._all_vm_rows = []
                    self.status_label.config(
                        text=f"✗  No SPICE VMs found "
                        f"({len(qemu_vms)} checked)",
                        fg=C["red"],
                    )
                    return

                spice_vms.sort(key=lambda v: v.get("vmid", 0))
                self._all_vm_rows = []
                for vm in spice_vms:
                    status = vm.get("status", "?")
                    display_status = (
                        "● running" if status == "running" else "○ stopped"
                    )
                    tag = "running" if status == "running" else "stopped"
                    snap_count = vm.get("_snap_count", 0)
                    snap_display = (
                        f"📸 {snap_count}" if snap_count > 0 else "—"
                    )

                    vmid_str = str(vm.get("vmid", "?"))
                    note = self.config_data.get(
                        "vm_notes", {}
                    ).get(vmid_str, "")
                    row = (
                        vmid_str,
                        vm.get("name", "unnamed"),
                        vm.get("node", "?"),
                        vm.get("pool", "—"),
                        snap_display,
                        display_status,
                        note,
                    )
                    self._all_vm_rows.append((row, tag))

                self._apply_filters()
                tls_warn = "  ⚠ TLS off" if cluster.get(
                    "skip_tls_verify", False) else ""
                self.status_label.config(
                    text=f"◈  {cluster['name']}  —  "
                    f"{len(spice_vms)} SPICE VMs{tls_warn}",
                    fg=C["yellow"] if tls_warn else C["text"],
                )

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

        col_indices = {
            "vmid": 0, "name": 1, "node": 2, "pool": 3, "snaps": 4,
            "status": 5, "notes": 6,
        }
        placeholders = {
            "vmid": "VMID", "name": "Name", "node": "Node", "pool": "Pool",
            "snaps": "Snaps", "status": "Status", "notes": "Notes",
        }

        filters = {}
        for col_id, var in self._filter_vars.items():
            val = var.get().strip().lower()
            if val and val != placeholders.get(col_id, "").lower():
                filters[col_id] = val

        self.vm_tree.delete(*self.vm_tree.get_children())
        visible = 0
        for row, tag in self._all_vm_rows:
            match = all(
                f_text in str(row[col_indices.get(cid, -1)]).lower()
                for cid, f_text in filters.items()
            )
            if match:
                vmid = row[0]
                check = "☑" if vmid in self._checked_items else "☐"
                self.vm_tree.insert(
                    "", "end", values=(check,) + row, tags=(tag,),
                )
                visible += 1

        self.vm_tree.tag_configure("running", foreground=C["green"])
        self.vm_tree.tag_configure("stopped", foreground=C["overlay0"])

        self._update_check_header()
        self._update_selection_count()

        # Re-apply sort after filter rebuild
        if self._tree_sort_col:
            self._reapply_sort()

        if filters and visible != len(self._all_vm_rows):
            self.status_label.config(
                text=f"🔍  Showing {visible} of "
                f"{len(self._all_vm_rows)} VMs",
                fg=C["sapphire"],
            )

    def _clear_filters(self):
        placeholders = {
            "vmid": "VMID", "name": "Name", "node": "Node", "pool": "Pool",
            "snaps": "Snaps", "status": "Status", "notes": "Notes",
        }
        for col_id, var in self._filter_vars.items():
            var.set("")
            entry = self._filter_entries[col_id]
            entry.delete(0, "end")
            entry.insert(0, placeholders[col_id])
            entry.config(fg=C["overlay0"])

    # ── Sorting ───────────────────────────────────────────────────────────────
    def _reapply_sort(self):
        """Re-sort the tree using the current sort column/direction without toggling."""
        col = self._tree_sort_col
        if not col:
            return

        rows = [
            (self.vm_tree.set(iid, col), iid)
            for iid in self.vm_tree.get_children("")
        ]

        if col == "vmid":
            rows.sort(
                key=lambda r: int(r[0]) if r[0].isdigit() else 0,
                reverse=not self._tree_sort_asc,
            )
        else:
            rows.sort(
                key=lambda r: r[0].lower(), reverse=not self._tree_sort_asc
            )

        for idx, (_, iid) in enumerate(rows):
            self.vm_tree.move(iid, "", idx)

        for c in self._data_columns:
            label = c.upper()
            if c == col:
                label += "  ▲" if self._tree_sort_asc else "  ▼"
            self.vm_tree.heading(c, text=label)

    def _sort_tree(self, col):
        if col == "check":
            return
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
                    if self._display_columns[idx] == "check":
                        return None
                    return idx
        return None

    def _on_heading_press(self, event):
        region = self.vm_tree.identify_region(event.x, event.y)
        if region == "heading":
            self._drag_col = self._col_from_x(event.x)
            self._drag_start_x = event.x
        else:
            self._drag_col = None
            self._drag_start_x = None
            if region == "cell":
                col_id = self.vm_tree.identify_column(event.x)
                display_idx = int(col_id.replace("#", "")) - 1
                if 0 <= display_idx < len(self._display_columns):
                    col_name = self._display_columns[display_idx]
                    if col_name == "check":
                        iid = self.vm_tree.identify_row(event.y)
                        if iid:
                            self._toggle_check(iid)
                    elif col_name == "notes":
                        iid = self.vm_tree.identify_row(event.y)
                        if iid:
                            self._edit_notes_cell(iid, event)

    def _on_heading_drag(self, event):
        if (self._drag_col is not None and self._drag_start_x is not None
                and abs(event.x - self._drag_start_x) > 20):
            self.vm_tree.config(cursor="sb_h_double_arrow")

    def _on_heading_release(self, event):
        self.vm_tree.config(cursor="")
        if (self._drag_col is None or self._drag_start_x is None
                or abs(event.x - self._drag_start_x) < 20):
            self._drag_col = None
            self._drag_start_x = None
            return

        target_idx = self._col_from_x(event.x)
        if target_idx is None or target_idx == self._drag_col:
            self._drag_col = None
            self._drag_start_x = None
            return

        cols = list(self._display_columns)
        cols.insert(target_idx, cols.pop(self._drag_col))
        self._display_columns = cols
        self.vm_tree["displaycolumns"] = cols
        self.config_data["column_order"] = [c for c in cols if c != "check"]
        save_config(self.config_data)

        self._drag_col = None
        self._drag_start_x = None

    # ── Checkbox Selection ────────────────────────────────────────────────────
    def _toggle_check(self, iid):
        values = list(self.vm_tree.item(iid, "values"))
        vmid = values[1]
        if vmid in self._checked_items:
            self._checked_items.discard(vmid)
            values[0] = "☐"
        else:
            self._checked_items.add(vmid)
            values[0] = "☑"
        self.vm_tree.item(iid, values=values)
        self._update_check_header()
        self._update_selection_count()

    def _toggle_all_checks(self):
        all_items = self.vm_tree.get_children("")
        all_checked = all(
            self.vm_tree.item(iid, "values")[0] == "☑"
            for iid in all_items
        ) if all_items else False

        for iid in all_items:
            values = list(self.vm_tree.item(iid, "values"))
            vmid = values[1]
            if all_checked:
                self._checked_items.discard(vmid)
                values[0] = "☐"
            else:
                self._checked_items.add(vmid)
                values[0] = "☑"
            self.vm_tree.item(iid, values=values)
        self._update_check_header()
        self._update_selection_count()

    def _update_check_header(self):
        all_items = self.vm_tree.get_children("")
        if not all_items:
            self.vm_tree.heading("check", text="☐")
            return
        all_checked = all(
            self.vm_tree.item(iid, "values")[0] == "☑"
            for iid in all_items
        )
        self.vm_tree.heading("check", text="☑" if all_checked else "☐")

    def _update_selection_count(self):
        count = len([
            iid for iid in self.vm_tree.get_children("")
            if self.vm_tree.item(iid, "values")[0] == "☑"
        ])
        if hasattr(self, "_check_count_label"):
            if count > 0:
                self._check_count_label.config(text=f"  {count} checked")
            else:
                self._check_count_label.config(text="")

    # ── Notes Editing ────────────────────────────────────────────────────────
    def _edit_notes_cell(self, iid, event):
        if hasattr(self, "_notes_combo") and self._notes_combo:
            self._notes_combo.destroy()
            self._notes_combo = None

        bbox = self.vm_tree.bbox(iid, column="notes")
        if not bbox:
            return

        values = self.vm_tree.item(iid, "values")
        vmid = values[1]
        current = values[7] if len(values) > 7 else ""

        options = self.config_data.get("note_options", [])
        combo_values = [""] + options

        combo = ttk.Combobox(
            self.vm_tree, values=combo_values, state="normal",
            font=("sans-serif", 10),
        )
        combo.set(current)
        combo.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])
        combo.focus_set()
        combo.icursor("end")
        self._notes_combo = combo

        def commit(e=None):
            val = combo.get().strip()
            if val and val not in self.config_data.get("note_options", []):
                self.config_data.setdefault("note_options", []).append(val)
            vm_notes = self.config_data.setdefault("vm_notes", {})
            if val:
                vm_notes[vmid] = val
            else:
                vm_notes.pop(vmid, None)
            save_config(self.config_data)

            vals = list(self.vm_tree.item(iid, "values"))
            vals[7] = val
            self.vm_tree.item(iid, values=vals)

            for i, (row, tag) in enumerate(self._all_vm_rows):
                if row[0] == vmid:
                    self._all_vm_rows[i] = (row[:-1] + (val,), tag)
                    break

            combo.destroy()
            self._notes_combo = None

        def cancel(e=None):
            combo.destroy()
            self._notes_combo = None

        combo.bind("<Return>", commit)
        combo.bind("<Escape>", cancel)
        combo.bind("<FocusOut>", commit)
        combo.bind("<<ComboboxSelected>>", commit)

    def _manage_note_options(self):
        dlg = tk.Toplevel(self)
        dlg.title("Manage Note Options")
        dlg.geometry("300x350")
        dlg.configure(bg=C["base"])
        dlg.transient(self)
        dlg.grab_set()

        tk.Label(
            dlg, text="Note Options", bg=C["base"], fg=C["text"],
            font=("sans-serif", 12, "bold"),
        ).pack(pady=(12, 8))

        list_frame = tk.Frame(dlg, bg=C["base"])
        list_frame.pack(fill="both", expand=True, padx=16)

        listbox = tk.Listbox(
            list_frame, bg=C["surface0"], fg=C["text"],
            selectbackground=C["surface2"], selectforeground=C["text"],
            font=("sans-serif", 10), relief="flat", borderwidth=0,
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
            font=("sans-serif", 10),
        )
        add_entry.pack(side="left", fill="x", expand=True, ipady=4)

        def add_option():
            val = add_var.get().strip()
            if val and val not in self.config_data.get("note_options", []):
                self.config_data.setdefault("note_options", []).append(val)
                listbox.insert("end", val)
                save_config(self.config_data)
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
                save_config(self.config_data)

        HoverButton(
            btn_frame, text=" Add ", command=add_option,
            bg=C["green"], fg=C["crust"], relief="flat", padx=8, pady=4,
            hover_bg=C["teal"], hover_fg=C["crust"],
            font=("sans-serif", 10),
        ).pack(side="left", padx=(4, 0))

        add_entry.bind("<Return>", lambda e: add_option())

        bottom_frame = tk.Frame(dlg, bg=C["base"])
        bottom_frame.pack(fill="x", padx=16, pady=(4, 12))

        HoverButton(
            bottom_frame, text=" Delete Selected ",
            command=delete_selected,
            bg=C["red"], fg=C["crust"], relief="flat", padx=8, pady=4,
            hover_bg=C["red"], hover_fg=C["crust"],
            font=("sans-serif", 10),
        ).pack(side="left")

        HoverButton(
            bottom_frame, text=" Close ", command=dlg.destroy,
            bg=C["surface1"], fg=C["text"], relief="flat", padx=8, pady=4,
            hover_bg=C["surface2"], font=("sans-serif", 10),
        ).pack(side="right")

    # ── VM Selection ──────────────────────────────────────────────────────────
    def _get_selected_vms(self):
        vms = []
        for iid in self.vm_tree.get_children(""):
            values = self.vm_tree.item(iid, "values")
            if values[0] != "☑":
                continue
            status = (
                values[6].replace("● ", "").replace("○ ", "").strip()
            )
            vms.append({
                "vmid": values[1], "name": values[2], "node": values[3],
                "pool": values[4], "snaps": values[5], "status": status,
            })
        return vms

    def _get_selected_vm(self):
        """Get a single selected VM from tree selection (click)."""
        sel = self.vm_tree.selection()
        if not sel:
            return None
        if len(sel) > 1:
            messagebox.showinfo(
                "Single Selection",
                "Please select a single VM for this action.",
                parent=self,
            )
            return None
        values = self.vm_tree.item(sel[0], "values")
        status = values[6].replace("● ", "").replace("○ ", "").strip()
        return {
            "vmid": values[1], "name": values[2], "node": values[3],
            "pool": values[4], "snaps": values[5], "status": status,
        }

    def _on_vm_double_click(self, event):
        region = self.vm_tree.identify_region(event.x, event.y)
        if region != "cell":
            return
        col_id = self.vm_tree.identify_column(event.x)
        display_idx = int(col_id.replace("#", "")) - 1
        if 0 <= display_idx < len(self._display_columns):
            if self._display_columns[display_idx] in ("check", "notes"):
                return
        self._launch_spice()

    # ── SPICE Launch ──────────────────────────────────────────────────────────
    def _launch_spice(self):
        vm = self._get_selected_vm()
        if not vm:
            return
        if vm["status"] != "running":
            messagebox.showwarning(
                "VM Not Running",
                f"VM {vm['vmid']} ({vm['name']}) is not running.",
                parent=self,
            )
            return

        cluster = self.current_cluster
        auth = self._get_auth(cluster)
        if not auth:
            return

        self.status_label.config(
            text=f"⏳  Connecting to {vm['name']}...", fg=C["yellow"]
        )
        self.update_idletasks()

        def connect():
            data = api_request(
                cluster["host"],
                f"/api2/json/nodes/{vm['node']}"
                f"/qemu/{vm['vmid']}/spiceproxy",
                method="POST", auth=auth,
            )
            spice_data = data.get("data")

            if "error" in data or not spice_data or not spice_data.get("type"):
                err = data.get("error", "Unknown Error")
                self.after(0, lambda: (
                    self.status_label.config(
                        text="✗  Connection failed", fg=C["red"]
                    ),
                    messagebox.showerror(
                        "SPICE Error",
                        f"Failed to get SPICE config:\n{err}",
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
                    for key in (
                        "type", "host", "port", "tls-port", "password",
                        "proxy", "host-subject", "ca",
                    ):
                        f.write(f"{key}={spice_data.get(key, '')}\n")
                    f.write(
                        "toggle-fullscreen=shift+f11\n"
                        "release-cursor=shift+f12\n"
                        "secure-attention=ctrl+alt+end\n"
                        "delete-this-file=1\n"
                    )

                os.chmod(vv_path, 0o600)

                proc = subprocess.Popen(["remote-viewer", vv_path])
                def _cleanup_vv(p=proc, path=vv_path):
                    p.wait()
                    try:
                        os.unlink(path)
                    except OSError:
                        pass
                threading.Thread(target=_cleanup_vv, daemon=True).start()
                self.after(0, lambda: self.status_label.config(
                    text=f"✓  Connected to {vm['name']} ({vm['vmid']})",
                    fg=C["green"],
                ))
            except FileNotFoundError:
                # Clean up .vv file (contains SPICE password) if launch failed
                if vv_path:
                    try:
                        os.unlink(vv_path)
                    except OSError:
                        pass
                mgr = detect_pkg_manager()
                hint = (
                    f"sudo {mgr} install virt-viewer"
                    if mgr else "Install virt-viewer"
                )
                self.after(0, lambda: (
                    self.status_label.config(
                        text="✗  remote-viewer not found", fg=C["red"]
                    ),
                    messagebox.showerror(
                        "Missing Dependency",
                        f"remote-viewer not found.\n{hint}",
                        parent=self,
                    ),
                ))

        threading.Thread(target=connect, daemon=True).start()

    # ── Power Actions ─────────────────────────────────────────────────────────
    def _vm_power_action(self, action, action_label):
        vms = self._get_selected_vms()
        if not vms:
            messagebox.showinfo(
                "No Selection", "Select one or more VMs first.", parent=self
            )
            return

        if action == "start":
            valid = [v for v in vms if v["status"] != "running"]
            skipped = [v for v in vms if v["status"] == "running"]
        else:
            valid = [v for v in vms if v["status"] == "running"]
            skipped = [v for v in vms if v["status"] != "running"]

        if not valid:
            messagebox.showinfo(
                "Already in State",
                "All selected VMs are already in the target state.",
                parent=self,
            )
            return

        vm_names = ", ".join(f"{v['name']} ({v['vmid']})" for v in valid)

        if action == "stop":
            if not messagebox.askyesno(
                "Force Stop",
                f"Force stop {len(valid)} VM(s)?\n\n{vm_names}\n\n"
                "Unsaved data may be lost.",
                parent=self,
            ):
                return
        elif action == "shutdown":
            if not messagebox.askyesno(
                "Shutdown",
                f"Send shutdown signal to {len(valid)} VM(s)?\n\n{vm_names}",
                parent=self,
            ):
                return
        elif action == "reboot":
            if not messagebox.askyesno(
                "Reboot",
                f"Reboot {len(valid)} VM(s)?\n\n{vm_names}",
                parent=self,
            ):
                return
        elif action == "start" and len(valid) > 1:
            if not messagebox.askyesno(
                "Start VMs", f"Start {len(valid)} VM(s)?\n\n{vm_names}",
                parent=self,
            ):
                return

        cluster = self.current_cluster
        auth = self._get_auth(cluster)
        if not auth:
            return

        self.status_label.config(
            text=f"⏳  {action_label} {len(valid)} VM(s)...", fg=C["yellow"]
        )
        self.update_idletasks()

        # Capture auth for polling thread
        poll_auth = auth

        def do_action():
            errors = []
            for vm in valid:
                data = api_request(
                    cluster["host"],
                    f"/api2/json/nodes/{vm['node']}"
                    f"/qemu/{vm['vmid']}/status/{action}",
                    method="POST", auth=auth,
                )
                err = data.get("error")
                if err and "already" not in str(err).lower():
                    errors.append(f"{vm['name']}: {err}")

            def on_done():
                if errors:
                    self.status_label.config(
                        text="✗  Some actions failed", fg=C["red"]
                    )
                    messagebox.showerror(
                        "Errors",
                        f"{action_label} failed for:\n\n" + "\n".join(errors),
                        parent=self,
                    )
                else:
                    skip_note = ""
                    if skipped:
                        skip_note = (
                            f" (skipped: "
                            f"{', '.join(v['name'] for v in skipped)})"
                        )
                    self.status_label.config(
                        text=f"✓  {action_label} signal sent to "
                        f"{len(valid)} VM(s){skip_note}",
                        fg=C["green"],
                    )

            expected = {
                str(vm["vmid"]): (
                    "running" if action in ("start", "reboot")
                    else "stopped"
                )
                for vm in valid
            }
            self.after(0, on_done)
            self.after(0, lambda: self._poll_until_changed(
                expected, auth=poll_auth
            ))

        threading.Thread(target=do_action, daemon=True).start()

    def _start_vm(self):
        self._vm_power_action("start", "Starting")

    def _shutdown_vm(self):
        self._vm_power_action("shutdown", "Shutting down")

    def _stop_vm(self):
        self._vm_power_action("stop", "Force stopping")

    def _reboot_vm(self):
        self._vm_power_action("reboot", "Rebooting")

    # ── Quick Rollback ────────────────────────────────────────────────────────
    def _quick_rollback(self):
        vm = self._get_selected_vm()
        if not vm:
            return

        cluster = self.current_cluster
        auth = self._get_auth(cluster)
        if not auth:
            return

        self.status_label.config(
            text=f"⏳  Finding latest snapshot for {vm['name']}...",
            fg=C["yellow"],
        )
        self.update_idletasks()

        # Capture auth for threads
        saved_auth = auth

        def fetch_and_rollback():
            data = api_request(
                cluster["host"],
                f"/api2/json/nodes/{vm['node']}"
                f"/qemu/{vm['vmid']}/snapshot",
                auth=saved_auth,
            )
            if "error" in data:
                self.after(0, lambda d=data: (
                    self.status_label.config(
                        text=f"✗ {d['error']}", fg=C["red"]
                    ),
                    messagebox.showerror("Error", d["error"], parent=self),
                ))
                return

            snaps = [
                s for s in data.get("data", [])
                if s.get("name") != "current"
            ]
            if not snaps:
                self.after(0, lambda: (
                    self.status_label.config(
                        text="✗ No snapshots found", fg=C["overlay0"]
                    ),
                    messagebox.showinfo(
                        "No Snapshots",
                        f"No snapshots found for VM {vm['vmid']}.",
                        parent=self,
                    ),
                ))
                return

            latest = max(snaps, key=lambda s: s.get("snaptime", 0))
            snap_name = latest.get("name")

            def confirm_and_execute():
                if vm["status"] == "running":
                    msg = (
                        f"VM {vm['vmid']} is currently running.\n"
                        f"Rolling back will stop it.\n\n"
                        f"Rollback to latest snapshot '{snap_name}'?"
                    )
                else:
                    msg = (
                        f"Rollback VM {vm['vmid']} to latest snapshot "
                        f"'{snap_name}'?\nCurrent state will be lost."
                    )

                if not messagebox.askyesno(
                    "Confirm Quick Rollback", msg, parent=self
                ):
                    self.status_label.config(
                        text="◈ Quick rollback cancelled", fg=C["overlay0"]
                    )
                    return

                self.status_label.config(
                    text=f"⏳  Rolling back to '{snap_name}'...",
                    fg=C["yellow"],
                )
                self.update_idletasks()

                def do_rollback():
                    rb_data = api_request(
                        cluster["host"],
                        f"/api2/json/nodes/{vm['node']}"
                        f"/qemu/{vm['vmid']}/snapshot/{urllib.parse.quote(snap_name, safe='')}/rollback",
                        method="POST", auth=saved_auth,
                    )
                    if "error" in rb_data:
                        self.after(0, lambda d=rb_data: (
                            self.status_label.config(
                                text="✗  Rollback failed", fg=C["red"]
                            ),
                            messagebox.showerror(
                                "Rollback Failed", d["error"], parent=self
                            ),
                        ))
                    else:
                        self.after(0, lambda: self.status_label.config(
                            text=f"✓  Rolled back to '{snap_name}'",
                            fg=C["green"],
                        ))
                        self.after(0, lambda: self._poll_until_changed(
                            {str(vm["vmid"]): "stopped"}, auth=saved_auth
                        ))

                threading.Thread(target=do_rollback, daemon=True).start()

            self.after(0, confirm_and_execute)

        threading.Thread(target=fetch_and_rollback, daemon=True).start()

    # ── Polling ───────────────────────────────────────────────────────────────
    def _poll_until_changed(
        self, expected_changes, auth=None, attempts=0, max_attempts=12
    ):
        """Poll every 10s until VM statuses match expected, or timeout."""
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

        # Capture for thread
        saved_auth = auth

        def check():
            data = api_request(
                cluster["host"],
                "/api2/json/cluster/resources?type=vm", auth=saved_auth,
            )
            if "error" in data:
                return

            vms = data.get("data", [])
            all_changed = all(
                next(
                    (v for v in vms if str(v.get("vmid")) == vmid), {}
                ).get("status") == expected
                for vmid, expected in expected_changes.items()
            )

            if all_changed:
                self.after(0, self._refresh_vms)
            else:
                self.after(0, lambda: self.after(
                    10000,
                    lambda: self._poll_until_changed(
                        expected_changes, auth=saved_auth,
                        attempts=attempts + 1, max_attempts=max_attempts,
                    ),
                ))

        threading.Thread(target=check, daemon=True).start()

    def _poll_snap_changed(
        self, vmid, node, old_count, auth=None, attempts=0, max_attempts=12
    ):
        """Poll every 10s until snapshot count changes, or timeout."""
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

            current_count = len(
                [s for s in snap_data.get("data", [])
                 if s.get("name") != "current"]
            )

            if current_count != old_count:
                self.after(0, self._refresh_vms)
            else:
                self.after(0, lambda: self.after(
                    10000,
                    lambda: self._poll_snap_changed(
                        vmid, node, old_count, auth=saved_auth,
                        attempts=attempts + 1, max_attempts=max_attempts,
                    ),
                ))

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

        SnapshotDialog(
            self, vm, self.current_cluster, auth,
            on_change=lambda vmid, node, old_count:
                self._poll_snap_changed(
                    vmid, node, old_count, auth=saved_auth
                ),
        )

    # ── Export Desktop ────────────────────────────────────────────────────────
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

    # ── Install to App Menu ───────────────────────────────────────────────────
    def _install_to_app_menu(self):
        icon_dlg = IconPickerDialog(self)
        if icon_dlg.result is None:
            return

        icon_value = icon_dlg.result
        script_name = "proxmox-spice-manager.py"
        installed_script = Path.home() / script_name
        desktop_dir = Path.home() / ".local" / "share" / "applications"
        desktop_file = desktop_dir / "proxmox-spice-manager.desktop"

        # Copy custom icon to persistent location
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

        # Copy script
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

        # Create .desktop entry
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
    app = ProxmoxSpiceManager()
    app.mainloop()
