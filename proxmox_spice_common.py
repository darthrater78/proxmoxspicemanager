"""
Proxmox SPICE Manager — Shared module
Common UI, API helpers, and base application class used by both
the Linux and Windows platform scripts.
"""

import json
import os
import copy
import subprocess
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

APP_ID = "proxmox-spice-manager"
APP_VERSION = "2.2.4"

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

# Font constants — overridden by platform scripts before UI is built
FONT = "sans-serif"
MONO = "monospace"


def set_fonts(font, mono):
    global FONT, MONO
    FONT = font
    MONO = mono


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

    def _platform_header_buttons(self, header):
        pass

    def _platform_bottom_buttons(self, bottom):
        pass

    def _platform_set_vv_permissions(self, vv_path):
        pass

    def _platform_set_icon(self):
        pass

    def _get_config_file(self):
        raise NotImplementedError

    def _get_app_version(self):
        return APP_VERSION

    # ── Init ─────────────────────────────────────────────────────────────────
    def __init__(self):
        super().__init__()
        version = self._get_app_version()
        self.title(f"Proxmox SPICE Manager v{version}")
        self.geometry("1100x640")
        self.configure(bg=C["base"])
        self.minsize(900, 500)
        self._platform_set_icon()

        self.config_data = load_config(self._get_config_file())
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
            self._save_config()

        self._platform_migrate_secrets()
        self._build_ui()
        self._populate_clusters()

        if self.config_data.get("clusters"):
            self.cluster_listbox.select_set(0)
            self.current_cluster = self.config_data["clusters"][0]
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

        version = self._get_app_version()

        # Header
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
            title_frame, text=f"Proxmox SPICE Manager v{version}",
            bg=C["crust"], fg=C["text"], font=(FONT, 12, "bold"),
        ).pack(side="left")

        links_frame = tk.Frame(title_frame, bg=C["crust"])
        links_frame.pack(side="left", padx=(12, 0))
        gh_link = tk.Label(
            links_frame, text="GitHub", bg=C["crust"], fg=C["blue"],
            font=(FONT, 9, "underline"), cursor="hand2",
        )
        gh_link.pack(side="left")
        gh_link.bind("<Button-1>", lambda e: webbrowser.open(
            "https://github.com/darthrater78/proxmoxspicemanager"))
        tk.Label(
            links_frame, text=" · ", bg=C["crust"], fg=C["overlay0"],
            font=(FONT, 9),
        ).pack(side="left")
        rn_link = tk.Label(
            links_frame, text="Release Notes", bg=C["crust"], fg=C["blue"],
            font=(FONT, 9, "underline"), cursor="hand2",
        )
        rn_link.pack(side="left")
        release_version = version.replace("-win", "")
        rn_link.bind("<Button-1>", lambda e: webbrowser.open(
            f"https://github.com/darthrater78/proxmoxspicemanager/releases/tag/v{release_version}"))

        hbtn = {
            "bg": C["crust"], "fg": C["subtext0"], "relief": "flat",
            "font": (FONT, 9), "padx": 10, "pady": 4,
            "activebackground": C["mantle"], "activeforeground": C["text"],
        }

        self._platform_header_buttons(header)

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

        # Body
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
        self._checked_items = set()
        self._notes_combo = None
        self._active_filters = {}
        self._filter_popup = None

        # VM Table
        table_frame = tk.Frame(content, bg=C["base"])
        table_frame.pack(fill="both", expand=True, padx=16, pady=(10, 0))

        columns = ("check", "vmid", "name", "ip", "node", "pool", "snaps", "status", "notes")
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
        )
        style.map("Treeview.Heading", background=[("active", C["surface2"])])

        self.vm_tree.heading(
            "check", text="☐", command=self._toggle_all_checks,
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
        self.vm_tree.column("ip", width=130, minwidth=80)
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
        elif set(self._display_columns) != set(columns):
            self._display_columns = list(columns)
        self._drag_col = None
        self._drag_start_x = None

        self.vm_tree.bind("<ButtonPress-1>", self._on_heading_press)
        self.vm_tree.bind("<B1-Motion>", self._on_heading_drag)
        self.vm_tree.bind("<ButtonRelease-1>", self._on_heading_release)
        self.vm_tree.bind("<Button-3>", self._on_heading_right_click)
        self.vm_tree.bind("<Motion>", self._show_heading_tooltip)
        self.vm_tree.bind("<Leave>", self._hide_heading_tooltip)

        saved_order = self.config_data.get("column_order")
        if saved_order and set(saved_order) == set(self._data_columns):
            self._display_columns = ["check"] + saved_order
        self.vm_tree["displaycolumns"] = self._display_columns

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
            bottom, text=" Launch SPICE ", command=self._launch_spice,
            bg=C["green"], fg=C["crust"], relief="flat", padx=16, pady=8,
            hover_bg=C["teal"], hover_fg=C["crust"],
            font=(FONT, 11, "bold"),
        ).pack(side="right")

        self._platform_bottom_buttons(bottom)

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
            power_frame, text=" Reboot ", command=self._reboot_vm,
            bg=C["surface0"], fg=C["peach"], hover_bg=C["surface1"],
            hover_fg=C["peach"], **pbtn,
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
        ).pack(side="left", padx=(0, 4))
        HoverButton(
            power_frame, text=" Notes ⚙ ", command=self._manage_note_options,
            bg=C["surface0"], fg=C["subtext0"], hover_bg=C["surface1"],
            hover_fg=C["text"], **pbtn,
        ).pack(side="left")

        self._check_count_label = tk.Label(
            bottom, text="", bg=C["base"], fg=C["sapphire"],
            font=(FONT, 9),
        )
        self._check_count_label.pack(side="left", padx=(12, 0))

    # ── Theme ────────────────────────────────────────────────────────────────
    def _on_theme_change(self, event=None):
        theme_name = self.theme_var.get()
        if theme_name not in THEMES:
            return
        C.update(THEMES[theme_name])
        self.config_data["theme"] = theme_name
        self._save_config()

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

    # ── Clusters ─────────────────────────────────────────────────────────────
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
        dlg = ClusterDialog(self, get_secret_fn=self._platform_get_secret)
        if dlg.result:
            self.config_data.setdefault("clusters", []).append(dlg.result)
            self._save_config()
            if dlg._pending_secret:
                self._platform_save_secret(dlg.result["name"], dlg._pending_secret)
            self._populate_clusters()

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
            self.config_data["clusters"][idx] = dlg.result
            self._save_config()
            if dlg._pending_secret:
                self._platform_save_secret(dlg.result["name"], dlg._pending_secret)
            self._populate_clusters()

    def _remove_cluster(self):
        result = self._get_selected_cluster()
        if not result:
            return
        idx, cluster = result
        if messagebox.askyesno("Confirm", f"Remove cluster '{cluster['name']}'?", parent=self):
            self._platform_delete_secret(cluster["name"])
            self.config_data["clusters"].pop(idx)
            self._save_config()
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
    def _refresh_vms(self):
        if not self.current_cluster:
            return
        cluster = self.current_cluster
        auth = self._get_auth(cluster)
        if not auth:
            self.status_label.config(text="Auth failed", fg=C["red"])
            return
        self.status_label.config(text="Loading VMs...", fg=C["yellow"])
        self.update_idletasks()

        def fetch():
            data = api_request(
                cluster["host"],
                "/api2/json/cluster/resources?type=vm", auth=auth,
            )
            if "error" in data:
                self.after(0, lambda d=data: self.status_label.config(
                    text=f"Error: {d['error']}", fg=C["red"]
                ))
                return

            all_vms = data.get("data", [])
            if not all_vms:
                self.after(0, lambda: (
                    self.vm_tree.delete(*self.vm_tree.get_children()),
                    self.status_label.config(text="No VMs found", fg=C["red"]),
                ))
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
                    ip_addr = ""
                    if vm.get("status") == "running":
                        agent_data = api_request(
                            cluster["host"],
                            f"/api2/json/nodes/{vm.get('node')}"
                            f"/qemu/{vm.get('vmid')}/agent/network-get-interfaces",
                            auth=auth,
                        )
                        if "error" not in agent_data:
                            for iface in agent_data.get("data", {}).get("result", []):
                                if iface.get("name") == "lo":
                                    continue
                                for addr in iface.get("ip-addresses", []):
                                    if addr.get("ip-address-type") == "ipv4":
                                        ip_addr = addr.get("ip-address", "")
                                        break
                                if ip_addr:
                                    break
                    vm["_ip_address"] = ip_addr
                    spice_vms.append(vm)

            def update_ui():
                self.vm_tree.delete(*self.vm_tree.get_children())
                if not spice_vms:
                    self._all_vm_rows = []
                    self.status_label.config(
                        text=f"No SPICE VMs found ({len(qemu_vms)} checked)",
                        fg=C["red"],
                    )
                    return

                spice_vms.sort(key=lambda v: v.get("vmid", 0))
                self._all_vm_rows = []
                for vm in spice_vms:
                    status = vm.get("status", "?")
                    display_status = "● running" if status == "running" else "○ stopped"
                    tag = "running" if status == "running" else "stopped"
                    snap_count = vm.get("_snap_count", 0)
                    snap_display = f"📸 {snap_count}" if snap_count > 0 else "—"
                    vmid_str = str(vm.get("vmid", "?"))
                    note = self.config_data.get("vm_notes", {}).get(vmid_str, "")
                    row = (
                        vmid_str, vm.get("name", "unnamed"),
                        vm.get("_ip_address", ""),
                        vm.get("node", "?"), vm.get("pool", "—"),
                        snap_display, display_status, note,
                    )
                    self._all_vm_rows.append((row, tag))

                self._refresh_filter_dropdowns()
                self._apply_filters()
                tls_warn = "  ⚠ TLS off" if cluster.get("skip_tls_verify", False) else ""
                self.status_label.config(
                    text=f"◈  {cluster['name']}  —  {len(spice_vms)} SPICE VMs{tls_warn}",
                    fg=C["yellow"] if tls_warn else C["text"],
                )

                if hasattr(self, "_display_columns"):
                    self.vm_tree["displaycolumns"] = self._display_columns
                if self._tree_sort_col:
                    self._reapply_sort()

            self.after(0, update_ui)

        threading.Thread(target=fetch, daemon=True).start()

    # ── Filtering ────────────────────────────────────────────────────────────
    def _on_heading_right_click(self, event):
        if self._filter_popup and self._filter_popup.winfo_exists():
            self._filter_popup.destroy()
            self._filter_popup = None
            return
        region = self.vm_tree.identify_region(event.x, event.y)
        if region != "heading":
            return
        col_id = self.vm_tree.identify_column(event.x)
        if not col_id:
            return
        idx = int(col_id.replace("#", "")) - 1
        if idx < 0 or idx >= len(self._display_columns):
            return
        col_name = self._display_columns[idx]
        if col_name == "check":
            return
        self._show_filter_popup(col_name, event.x_root, event.y_root)

    def _show_heading_tooltip(self, event):
        region = self.vm_tree.identify_region(event.x, event.y)
        if region == "heading":
            col_id = self.vm_tree.identify_column(event.x)
            if col_id:
                idx = int(col_id.replace("#", "")) - 1
                if 0 <= idx < len(self._display_columns) and self._display_columns[idx] != "check":
                    if not hasattr(self, "_heading_tip") or not self._heading_tip or not self._heading_tip.winfo_exists():
                        tip = tk.Toplevel(self)
                        tip.wm_overrideredirect(True)
                        lbl = tk.Label(
                            tip, text="Right-click to filter", bg=C["surface2"],
                            fg=C["subtext0"], font=(FONT, 8), padx=6, pady=2,
                        )
                        lbl.pack()
                        tip.geometry(f"+{event.x_root + 12}+{event.y_root + 16}")
                        self._heading_tip = tip
                    return
        if hasattr(self, "_heading_tip") and self._heading_tip and self._heading_tip.winfo_exists():
            self._heading_tip.destroy()
            self._heading_tip = None

    def _hide_heading_tooltip(self, event):
        if hasattr(self, "_heading_tip") and self._heading_tip and self._heading_tip.winfo_exists():
            self._heading_tip.destroy()
            self._heading_tip = None

    def _show_filter_popup(self, col_name, x, y):
        if self._filter_popup and self._filter_popup.winfo_exists():
            self._filter_popup.destroy()

        popup = tk.Toplevel(self)
        popup.wm_overrideredirect(True)
        popup.configure(bg=C["surface0"], highlightbackground=C["overlay0"], highlightthickness=1)
        popup.geometry(f"+{x}+{y}")
        popup.lift()
        self._filter_popup = popup

        title = tk.Label(
            popup, text=f"Filter: {col_name.upper()}", bg=C["surface0"],
            fg=C["subtext0"], font=(FONT, 9, "bold"), anchor="w",
        )
        title.pack(fill="x", padx=8, pady=(6, 2))

        col_indices = {"vmid": 0, "name": 1, "ip": 2, "node": 3, "pool": 4, "snaps": 5, "status": 6, "notes": 7}
        current_val = self._active_filters.get(col_name, "")

        if col_name == "name":
            var = tk.StringVar(value=current_val)
            entry = tk.Entry(
                popup, textvariable=var, bg=C["surface1"], fg=C["text"],
                insertbackground=C["text"], relief="flat", font=(FONT, 10),
            )
            entry.pack(fill="x", padx=8, pady=4, ipady=3)
            entry.focus_set()
            entry.select_range(0, "end")

            def apply_name_filter(event=None):
                val = var.get().strip()
                if val:
                    self._active_filters["name"] = val
                else:
                    self._active_filters.pop("name", None)
                self._close_filter_popup()
                self._apply_filters()
                self._update_heading_labels()

            entry.bind("<Return>", apply_name_filter)
        else:
            values = []
            if hasattr(self, "_all_vm_rows") and self._all_vm_rows:
                if col_name == "notes":
                    values = self.config_data.get("note_options", [])
                else:
                    values = sorted(set(
                        str(row[col_indices[col_name]])
                        for row, _ in self._all_vm_rows
                        if str(row[col_indices[col_name]])
                    ))

            combo_var = tk.StringVar(value=current_val)
            combo = ttk.Combobox(
                popup, textvariable=combo_var, values=[""] + values,
                state="readonly", font=(FONT, 10), width=20,
            )
            combo.pack(fill="x", padx=8, pady=4)
            combo.focus_set()

            def apply_dropdown_filter(event=None):
                val = combo_var.get().strip()
                if val:
                    self._active_filters[col_name] = val
                else:
                    self._active_filters.pop(col_name, None)
                self._close_filter_popup()
                self._apply_filters()
                self._update_heading_labels()

            combo.bind("<<ComboboxSelected>>", apply_dropdown_filter)

        btn_frame = tk.Frame(popup, bg=C["surface0"])
        btn_frame.pack(fill="x", padx=8, pady=(2, 6))

        if col_name in self._active_filters:
            HoverButton(
                btn_frame, text="Clear",
                command=lambda: self._clear_single_filter(col_name, popup),
                bg=C["red"], fg=C["crust"], relief="flat", padx=6, pady=2,
                hover_bg=C["red"], hover_fg=C["crust"], font=(FONT, 9),
            ).pack(side="left")

        if self._active_filters:
            HoverButton(
                btn_frame, text="Clear All",
                command=lambda: self._clear_filters(popup),
                bg=C["surface1"], fg=C["subtext0"], relief="flat", padx=6, pady=2,
                hover_bg=C["surface2"], hover_fg=C["text"], font=(FONT, 9),
            ).pack(side="right")

        popup.bind("<Escape>", lambda e: self._close_filter_popup())
        self._filter_deactivate_id = self.bind(
            "<Deactivate>", lambda e: self._close_filter_popup()
        )

    def _close_filter_popup(self):
        if hasattr(self, "_filter_deactivate_id") and self._filter_deactivate_id:
            self.unbind("<Deactivate>", self._filter_deactivate_id)
            self._filter_deactivate_id = None
        if self._filter_popup and self._filter_popup.winfo_exists():
            self._filter_popup.destroy()
        self._filter_popup = None

    def _clear_single_filter(self, col_name, popup=None):
        self._active_filters.pop(col_name, None)
        if popup and popup.winfo_exists():
            popup.destroy()
        self._filter_popup = None
        self._apply_filters()
        self._update_heading_labels()

    def _apply_filters(self):
        if not hasattr(self, "_all_vm_rows"):
            return
        col_indices = {"vmid": 0, "name": 1, "ip": 2, "node": 3, "pool": 4, "snaps": 5, "status": 6, "notes": 7}
        filters = {k: v.lower() for k, v in self._active_filters.items() if v}

        self.vm_tree.delete(*self.vm_tree.get_children())
        visible = 0
        for row, tag in self._all_vm_rows:
            match = True
            for cid, f_text in filters.items():
                cell = str(row[col_indices.get(cid, -1)]).lower()
                if cid == "name":
                    if f_text not in cell:
                        match = False
                        break
                else:
                    if cell != f_text:
                        match = False
                        break
            if not match:
                continue
            vmid = row[0]
            check = "☑" if vmid in self._checked_items else "☐"
            self.vm_tree.insert("", "end", values=(check,) + row, tags=(tag,))
            visible += 1

        self.vm_tree.tag_configure("running", foreground=C["green"])
        self.vm_tree.tag_configure("stopped", foreground=C["overlay0"])
        self._update_check_header()
        self._update_selection_count()

        if self._tree_sort_col:
            self._reapply_sort()

        if filters and visible != len(self._all_vm_rows):
            self.status_label.config(
                text=f"Showing {visible} of {len(self._all_vm_rows)} VMs",
                fg=C["sapphire"],
            )

    def _clear_filters(self, popup=None):
        self._active_filters.clear()
        if popup and popup.winfo_exists():
            popup.destroy()
        self._filter_popup = None
        self._apply_filters()
        self._update_heading_labels()

    def _update_heading_labels(self):
        import tkinter.font as tkfont
        heading_font = tkfont.Font(family=FONT, size=9, weight="bold")
        sort_col = self._tree_sort_col
        for c in self._data_columns:
            label = c.upper()
            if c in self._active_filters:
                label += f" [{self._active_filters[c]}]"
            if c == sort_col:
                label += "  ▲" if self._tree_sort_asc else "  ▼"
            self.vm_tree.heading(c, text=label)
            needed = heading_font.measure(label) + 24
            current = self.vm_tree.column(c, "width")
            if needed > current:
                self.vm_tree.column(c, width=needed)

    def _refresh_filter_dropdowns(self):
        pass

    # ── Sorting ──────────────────────────────────────────────────────────────
    def _reapply_sort(self):
        col = self._tree_sort_col
        if not col:
            return
        rows = [(self.vm_tree.set(iid, col), iid) for iid in self.vm_tree.get_children("")]
        if col == "vmid":
            rows.sort(key=lambda r: int(r[0]) if r[0].isdigit() else 0, reverse=not self._tree_sort_asc)
        else:
            rows.sort(key=lambda r: r[0].lower(), reverse=not self._tree_sort_asc)
        for idx, (_, iid) in enumerate(rows):
            self.vm_tree.move(iid, "", idx)
        self._update_heading_labels()

    def _sort_tree(self, col):
        if col == "check":
            return
        if self._tree_sort_col == col:
            self._tree_sort_asc = not self._tree_sort_asc
        else:
            self._tree_sort_col = col
            self._tree_sort_asc = True
        self._reapply_sort()

    # ── Column reorder ───────────────────────────────────────────────────────
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
            self._drag_col, self._drag_start_x = self._col_from_x(event.x), event.x
        else:
            self._drag_col, self._drag_start_x = None, None
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
        self.config_data["column_order"] = [c for c in cols if c != "check"]
        self._save_config()
        self._drag_col = self._drag_start_x = None

    # ── Checkbox Selection ───────────────────────────────────────────────────
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
        current = values[8] if len(values) > 8 else ""

        options = self.config_data.get("note_options", [])
        combo_values = [""] + options

        combo = ttk.Combobox(
            self.vm_tree, values=combo_values, state="normal",
            font=(FONT, 10),
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
            self._save_config()

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

    # ── VM Selection ─────────────────────────────────────────────────────────
    def _get_selected_vms(self):
        vms = []
        for iid in self.vm_tree.get_children(""):
            values = self.vm_tree.item(iid, "values")
            if values[0] != "☑":
                continue
            status = values[7].replace("● ", "").replace("○ ", "").strip()
            vms.append({
                "vmid": values[1], "name": values[2], "node": values[4],
                "pool": values[5], "snaps": values[6], "status": status,
            })
        return vms

    def _get_selected_vm(self):
        sel = self.vm_tree.selection()
        if not sel:
            return None
        if len(sel) > 1:
            messagebox.showinfo("Single Selection", "Select a single VM.", parent=self)
            return None
        values = self.vm_tree.item(sel[0], "values")
        status = values[7].replace("● ", "").replace("○ ", "").strip()
        return {
            "vmid": values[1], "name": values[2], "node": values[4],
            "pool": values[5], "snaps": values[6], "status": status,
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

    # ── SPICE Launch ─────────────────────────────────────────────────────────
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
                self.after(0, lambda: messagebox.showerror(
                    "Launch Error", str(e), parent=self
                ))

        threading.Thread(target=connect, daemon=True).start()

    # ── Power Actions ────────────────────────────────────────────────────────
    def _vm_power_action(self, action, action_label):
        vms = self._get_selected_vms()
        if not vms:
            vm = self._get_selected_vm()
            if vm:
                vms = [vm]
            else:
                messagebox.showinfo("No Selection", "Select one or more VMs.", parent=self)
                return

        if action == "start":
            valid = [v for v in vms if v["status"] != "running"]
        else:
            valid = [v for v in vms if v["status"] == "running"]
        skipped = [v for v in vms if v not in valid]

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
