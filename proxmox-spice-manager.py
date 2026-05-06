#!/usr/bin/env python3
"""
Proxmox SPICE Connection Manager
A GUI app to manage and launch SPICE console sessions to Proxmox VMs.
Connections are saved to ~/.config/proxmox-spice/connections.json

Dependencies: python3-tkinter, curl, jq, remote-viewer
Install on Fedora: sudo dnf install python3-tkinter virt-viewer
"""

import json
import os
import shutil
import subprocess
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "proxmox-spice"
CONFIG_FILE = CONFIG_DIR / "connections.json"

REQUIRED_DEPS = {
    "curl": {
        "cmd": "curl",
        "desc": "HTTP client for Proxmox API calls",
        "install": "sudo dnf install curl",
    },
    "jq": {
        "cmd": "jq",
        "desc": "JSON processor",
        "install": "sudo dnf install jq",
    },
    "remote-viewer": {
        "cmd": "remote-viewer",
        "desc": "SPICE client (virt-viewer)",
        "install": "sudo dnf install virt-viewer",
    },
}


def check_deps():
    """Check which required dependencies are installed. Returns (all_ok, results_dict)."""
    results = {}
    all_ok = True
    for name, info in REQUIRED_DEPS.items():
        found = shutil.which(info["cmd"]) is not None
        results[name] = found
        if not found:
            all_ok = False
    return all_ok, results

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

# Active theme — mutable reference
C = dict(THEMES["Catppuccin Mocha"])


def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {"clusters": [], "theme": "Catppuccin Mocha"}
    return {"clusters": [], "theme": "Catppuccin Mocha"}


def save_config(config):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)


