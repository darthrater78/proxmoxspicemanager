# Proxmox SPICE Connection Manager

A desktop GUI application for managing and launching SPICE console sessions to Proxmox VE virtual machines. Built with Python and tkinter — no browser required.

![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows-blue)
![Python](https://img.shields.io/badge/python-3.9%2B-yellow)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Multi-cluster management** — connect to multiple Proxmox clusters with saved credentials
- **Auto-discovery** — automatically detects SPICE-enabled VMs across all cluster nodes
- **One-click SPICE launch** — opens `remote-viewer` sessions with a double-click
- **VM power controls** — Start, ACPI Shutdown, and Force Stop with multi-select support
- **Snapshot management** — create, rollback, and delete snapshots with a full dialog, plus quick-rollback to the latest snapshot
- **Secure credential storage** — Linux: OS keyring (GNOME Keyring, KDE Wallet, etc.); Windows: DPAPI encryption tied to your Windows user account
- **5 built-in themes** — Catppuccin Mocha, Catppuccin Latte, Nord, Dracula, OLED Dark
- **Column filtering & sorting** — inline filters above the VM table, click headings to sort, drag headings to reorder
- **Import / Export** — share cluster configurations between machines (with plaintext secret warning on export)
- **App menu integration** — install as a desktop app (Linux: `.desktop` file; Windows: Start Menu shortcut)
- **Prerequisite checker** — first-run dialog detects missing dependencies and helps you install them

## Screenshots

The app uses a themed tkinter interface with a sidebar for cluster selection and a main table showing SPICE-enabled VMs with status indicators, snapshot counts, and pool membership.

## Requirements

### Both Platforms

- Python 3.9 or later (with tkinter — included in standard Python installers)
- Network access to your Proxmox VE host(s) on port 8006

### Linux

| Dependency | Fedora | Debian/Ubuntu |
|---|---|---|
| tkinter | `python3-tkinter` | `python3-tk` |
| keyring | `python3-keyring` | `python3-keyring` |
| virt-viewer | `virt-viewer` | `virt-viewer` |

**Fedora (one-liner):**

```bash
sudo dnf install python3-tkinter python3-keyring virt-viewer
```

**Debian/Ubuntu (one-liner):**

```bash
sudo apt install python3-tk python3-keyring virt-viewer
```

### Windows

| Dependency | How to install |
|---|---|
| Python 3.9+ | [python.org](https://www.python.org/downloads/) — check "Add to PATH" during install |
| virt-viewer | [spice-space.org/download.html](https://www.spice-space.org/download.html) — install the Windows MSI |

No `pip install` required — the Windows edition uses only the Python standard library plus Windows DPAPI for encryption.

## Installation

### Linux — Run from source

```bash
# Download
curl -O proxmox-spice-manager.py

# Make executable
chmod +x proxmox-spice-manager.py

# Run
./proxmox-spice-manager.py
```

Use **File → Install to App Menu** inside the app to create a `.desktop` entry with an icon of your choice.

See [linux-setup.md](linux-setup.md) for a full walkthrough with screenshots, then [proxmox-setup.md](proxmox-setup.md) to configure your connection.

### Windows — Run from source

```powershell
python proxmox-spice-manager-win.py
```

### Windows — Prebuilt executable

Download `Proxmox SPICE Manager.exe` from the [Releases](../../releases) page. virt-viewer must still be installed separately — the app will prompt you on first launch.

### Windows — Build your own .exe

See [build-windows.md](build-windows.md) for full instructions.

Once the app is running, see [proxmox-setup.md](proxmox-setup.md) to configure your Proxmox connection.

## Proxmox Setup

### Authentication

The app supports two authentication methods:

- **API Token** (recommended) — create a dedicated token in the Proxmox UI under Datacenter → Permissions → API Tokens. The token secret is stored encrypted (keyring on Linux, DPAPI on Windows).
- **Password** — prompted on each session. Not stored to disk.

### Required Permissions

Create a role or use `PVEVMUser` with the following privileges:

| Privilege | Purpose |
|---|---|
| `VM.Console` | Launch SPICE sessions |
| `VM.PowerMgmt` | Start, shutdown, stop VMs |
| `VM.Snapshot` | Create and delete snapshots |
| `VM.Snapshot.Rollback` | Rollback to snapshots |
| `Pool.Audit` | Show resource pool membership |
| `Sys.Audit` | List VMs across cluster nodes |

Example setup using the Proxmox CLI:

```bash
# Create a user
pveum useradd spice@pve -comment "SPICE Manager"

# Create an API token (disable privilege separation for simplicity)
pveum user token add spice@pve spice-token -privsep 0

# Assign the PVEVMUser role at the root level
pveum aclmod / -user spice@pve -role PVEVMUser
```

### VM Configuration

> **SPICE is for graphical (GUI) operating systems only.** Headless or CLI-only VMs won't benefit from a SPICE console — use SSH for those instead.

VMs must have a **QXL display adapter** to appear in the app:

1. In the Proxmox web UI, select your VM → Hardware → Display
2. Set the display to **SPICE (qxl)**

#### Guest drivers (required for a working SPICE session)

SPICE sessions will open but won't function correctly without the proper guest drivers installed inside the VM.

**Windows guests** — install both:
- **VirtIO drivers** — covers storage, network, and other paravirtualized devices. Download the ISO from the [Fedora VirtIO project](https://fedorapeople.org/groups/virt/virtio-win/direct-downloads/stable-virtio/virtio-win.iso) and run `virtio-win-guest-tools.exe` inside the VM.
- **SPICE guest tools** — enables display resizing, clipboard sharing, and mouse integration. Download from [spice-space.org](https://www.spice-space.org/download.html).

**Linux guests** — install `spice-vdagent` for clipboard sharing and display resizing:
```bash
# Fedora
sudo dnf install spice-vdagent

# Debian/Ubuntu
sudo apt install spice-vdagent
```

Only VMs with QXL/SPICE displays are shown — non-SPICE VMs are filtered out automatically.

## Configuration

### Config file locations

| Platform | Path |
|---|---|
| Linux | `~/.config/proxmox-spice/connections.json` |
| Windows | `%APPDATA%\proxmox-spice\connections.json` |

The config file stores cluster definitions, theme preference, column order, and (on Windows) DPAPI-encrypted token secrets. On Linux, secrets are stored separately in the OS keyring.

### Import / Export

Use the sidebar Import/Export buttons to transfer cluster configurations between machines:

- **Export** decrypts secrets and writes them as plaintext JSON — treat the exported file as sensitive
- **Import** re-encrypts secrets with the local machine's credentials and handles name collisions by appending "(Imported)"

## Security Notes

- **Linux:** Token secrets are stored in your desktop environment's keyring (GNOME Keyring, KDE Wallet, etc.) via the `keyring` Python package. They are never written to the JSON config file.
- **Windows:** Token secrets are encrypted using Windows DPAPI (`CryptProtectData`), which ties the encryption key to your Windows user account. The encrypted blobs are stored as base64 in `connections.json`. They cannot be decrypted by another user or on another machine.
- **SSL:** The app disables certificate verification for Proxmox API connections (self-signed certs are the default in Proxmox). All communication still uses HTTPS.
- **Export files** contain plaintext secrets — handle them accordingly.

## Tips

- **Clipboard sharing** requires `spice-vdagent` running inside the guest VM with a graphical session (not a raw TTY). For CLI-only VMs, use SSH for copy/paste.
- **ACPI Shutdown** sends a graceful shutdown signal — the guest OS must handle ACPI events. **Force Stop** kills the QEMU process immediately (unsaved data will be lost).
- **Polling** — after power or snapshot actions, the app polls every 10 seconds (up to 2 minutes) for state changes, then refreshes the VM list.

## Troubleshooting

| Problem | Solution |
|---|---|
| No VMs appear after connecting | Verify your API token has `Sys.Audit` permission and that VMs use QXL display |
| "Token secret not found" error | Re-edit the cluster and re-enter the token secret |
| SPICE window opens but is black | Install `spice-vdagent` and a QXL driver inside the guest VM |
| remote-viewer not found (Windows) | Install virt-viewer from [spice-space.org](https://www.spice-space.org/download.html) and restart the app |
| Clipboard not working | Ensure `spice-vdagent` is running in a graphical session, not a TTY |

## Project Structure

```
proxmox-spice-manager.py        # Linux edition (single file)
proxmox-spice-manager-win.py    # Windows edition (single file)
README.md                       # This file
proxmox-setup.md                # Proxmox server config and app setup (all platforms)
linux-setup.md                  # Linux installation walkthrough with screenshots
build-windows.md                # Instructions for building a standalone Windows .exe
```

Both editions are self-contained single-file applications with no external package dependencies beyond the platform prerequisites listed above.

## Version History

- **2.1.1** — Bug fixes: secret migration safety, API error normalization, sort persistence, auth passed to polling methods
- **2.1.0** — Rewrote to pure `urllib` (removed curl/jq deps), added column filters, snapshot indicators, pool column, import/export
- **2.0.0** — Full GUI rewrite with multi-cluster support, themes, snapshot management, keyring integration
- **1.0.0** — Initial shell script wrapper for `remote-viewer`
