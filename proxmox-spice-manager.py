#!/usr/bin/env python3
"""
Proxmox SPICE Connection Manager — Linux
A GUI app to manage and launch SPICE console sessions to Proxmox VMs.
Connections are saved to ~/.config/proxmox-spice/connections.json

Dependencies: python3-tkinter, python3-keyring, remote-viewer (virt-viewer)

Install on Fedora:  sudo dnf install python3-tkinter python3-keyring virt-viewer
Install on Debian:  sudo apt install python3-tk python3-keyring virt-viewer

VERSION 2.2.2
"""

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import threading
import importlib
from pathlib import Path

# Verify absolute GUI requirement first.
try:
    import tkinter as tk
    from tkinter import messagebox
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

import sys
from proxmox_spice_common import (
    set_fonts, C, HoverButton, ProxmoxSpiceManagerBase,
    load_config, APP_VERSION,
)

CONFIG_DIR = Path.home() / ".config" / "proxmox-spice"
CONFIG_FILE = CONFIG_DIR / "connections.json"
APP_ID = "proxmox-spice-manager"

_BASE_DIR = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).parent
ICON_PATH = _BASE_DIR / "icon.png"

set_fonts("sans-serif", "monospace")

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
        from tkinter import filedialog
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
        import tempfile
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

    def _platform_header_buttons(self, header):
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

    def _platform_bottom_buttons(self, bottom):
        HoverButton(
            bottom, text=" Export .desktop ", command=self._export_desktop,
            bg=C["surface0"], fg=C["subtext0"], relief="flat", padx=12, pady=8,
            hover_bg=C["surface1"], hover_fg=C["text"], font=("sans-serif", 10),
        ).pack(side="right", padx=(0, 8))

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
    app = ProxmoxSpiceManager()
    app.mainloop()