def api_request(host, endpoint, method="GET", auth=None):
    cmd = ["curl", "-s", "-k"]
    if auth.get("token_id") and auth.get("token_secret"):
        cmd += ["-H", f"Authorization: PVEAPIToken={auth['token_id']}={auth['token_secret']}"]
    elif auth.get("ticket"):
        cmd += ["-b", f"PVEAuthCookie={auth['ticket']}"]
        if auth.get("csrf"):
            cmd += ["-H", f"CSRFPreventionToken: {auth['csrf']}"]
    if method == "POST":
        cmd += ["-X", "POST"]
    cmd.append(f"{host}{endpoint}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return json.loads(result.stdout)
    except Exception as e:
        return {"error": str(e)}


def authenticate_password(host, username, password):
    cmd = [
        "curl", "-s", "-k",
        "-d", f"username={username}",
        "--data-urlencode", f"password={password}",
        f"{host}/api2/json/access/ticket"
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        data = json.loads(result.stdout)
        if data.get("data", {}).get("ticket"):
            return {
                "ticket": data["data"]["ticket"],
                "csrf": data["data"].get("CSRFPreventionToken", "")
            }
    except Exception:
        pass
    return None


# ─── Hover button ─────────────────────────────────────────────────────────────
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

    def update_colors(self, bg, fg, hover_bg, hover_fg):
        self._normal_bg = bg
        self._normal_fg = fg
        self._hover_bg = hover_bg
        self._hover_fg = hover_fg
        self.config(bg=bg, fg=fg, activebackground=hover_bg, activeforeground=hover_fg)


# ─── Dialogs ─────────────────────────────────────────────────────────────────
class ClusterDialog(tk.Toplevel):
    def __init__(self, parent, cluster=None):
        super().__init__(parent)
        self.result = None
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

        lbl = {"bg": C["base"], "fg": C["subtext0"], "font": ("sans-serif", 9)}
        entry_cfg = {
            "bg": C["surface0"], "fg": C["text"], "insertbackground": C["text"],
            "relief": "flat", "font": ("monospace", 10), "highlightthickness": 1,
            "highlightcolor": C["blue"], "highlightbackground": C["surface1"]
        }

        tk.Label(main, text="CLUSTER NAME", **lbl).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.name_entry = tk.Entry(main, **entry_cfg)
        self.name_entry.grid(row=1, column=0, sticky="ew", pady=(0, 16), ipady=6)

        tk.Label(main, text="HOST URL", **lbl).grid(row=2, column=0, sticky="w", pady=(0, 4))
        self.host_entry = tk.Entry(main, **entry_cfg)
        self.host_entry.grid(row=3, column=0, sticky="ew", pady=(0, 16), ipady=6)

        tk.Label(main, text="AUTHENTICATION", **lbl).grid(row=4, column=0, sticky="w", pady=(0, 4))
        self.auth_var = tk.StringVar(value="token")
        auth_frame = tk.Frame(main, bg=C["base"])
        auth_frame.grid(row=5, column=0, sticky="w", pady=(0, 12))

        radio_cfg = {"bg": C["base"], "fg": C["text"], "selectcolor": C["surface0"],
                     "activebackground": C["base"], "activeforeground": C["text"],
                     "font": ("sans-serif", 10), "command": self._toggle_auth}
        tk.Radiobutton(auth_frame, text="API Token", variable=self.auth_var,
                        value="token", **radio_cfg).pack(side="left", padx=(0, 20))
        tk.Radiobutton(auth_frame, text="Password", variable=self.auth_var,
                        value="password", **radio_cfg).pack(side="left")

        self.token_frame = tk.Frame(main, bg=C["base"])
        self.token_frame.grid(row=6, column=0, sticky="ew")
        self.token_frame.columnconfigure(0, weight=1)

        tk.Label(self.token_frame, text="TOKEN ID  (user@realm!token)", **lbl).pack(anchor="w", pady=(0, 4))
        self.token_id_entry = tk.Entry(self.token_frame, **entry_cfg)
        self.token_id_entry.pack(fill="x", pady=(0, 10), ipady=6)

        tk.Label(self.token_frame, text="TOKEN SECRET", **lbl).pack(anchor="w", pady=(0, 4))
        self.token_secret_entry = tk.Entry(self.token_frame, **entry_cfg, show="•")
        self.token_secret_entry.pack(fill="x", pady=(0, 8), ipady=6)

        self.pass_frame = tk.Frame(main, bg=C["base"])
        self.pass_frame.columnconfigure(0, weight=1)
        tk.Label(self.pass_frame, text="USERNAME", **lbl).pack(anchor="w", pady=(0, 4))
        self.user_entry = tk.Entry(self.pass_frame, **entry_cfg)
        self.user_entry.pack(fill="x", pady=(0, 8), ipady=6)
        self.user_entry.insert(0, "root@pam")

        btn_frame = tk.Frame(main, bg=C["base"])
        btn_frame.grid(row=7, column=0, sticky="e", pady=(20, 0))

        HoverButton(btn_frame, text="Cancel", command=self.destroy,
                    bg=C["surface1"], fg=C["text"], relief="flat", padx=18, pady=6,
                    hover_bg=C["surface2"], font=("sans-serif", 10)).pack(side="right", padx=(8, 0))
        HoverButton(btn_frame, text="  Save  ", command=self._save,
                    bg=C["blue"], fg=C["crust"], relief="flat", padx=18, pady=6,
                    hover_bg=C["sapphire"], hover_fg=C["crust"],
                    font=("sans-serif", 10, "bold")).pack(side="right")

        if cluster:
            self.name_entry.insert(0, cluster.get("name", ""))
            self.host_entry.insert(0, cluster.get("host", ""))
            self.auth_var.set(cluster.get("auth_method", "token"))
            self.token_id_entry.insert(0, cluster.get("token_id", ""))
            self.token_secret_entry.insert(0, cluster.get("token_secret", ""))
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
            messagebox.showwarning("Missing Fields", "Name and Host URL are required.", parent=self)
            return
        self.result = {
            "name": name, "host": host,
            "auth_method": self.auth_var.get(),
            "token_id": self.token_id_entry.get().strip(),
            "token_secret": self.token_secret_entry.get().strip(),
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
            "relief": "flat", "font": ("monospace", 10), "highlightthickness": 1,
            "highlightcolor": C["blue"], "highlightbackground": C["surface1"]
        }

        tk.Label(main, text=f"Password for {username}", bg=C["base"], fg=C["text"],
                 font=("sans-serif", 10)).pack(anchor="w", pady=(0, 2))
        tk.Label(main, text=host, bg=C["base"], fg=C["overlay0"],
                 font=("sans-serif", 9)).pack(anchor="w", pady=(0, 10))

        self.pw_entry = tk.Entry(main, **entry_cfg, show="•")
        self.pw_entry.pack(fill="x", ipady=6)
        self.pw_entry.bind("<Return>", lambda e: self._submit())

        btn_frame = tk.Frame(main, bg=C["base"])
        btn_frame.pack(anchor="e", pady=(14, 0))

        HoverButton(btn_frame, text="Cancel", command=self.destroy,
                    bg=C["surface1"], fg=C["text"], relief="flat", padx=16, pady=5,
                    hover_bg=C["surface2"]).pack(side="right", padx=(8, 0))
        HoverButton(btn_frame, text="  Connect  ", command=self._submit,
                    bg=C["blue"], fg=C["crust"], relief="flat", padx=16, pady=5,
                    hover_bg=C["sapphire"], hover_fg=C["crust"],
                    font=("sans-serif", 10, "bold")).pack(side="right")

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
            tk.Radiobutton(frame, text=f"  {label}", variable=self.icon_var, value=icon_name,
                            bg=C["base"], fg=C["text"], selectcolor=C["surface0"],
                            activebackground=C["base"], activeforeground=C["text"],
                            font=("sans-serif", 10), anchor="w").pack(side="left")
        icon_grid.columnconfigure(0, weight=1)
        icon_grid.columnconfigure(1, weight=1)

        tk.Frame(main, bg=C["surface0"], height=1).pack(fill="x", pady=(4, 16))

        tk.Label(main, text="CUSTOM ICON", **lbl).pack(anchor="w", pady=(0, 8))

        custom_frame = tk.Frame(main, bg=C["base"])
        custom_frame.pack(fill="x", pady=(0, 8))

        self.custom_var = tk.BooleanVar(value=False)
        tk.Checkbutton(custom_frame, text="  Use custom icon file", variable=self.custom_var,
                        bg=C["base"], fg=C["text"], selectcolor=C["surface0"],
                        activebackground=C["base"], activeforeground=C["text"],
                        font=("sans-serif", 10), command=self._toggle_custom).pack(side="left")

        self.custom_path_frame = tk.Frame(main, bg=C["base"])
        entry_cfg = {
            "bg": C["surface0"], "fg": C["text"], "insertbackground": C["text"],
            "relief": "flat", "font": ("monospace", 10), "highlightthickness": 1,
            "highlightcolor": C["blue"], "highlightbackground": C["surface1"]
        }

        path_row = tk.Frame(self.custom_path_frame, bg=C["base"])
        path_row.pack(fill="x", pady=(4, 4))
        self.icon_path_entry = tk.Entry(path_row, **entry_cfg)
        self.icon_path_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        HoverButton(path_row, text=" Browse ", command=self._browse_icon,
                    bg=C["surface0"], fg=C["subtext0"], relief="flat", padx=12, pady=4,
                    hover_bg=C["surface1"], hover_fg=C["text"],
                    font=("sans-serif", 9)).pack(side="right")

        tk.Label(self.custom_path_frame, text="PNG, SVG, or ICO file",
                 bg=C["base"], fg=C["overlay0"], font=("sans-serif", 8)).pack(anchor="w")
        self.preview_label = tk.Label(self.custom_path_frame, text="", bg=C["base"],
                                       fg=C["overlay0"], font=("sans-serif", 9))
        self.preview_label.pack(anchor="w", pady=(4, 0))

        btn_frame = tk.Frame(main, bg=C["base"])
        btn_frame.pack(side="bottom", anchor="e", pady=(16, 0))
        HoverButton(btn_frame, text="Cancel", command=self._cancel,
                    bg=C["surface1"], fg=C["text"], relief="flat", padx=18, pady=6,
                    hover_bg=C["surface2"], font=("sans-serif", 10)).pack(side="right", padx=(8, 0))
        HoverButton(btn_frame, text="  Install  ", command=self._confirm,
                    bg=C["green"], fg=C["crust"], relief="flat", padx=18, pady=6,
                    hover_bg=C["teal"], hover_fg=C["crust"],
                    font=("sans-serif", 10, "bold")).pack(side="right")

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
            filetypes=[("Image files", "*.png *.svg *.ico *.xpm"), ("All files", "*.*")])
        if path:
            self.icon_path_entry.delete(0, "end")
            self.icon_path_entry.insert(0, path)
            self.preview_label.config(text=f"Selected: {Path(path).name}")

    def _confirm(self):
        if self.custom_var.get():
            path = self.icon_path_entry.get().strip()
            if not path:
                messagebox.showwarning("No Icon", "Enter a path or browse for an icon file.", parent=self)
                return
            if not os.path.isfile(path):
                messagebox.showwarning("File Not Found", f"Could not find:\n{path}", parent=self)
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
    """First-run dialog showing dependency status and install instructions."""

    def __init__(self, parent, deps, results):
        super().__init__(parent)
        self.result = False
        self.title("Proxmox SPICE Manager — Setup")
        self.geometry("560x520")
        self.resizable(True, True)
        self.grab_set()
        self.configure(bg=C["base"])
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.focus_force()

        tk.Frame(self, bg=C["peach"], height=3).pack(fill="x")

        main = tk.Frame(self, bg=C["base"], padx=28, pady=20)
        main.pack(fill="both", expand=True)

        tk.Label(main, text="Welcome to Proxmox SPICE Manager",
                 bg=C["base"], fg=C["text"], font=("sans-serif", 13, "bold")).pack(anchor="w", pady=(0, 4))
        tk.Label(main, text="Some required tools are missing. Install them to continue.",
                 bg=C["base"], fg=C["subtext0"], font=("sans-serif", 10)).pack(anchor="w", pady=(0, 20))

        tk.Label(main, text="DEPENDENCIES", bg=C["base"], fg=C["overlay0"],
                 font=("sans-serif", 8, "bold")).pack(anchor="w", pady=(0, 8))

        self.dep_frames = {}
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

            tk.Label(header_row, text=status_icon, bg=C["surface0"], fg=status_color,
                     font=("sans-serif", 12, "bold")).pack(side="left", padx=(0, 8))
            tk.Label(header_row, text=name, bg=C["surface0"], fg=C["text"],
                     font=("sans-serif", 10, "bold")).pack(side="left")

            status_text = "Installed" if found else "Not found"
            tk.Label(header_row, text=f"  —  {status_text}", bg=C["surface0"],
                     fg=status_color, font=("sans-serif", 9)).pack(side="left")

            tk.Label(left, text=info["desc"], bg=C["surface0"], fg=C["subtext0"],
                     font=("sans-serif", 9)).pack(anchor="w", padx=(28, 0))

            if not found:
                install_frame = tk.Frame(left, bg=C["surface0"])
                install_frame.pack(anchor="w", padx=(28, 0), pady=(4, 0))

                pkg = info["install"].split()[-1]
                HoverButton(install_frame, text=f"  ⬇  Install {pkg}  ",
                            command=lambda p=pkg, n=name: self._install_pkg(p, n),
                            bg=C["peach"], fg=C["crust"], relief="flat", padx=10, pady=3,
                            hover_bg=C["yellow"], hover_fg=C["crust"],
                            font=("sans-serif", 9, "bold")).pack(side="left")

            self.dep_frames[name] = row

        missing = [info["install"].split()[-1] for name, info in deps.items() if not results[name]]
        if missing:
            tk.Frame(main, bg=C["surface0"], height=1).pack(fill="x", pady=(12, 12))

            all_pkgs = " ".join(missing)
            HoverButton(main, text=f"  ⬇  Install All Missing ({all_pkgs})  ",
                        command=lambda: self._install_pkg(all_pkgs, None),
                        bg=C["peach"], fg=C["crust"], relief="flat", padx=14, pady=8,
                        hover_bg=C["yellow"], hover_fg=C["crust"],
                        font=("sans-serif", 10, "bold")).pack(fill="x", pady=(0, 4))

        # Buttons at the very bottom
        prereq_btn_frame = tk.Frame(main, bg=C["base"])
        prereq_btn_frame.pack(side="bottom", fill="x", pady=(12, 0))

        HoverButton(prereq_btn_frame, text="Quit", command=self._cancel,
                    bg=C["surface1"], fg=C["text"], relief="flat", padx=18, pady=6,
                    hover_bg=C["surface2"], font=("sans-serif", 10)).pack(side="right", padx=(8, 0))
        HoverButton(prereq_btn_frame, text="  Re-check  ", command=lambda: self._recheck(deps),
                    bg=C["blue"], fg=C["crust"], relief="flat", padx=18, pady=6,
                    hover_bg=C["sapphire"], hover_fg=C["crust"],
                    font=("sans-serif", 10, "bold")).pack(side="right")

        self.deps = deps
        self.results = results
        self.wait_window()

    def _copy_cmd(self, cmd):
        self.clipboard_clear()
        self.clipboard_append(cmd)
        self.update()

    def _install_pkg(self, packages, dep_name):
        """Install packages by opening a terminal with dnf."""
        pkg_list = packages.split()
        # Try common terminal emulators in order of likelihood on Fedora KDE
        terminals = [
            ["konsole", "-e"],
            ["gnome-terminal", "--"],
            ["xfce4-terminal", "-e"],
            ["xterm", "-e"],
        ]

        cmd_str = f"sudo dnf install -y {' '.join(pkg_list)}; echo; echo 'Press Enter to close...'; read"

        launched = False
        for term_cmd in terminals:
            if shutil.which(term_cmd[0]):
                try:
                    subprocess.Popen(term_cmd + ["bash", "-c", cmd_str])
                    launched = True
                    break
                except Exception:
                    continue

        if not launched:
            messagebox.showwarning(
                "No Terminal Found",
                f"Could not find a terminal emulator.\n\n"
                f"Run manually:\n  sudo dnf install {' '.join(pkg_list)}",
                parent=self
            )
            return

        messagebox.showinfo(
            "Installing",
            "A terminal window has opened to install the packages.\n\n"
            "Click Re-check when it's done.",
            parent=self
        )

    def _recheck(self, deps):
        all_ok, results = check_deps()
        self.results = results

        if all_ok:
            self.result = True
            self.destroy()
        else:
            messagebox.showinfo(
                "Still Missing",
                "Some dependencies are still not installed.\n"
                "Run the install command in a terminal, then click Re-check.",
                parent=self
            )

    def _cancel(self):
        self.result = False
        self.destroy()


# ─── Main Application ────────────────────────────────────────────────────────
class ProxmoxSpiceManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Proxmox SPICE Manager")
        self.geometry("1000x640")
        self.configure(bg=C["base"])
        self.minsize(800, 500)

        self.config_data = load_config()
        self.vm_list = []
        self.current_cluster = None
        self.auth_cache = {}

        # Load saved theme
        saved_theme = self.config_data.get("theme", "Catppuccin Mocha")
        if saved_theme in THEMES:
            C.update(THEMES[saved_theme])

        # One-time prerequisite check
        if not self.config_data.get("prereqs_ok"):
            # Show main window briefly so dialogs can attach to it
            self.update_idletasks()
            if not self._check_prereqs():
                self.destroy()
                return
            self.config_data["prereqs_ok"] = True
            save_config(self.config_data)

        self._build_ui()
        self._populate_clusters()

        if self.config_data.get("clusters"):
            self.cluster_listbox.select_set(0)
            self.current_cluster = self.config_data["clusters"][0]
            self.after(100, self._refresh_vms)

    def _check_prereqs(self):
        """Check for required dependencies and show a setup dialog."""
        all_ok, results = check_deps()
        if all_ok:
            return True
        dlg = PrereqDialog(self, REQUIRED_DEPS, results)
        return dlg.result

    def _recheck_prereqs(self):
        """Manual prereq recheck — always shows the dialog with current status."""
        all_ok, results = check_deps()

        if all_ok:
            messagebox.showinfo(
                "All Good",
                "All prerequisites are installed.\n\n"
                "  ✓  curl\n"
                "  ✓  jq\n"
                "  ✓  remote-viewer",
                parent=self
            )
        else:
            dlg = PrereqDialog(self, REQUIRED_DEPS, results)
            if dlg.result:
                self.config_data["prereqs_ok"] = True
                save_config(self.config_data)

    def _build_ui(self):
        # Destroy existing widgets if rebuilding
        for widget in self.winfo_children():
            widget.destroy()

        self.configure(bg=C["base"])

        # ── Top header bar ──
        header = tk.Frame(self, bg=C["crust"], height=52)
        header.pack(fill="x")
        header.pack_propagate(False)

        title_frame = tk.Frame(header, bg=C["crust"])
        title_frame.pack(side="left", padx=16)
        tk.Label(title_frame, text="◈", bg=C["crust"], fg=C["mauve"],
                 font=("sans-serif", 18)).pack(side="left", padx=(0, 8))
        tk.Label(title_frame, text="Proxmox SPICE Manager", bg=C["crust"], fg=C["text"],
                 font=("sans-serif", 12, "bold")).pack(side="left")

        header_btn = {"bg": C["crust"], "fg": C["subtext0"], "relief": "flat",
                      "font": ("sans-serif", 9), "padx": 10, "pady": 4,
                      "activebackground": C["mantle"], "activeforeground": C["text"]}

        HoverButton(header, text="⚙  Install to App Menu", command=self._install_to_app_menu,
                    hover_bg=C["mantle"], hover_fg=C["text"], **header_btn).pack(side="right", padx=(0, 12))

        HoverButton(header, text="🔍  Check Prerequisites", command=self._recheck_prereqs,
                    hover_bg=C["mantle"], hover_fg=C["text"], **header_btn).pack(side="right", padx=(0, 4))

        # Theme selector in header
        theme_frame = tk.Frame(header, bg=C["crust"])
        theme_frame.pack(side="right", padx=(0, 8))

        tk.Label(theme_frame, text="Theme:", bg=C["crust"], fg=C["overlay0"],
                 font=("sans-serif", 9)).pack(side="left", padx=(0, 6))

        current_theme = self.config_data.get("theme", "Catppuccin Mocha")
        self.theme_var = tk.StringVar(value=current_theme)
        theme_menu = ttk.Combobox(theme_frame, textvariable=self.theme_var,
                                   values=list(THEMES.keys()), state="readonly",
                                   width=18, font=("sans-serif", 9))
        theme_menu.pack(side="left")
        theme_menu.bind("<<ComboboxSelected>>", self._on_theme_change)

        # Style the combobox
        combo_style = ttk.Style()
        combo_style.theme_use("clam")
        combo_style.configure("TCombobox",
                               fieldbackground=C["surface0"], background=C["surface1"],
                               foreground=C["text"], arrowcolor=C["text"],
                               borderwidth=0, relief="flat")
        combo_style.map("TCombobox",
                         fieldbackground=[("readonly", C["surface0"])],
                         foreground=[("readonly", C["text"])],
                         background=[("readonly", C["surface1"])])

        # Accent line
        tk.Frame(self, bg=C["mauve"], height=2).pack(fill="x")

        # ── Body ──
        body = tk.Frame(self, bg=C["base"])
        body.pack(fill="both", expand=True)

        # ── Sidebar ──
        sidebar = tk.Frame(body, bg=C["mantle"], width=200)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="CLUSTERS", bg=C["mantle"], fg=C["overlay0"],
                 font=("sans-serif", 8, "bold"), anchor="w").pack(fill="x", padx=14, pady=(14, 6))
        tk.Frame(sidebar, bg=C["surface0"], height=1).pack(fill="x", padx=12, pady=(0, 6))

        self.cluster_listbox = tk.Listbox(
            sidebar, bg=C["mantle"], fg=C["text"], selectbackground=C["surface0"],
            selectforeground=C["blue"], relief="flat", font=("sans-serif", 10),
            highlightthickness=0, activestyle="none", borderwidth=0
        )
        self.cluster_listbox.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.cluster_listbox.bind("<<ListboxSelect>>", self._on_cluster_select)

        tk.Frame(sidebar, bg=C["surface0"], height=1).pack(fill="x", padx=12)

        btn_bar = tk.Frame(sidebar, bg=C["mantle"])
        btn_bar.pack(fill="x", padx=8, pady=10)

        sb_btn = {"bg": C["surface0"], "fg": C["subtext0"], "relief": "flat",
                  "padx": 10, "pady": 4, "font": ("sans-serif", 9),
                  "activebackground": C["surface1"], "activeforeground": C["text"]}

        HoverButton(btn_bar, text="+ Add", command=self._add_cluster,
                    hover_bg=C["surface1"], hover_fg=C["text"], **sb_btn).pack(side="left", padx=(0, 4))
        HoverButton(btn_bar, text="Edit", command=self._edit_cluster,
                    hover_bg=C["surface1"], hover_fg=C["text"], **sb_btn).pack(side="left", padx=(0, 4))
        HoverButton(btn_bar, text="Remove", command=self._remove_cluster,
                    hover_bg=C["surface1"], hover_fg=C["red"], **sb_btn).pack(side="left")

        tk.Frame(body, bg=C["surface0"], width=1).pack(side="left", fill="y")

        # ── Main content ──
        content = tk.Frame(body, bg=C["base"])
        content.pack(side="right", fill="both", expand=True)

        toolbar = tk.Frame(content, bg=C["base"])
        toolbar.pack(fill="x", padx=16, pady=(14, 0))

        self.status_label = tk.Label(toolbar, text="Select a cluster to view VMs",
                                      bg=C["base"], fg=C["overlay0"],
                                      font=("sans-serif", 10), anchor="w")
        self.status_label.pack(side="left")

        HoverButton(toolbar, text="↻  Refresh", command=self._refresh_vms,
                    bg=C["surface0"], fg=C["subtext0"], relief="flat", padx=12, pady=4,
                    hover_bg=C["surface1"], hover_fg=C["text"],
                    font=("sans-serif", 9)).pack(side="right")

        # VM Table
        table_frame = tk.Frame(content, bg=C["base"])
        table_frame.pack(fill="both", expand=True, padx=16, pady=(10, 0))

        columns = ("vmid", "name", "node", "pool", "status")
        self.vm_tree = ttk.Treeview(table_frame, columns=columns, show="headings",
                                      selectmode="browse", height=12)

        style = ttk.Style()
        style.configure("Treeview",
                         background=C["surface0"], foreground=C["text"],
                         fieldbackground=C["surface0"], rowheight=32,
                         font=("sans-serif", 10), borderwidth=0)
        style.configure("Treeview.Heading",
                         background=C["surface1"], foreground=C["subtext0"],
                         font=("sans-serif", 9, "bold"), borderwidth=0, relief="flat")
        style.map("Treeview",
                   background=[("selected", C["surface1"])],
                   foreground=[("selected", C["blue"])])
        style.map("Treeview.Heading", background=[("active", C["surface2"])])

        for col in columns:
            self.vm_tree.heading(col, text=col.upper(),
                                  command=lambda c=col: self._sort_tree(c))

        self.vm_tree.column("vmid", width=70, minwidth=50, anchor="center")
        self.vm_tree.column("name", width=240, minwidth=120)
        self.vm_tree.column("node", width=130, minwidth=80)
        self.vm_tree.column("pool", width=120, minwidth=60)
        self.vm_tree.column("status", width=110, minwidth=70, anchor="center")

        self._tree_sort_col = None
        self._tree_sort_asc = True

        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=self.vm_tree.yview)
        style.configure("Vertical.TScrollbar",
                         background=C["surface0"], troughcolor=C["surface0"],
                         arrowcolor=C["overlay0"], borderwidth=0)
        self.vm_tree.configure(yscrollcommand=scrollbar.set)

        self.vm_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.vm_tree.bind("<Double-1>", self._on_vm_double_click)

        # ── Bottom action bar ──
        tk.Frame(content, bg=C["surface0"], height=1).pack(fill="x", padx=16)

        bottom = tk.Frame(content, bg=C["base"])
        bottom.pack(fill="x", padx=16, pady=12)

        HoverButton(bottom, text="  ▶  Launch SPICE Console  ", command=self._launch_spice,
                    bg=C["green"], fg=C["crust"], relief="flat", padx=20, pady=8,
                    hover_bg=C["teal"], hover_fg=C["crust"],
                    font=("sans-serif", 11, "bold")).pack(side="right")

        HoverButton(bottom, text="  Export .desktop  ", command=self._export_desktop,
                    bg=C["surface0"], fg=C["subtext0"], relief="flat", padx=14, pady=8,
                    hover_bg=C["surface1"], hover_fg=C["text"],
                    font=("sans-serif", 10)).pack(side="right", padx=(0, 10))

    # ── Theme switching ───────────────────────────────────────────────────────
    def _on_theme_change(self, event=None):
        theme_name = self.theme_var.get()
        if theme_name in THEMES:
            C.update(THEMES[theme_name])
            self.config_data["theme"] = theme_name
            save_config(self.config_data)

            # Remember state
            selected_cluster_idx = None
            sel = self.cluster_listbox.curselection()
            if sel:
                selected_cluster_idx = sel[0]

            # Rebuild UI
            self._build_ui()
            self._populate_clusters()

            # Restore selection
            if selected_cluster_idx is not None:
                self.cluster_listbox.select_set(selected_cluster_idx)
                clusters = self.config_data.get("clusters", [])
                if selected_cluster_idx < len(clusters):
                    self.current_cluster = clusters[selected_cluster_idx]

            # Re-fetch VMs if a cluster was selected
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
            messagebox.showinfo("No Selection", "Select a cluster to edit.")
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
        if messagebox.askyesno("Confirm", f"Remove cluster '{cluster['name']}'?"):
            self.config_data["clusters"].pop(idx)
            save_config(self.config_data)
            self._populate_clusters()
            self.vm_tree.delete(*self.vm_tree.get_children())
            self.current_cluster = None
            self.status_label.config(text="Select a cluster to view VMs")

    # ── Auth ──────────────────────────────────────────────────────────────────
    def _get_auth(self, cluster):
        name = cluster["name"]
        if cluster["auth_method"] == "token":
            if cluster.get("token_id") and cluster.get("token_secret"):
                return {"token_id": cluster["token_id"], "token_secret": cluster["token_secret"]}
            else:
                messagebox.showerror("Auth Error", "Token ID and Secret are required.", parent=self)
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
        else:
            messagebox.showerror("Auth Failed", "Could not authenticate. Check credentials.", parent=self)
            return None

    # ── VM list ───────────────────────────────────────────────────────────────
    def _refresh_vms(self):
        if not self.current_cluster:
            return
        self.status_label.config(text="⏳  Loading VMs...", fg=C["yellow"])
        self.update_idletasks()

        def fetch():
            cluster = self.current_cluster
            auth = self._get_auth(cluster)
            if not auth:
                self.after(0, lambda: self.status_label.config(
                    text="✗  Authentication failed", fg=C["red"]))
                return

            data = api_request(cluster["host"], "/api2/json/cluster/resources?type=vm", auth=auth)
            all_vms = data.get("data", [])

            if not all_vms:
                self.after(0, lambda: (
                    self.vm_tree.delete(*self.vm_tree.get_children()),
                    self.status_label.config(text="✗  No VMs found (check permissions)", fg=C["red"])
                ))
                return

            qemu_vms = [v for v in all_vms if v.get("type") == "qemu"]
            self.after(0, lambda: self.status_label.config(
                text=f"⏳  Checking {len(qemu_vms)} VMs for SPICE...", fg=C["yellow"]))

            spice_vms = []
            for vm in qemu_vms:
                vmid = vm.get("vmid", "?")
                node = vm.get("node", "?")
                config = api_request(
                    cluster["host"],
                    f"/api2/json/nodes/{node}/qemu/{vmid}/config",
                    auth=auth
                )
                vga = config.get("data", {}).get("vga", "")
                if "qxl" in str(vga).lower() or "spice" in str(vga).lower():
                    spice_vms.append(vm)

            def update_ui():
                self.vm_tree.delete(*self.vm_tree.get_children())
                if not spice_vms:
                    self.status_label.config(
                        text=f"✗  No SPICE VMs found ({len(qemu_vms)} checked)", fg=C["red"])
                    return

                spice_vms.sort(key=lambda v: v.get("vmid", 0))
                for vm in spice_vms:
                    vmid = vm.get("vmid", "?")
                    name = vm.get("name", "unnamed")
                    node = vm.get("node", "?")
                    pool = vm.get("pool", "—")
                    status = vm.get("status", "?")

                    if status == "running":
                        display_status = "● running"
                        tag = "running"
                    else:
                        display_status = "○ stopped"
                        tag = "stopped"

                    self.vm_tree.insert("", "end",
                                         values=(vmid, name, node, pool, display_status), tags=(tag,))

                self.vm_tree.tag_configure("running", foreground=C["green"])
                self.vm_tree.tag_configure("stopped", foreground=C["overlay0"])
                self.status_label.config(
                    text=f"◈  {cluster['name']}  —  {len(spice_vms)} SPICE VMs", fg=C["text"])

            self.after(0, update_ui)

        threading.Thread(target=fetch, daemon=True).start()

    # ── VM actions ────────────────────────────────────────────────────────────
    def _sort_tree(self, col):
        """Sort the treeview by a column. Click again to reverse."""
        if self._tree_sort_col == col:
            self._tree_sort_asc = not self._tree_sort_asc
        else:
            self._tree_sort_col = col
            self._tree_sort_asc = True

        columns = ("vmid", "name", "node", "pool", "status")
        col_idx = columns.index(col)

        rows = [(self.vm_tree.set(iid, col), iid) for iid in self.vm_tree.get_children("")]

        # Numeric sort for VMID, alpha for everything else
        if col == "vmid":
            rows.sort(key=lambda r: int(r[0]) if r[0].isdigit() else 0, reverse=not self._tree_sort_asc)
        else:
            rows.sort(key=lambda r: r[0].lower(), reverse=not self._tree_sort_asc)

        for idx, (_, iid) in enumerate(rows):
            self.vm_tree.move(iid, "", idx)

        # Update heading labels with sort indicator
        for c in columns:
            label = c.upper()
            if c == col:
                label += "  ▲" if self._tree_sort_asc else "  ▼"
            self.vm_tree.heading(c, text=label)

    def _get_selected_vm(self):
        sel = self.vm_tree.selection()
        if not sel:
            return None
        values = self.vm_tree.item(sel[0], "values")
        status = values[4].replace("● ", "").replace("○ ", "").strip()
        return {"vmid": values[0], "name": values[1], "node": values[2],
                "pool": values[3], "status": status}

    def _on_vm_double_click(self, event):
        self._launch_spice()

    def _launch_spice(self):
        vm = self._get_selected_vm()
        if not vm:
            messagebox.showinfo("No Selection", "Select a VM to connect to.")
            return
        if vm["status"] != "running":
            messagebox.showwarning("VM Not Running", f"VM {vm['vmid']} ({vm['name']}) is not running.")
            return

        cluster = self.current_cluster
        auth = self._get_auth(cluster)
        if not auth:
            return

        self.status_label.config(text=f"⏳  Connecting to {vm['name']}...", fg=C["yellow"])
        self.update_idletasks()

        def connect():
            data = api_request(
                cluster["host"],
                f"/api2/json/nodes/{vm['node']}/qemu/{vm['vmid']}/spiceproxy",
                method="POST", auth=auth
            )

            spice_data = data.get("data")
            if not spice_data or not spice_data.get("type"):
                err = data.get("message", data.get("error", "Unknown error"))
                self.after(0, lambda: (
                    self.status_label.config(text="✗  Connection failed", fg=C["red"]),
                    messagebox.showerror("SPICE Error",
                                          f"Failed to get SPICE config:\n{err}", parent=self)
                ))
                return

            vv_path = os.path.join(tempfile.gettempdir(), f"proxmox-spice-{vm['vmid']}.vv")
            with open(vv_path, "w") as f:
                f.write("[virt-viewer]\n")
                for key in ("type", "host", "port", "tls-port", "password",
                            "proxy", "host-subject", "ca"):
                    f.write(f"{key}={spice_data.get(key, '')}\n")
                f.write("toggle-fullscreen=shift+f11\n")
                f.write("release-cursor=shift+f12\n")
                f.write("secure-attention=ctrl+alt+end\n")
                f.write("delete-this-file=1\n")

            try:
                subprocess.Popen(["remote-viewer", vv_path])
                self.after(0, lambda: self.status_label.config(
                    text=f"✓  Connected to {vm['name']} ({vm['vmid']})", fg=C["green"]))
            except FileNotFoundError:
                self.after(0, lambda: (
                    self.status_label.config(text="✗  remote-viewer not found", fg=C["red"]),
                    messagebox.showerror("Missing Dependency",
                                          "remote-viewer not found.\n"
                                          "Install: sudo dnf install virt-viewer", parent=self)
                ))

        threading.Thread(target=connect, daemon=True).start()

    def _export_desktop(self):
        vm = self._get_selected_vm()
        if not vm:
            messagebox.showinfo("No Selection", "Select a VM first.")
            return

        desktop_dir = Path.home() / ".local" / "share" / "applications"
        desktop_dir.mkdir(parents=True, exist_ok=True)

        script_path = Path.home() / "proxmox-spice.sh"
        if not script_path.exists():
            messagebox.showwarning("Script Not Found",
                                    f"Shell script not found at {script_path}.\n"
                                    "The .desktop file will reference it — make sure it exists.")

        filepath = desktop_dir / f"spice-vm{vm['vmid']}.desktop"
        content = (
            "[Desktop Entry]\n"
            f"Name={vm['name']} (VM {vm['vmid']})\n"
            f"Exec={script_path} {vm['vmid']}\n"
            "Icon=computer\n"
            "Type=Application\n"
            "Terminal=false\n"
            "Categories=System;\n"
        )
        with open(filepath, "w") as f:
            f.write(content)
        os.chmod(filepath, 0o755)
        messagebox.showinfo("Exported", f"Desktop launcher saved:\n{filepath}")

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
                messagebox.showerror("Icon Error", f"Could not copy icon:\n{e}", parent=self)
                return

        current_script = Path(os.path.abspath(__file__))
        try:
            if current_script.resolve() != installed_script.resolve():
                shutil.copy2(current_script, installed_script)
            os.chmod(installed_script, 0o755)
        except Exception as e:
            messagebox.showerror("Install Failed", f"Could not copy script:\n{e}", parent=self)
            return

        desktop_dir.mkdir(parents=True, exist_ok=True)
        content = (
            "[Desktop Entry]\n"
            "Name=Proxmox SPICE Manager\n"
            f"Exec=/usr/bin/python3 {installed_script}\n"
            f"Icon={icon_value}\n"
            "Type=Application\n"
            "Terminal=false\n"
            "Categories=System;Network;\n"
            "Comment=Manage and launch SPICE console sessions to Proxmox VMs\n"
        )

        try:
            with open(desktop_file, "w") as f:
                f.write(content)
            os.chmod(desktop_file, 0o755)
        except Exception as e:
            messagebox.showerror("Install Failed",
                                  f"Could not create desktop entry:\n{e}", parent=self)
            return

        messagebox.showinfo(
            "Installed",
            "App installed!\n\n"
            f"Script: ~/{script_name}\n"
            f"Icon: {icon_value}\n"
            "Menu entry created.\n\n"
            "It should appear in your app menu shortly."
        )


if __name__ == "__main__":
    app = ProxmoxSpiceManager()
    app.mainloop()
