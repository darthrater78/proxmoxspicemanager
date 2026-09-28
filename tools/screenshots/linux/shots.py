"""Drives the Linux app's real window with mock data and saves PNGs of it.

Nothing touches a network, the keyring or your own config: the config lives in
a temporary directory and the refresh is replaced with fixed VMs. Run under an
X server (run.sh uses Xvfb).

Usage: shots.py <path to proxmox-spice-manager.py> <output dir>
"""
import importlib.util
import sys
import tempfile
from pathlib import Path

from PIL import ImageGrab

script, out = Path(sys.argv[1]), Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)

spec = importlib.util.spec_from_file_location("psm", script)
psm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(psm)

config_dir = Path(tempfile.mkdtemp(prefix="psm-shots-"))
psm.CONFIG_DIR = config_dir
psm.CONFIG_FILE = config_dir / "connections.json"
psm.save_config({
    "clusters": [
        {"name": name, "host": f"https://{name.lower().replace(' ', '-')}.example.com:8006",
         "auth_method": "token", "token_id": "shots@pve!shots"}
        for name in ("Homelab", "Lab East", "DR Site")
    ],
    "theme": psm.DEFAULT_THEME,
    "prereqs_ok": True,
    "vm_notes": {"Homelab:101": "Daily driver", "Homelab:110": "Testing",
                 "Homelab:120": "Domain controller", "Homelab:130": "Keep for old apps"},
    "note_options": ["Daily driver", "Testing", "Domain controller", "Keep for old apps"],
})

VMS = [
    (101, "win11-dev", "pve1", "desktops", 3, "running",
     [("Ethernet", "10.20.30.41"), ("Ethernet 2", "192.168.50.41"), ("Ethernet", "2001:db8:20::41")],
     "win11"),
    (102, "fedora-43-ws", "pve1", "desktops", 1, "running", "10.20.30.42", "l26"),
    (103, "ubuntu-2404-desk", "pve2", "desktops", 0, "stopped", "", "l26"),
    (110, "kali-lab", "pve2", "security", 5, "running", "no agent", "l26"),
    (120, "win-server-2025", "pve1", "servers", 2, "running", "10.20.30.60", "win11"),
    (121, "debian-13-build", "pve3", "servers", 0, "stopped", "", "l26"),
    (130, "win10-legacy", "pve3", "desktops", 1, "stopped", "", "win10"),
    (140, "arch-sandbox", "pve2", "", 4, "running", "10.20.30.75", "l26"),
]


# The VMs' own Notes in Proxmox (their config "description")
PVE_NOTES = {102: "## Build workstation\nSee the wiki for the toolchain setup.",
             140: "Reset weekly from the base snapshot"}


class Shots(psm.ProxmoxSpiceManager):
    def _refresh_vms(self):
        cluster = self.current_cluster
        if not cluster:
            return
        self.cluster_title.config(text=cluster["name"])
        keep = {vm["vmid"] for vm in self._get_selected_vms()}
        self._vms = [
            {"vmid": vmid, "name": name, "node": node, "pool": pool, "snaps": snaps,
             "status": status, "ostype": ostype,
             # A string stands for why there's no address ("", "no agent")
             "ips": ip if isinstance(ip, list) else [("eth0", ip)] if ip[:1].isdigit() else [],
             "ip_note": "" if isinstance(ip, list) or ip[:1].isdigit() else ip,
             "note": self._lookup_vm_note(vmid), "pve_note": PVE_NOTES.get(vmid, "")}
            for vmid, name, node, pool, snaps, status, ip, ostype in VMS
        ]
        self._loaded_cluster = cluster["name"]
        self._cluster_status.update({cluster["name"]: (True, len(VMS)),
                                     "Lab East": (True, 4), "DR Site": (False, None)})
        self._populate_clusters()
        self._render_vms(keep)
        self._show_summary()


def capture(app, name):
    app.update()
    app.after(300)
    app.update()
    x, y = app.winfo_rootx(), app.winfo_rooty()
    ImageGrab.grab(bbox=(x, y, x + app.winfo_width(), y + app.winfo_height())).save(out / name)
    print(f"wrote {out / name}")


def appearance(app, theme, accent=psm.DEFAULT_ACCENT):
    app._apply_appearance(theme=theme, accent=accent)
    # It reopens the flyout shortly after; let that happen, then close it
    app.update()
    app.after(150)
    app.update()
    app._close_popup()


def run(app):
    capture(app, "linux-main.png")
    for theme in psm.THEMES:
        appearance(app, theme)
        capture(app, f"linux-main-{theme.lower().replace(' ', '-')}.png")
    appearance(app, psm.DEFAULT_THEME)

    tree = app.vm_tree
    tree.selection_set(["vm:101", "vm:103", "vm:130"])
    capture(app, "linux-state-multiselect.png")
    app.search_var.set("win")
    capture(app, "linux-state-search.png")
    app.search_var.set("")
    app._set_vm_filter("running")
    capture(app, "linux-state-running.png")
    app._set_vm_filter("all")
    app.search_var.set("nothing-matches")
    capture(app, "linux-state-empty.png")
    app.search_var.set("")
    app._toggle_grouping()
    app._sort_by("ip")
    capture(app, "linux-state-ungrouped.png")
    # A VM with Notes in Proxmox: its first line in the list, all of it in the inspector
    tree.selection_set(["vm:102"])
    capture(app, "linux-state-proxmox-notes.png")
    # Wide window with IPv6 on: the address column grows to show every address
    app._toggle_ipv6()
    app.geometry("1800x760")
    app.update()
    capture(app, "linux-state-wide.png")
    app.geometry("1280x760")
    app._toggle_ipv6()
    app.update()
    app._toggle_grouping()
    app._sort_by("vmid")
    app._collapsed_nodes.add("pve3")
    app._render_vms()
    capture(app, "linux-state-collapsed.png")
    app._collapsed_nodes.clear()
    app._render_vms()

    tree.selection_set(["vm:101"])
    app._open_appearance()
    capture(app, "linux-appearance.png")
    app._close_popup()
    app._open_settings()
    capture(app, "linux-settings.png")
    app._close_popup()
    app.destroy()


app = Shots()
app.geometry("1280x760+0+0")
app.after(500, lambda: run(app))
app.mainloop()
