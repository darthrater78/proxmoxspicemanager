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

## Getting Started

1. **[proxmox-setup.md](proxmox-setup.md)** — Configure Proxmox first: create a user, role, API token, and set up your VMs for SPICE
2. **[linux-setup.md](linux-setup.md)** — Install and run on Linux (Fedora/Debian walkthrough with screenshots)
3. **[build-windows.md](build-windows.md)** — Run from source or build a standalone `.exe` on Windows

Windows users can also grab the prebuilt `Proxmox SPICE Manager.exe` directly from the [Releases](../../releases) page.

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
| No VMs appear after connecting | Verify your API token has `VM.Audit` permission and that VMs use QXL display |
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
