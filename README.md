# Proxmox SPICE Connection Manager

A desktop GUI application for managing and launching SPICE console sessions to Proxmox VE virtual machines. No browser required.

- **Windows** — native WPF app (C#/.NET 8), single-file exe with zero dependencies
- **Linux** — Python + tkinter

![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## Features

- **Multi-cluster management** — connect to multiple Proxmox clusters with saved credentials
- **Auto-discovery** — automatically detects SPICE-enabled VMs across all cluster nodes
- **Live IP address** — shows each running VM's IP via QEMU guest agent (requires `VM.GuestAgent.Audit` permission)
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

### Windows (WPF app)

| Dependency | How to install |
|---|---|
| virt-viewer | [spice-space.org/download.html](https://www.spice-space.org/download.html) — install the Windows MSI |

The WPF app is a self-contained single-file exe — no Python, no .NET runtime install needed.

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

## Getting Started

> [!IMPORTANT]
> **Step 1 — Configure Proxmox first:** create a user, role, API token, and set up your VMs → [proxmox-setup.md](proxmox-setup.md)
>
> **Then install the app for your platform:**
> - **Windows** — download `Proxmox-SPICE-Manager.exe` from [Releases](../../releases/latest)
> - **Linux** — run `proxmox-spice-manager.py` (Fedora/Debian walkthrough with screenshots) → [linux-setup.md](linux-setup.md)

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
- **SSL:** TLS certificate verification can be skipped per-cluster via the "Skip TLS verification" option (for self-signed certs, common in Proxmox). All communication still uses HTTPS.
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
windows/                        # Native WPF Windows app (C#/.NET 8)
proxmox-spice-manager.py        # Linux edition (standalone, single file)
README.md                       # This file
proxmox-setup.md                # Proxmox server config and app setup (all platforms)
linux-setup.md                  # Linux installation walkthrough with screenshots
```

The Linux script is a standalone single-file Python app. The WPF app in `windows/` is a standalone C#/.NET 8 project. Both have full feature parity.

## Version History

- **1.1.2-wpf** — Fix selected row text turning blue for stopped VMs (preserve running/stopped color when selected)
- **1.1.1-wpf** — Fix notes ComboBox theming (dark background for edit field, dropdown, and selected item), adjust column widths for IP column fit
- **1.1.0-wpf** — Add live VM IP address column (via QEMU guest agent), running/stopped row color differentiation, release notes link uses /releases/latest
- **1.0.0-wpf** — Native WPF Windows app (C#/.NET 8): full feature parity with Python version, notes editing with dropdown, column filtering, parallel API refresh, single-instance guard
- **2.2.4** — Fix selected row text turning blue for stopped VMs (preserve running/stopped color when selected)
- **2.2.3** — Extract shared base module, fix PowerShell injection in shortcut creation
- **2.2.2** — Add GitHub and Release Notes links in header
- **2.2.1** — Filter UI redesign, power action UX, security hardening
- **2.2.0** — Bulk select, reboot, notes column, security hardening
- **2.1.4** — App icon update
- **2.1.3** — App icon — SPICE text with S monogram for small sizes
- **2.1.1** — Bug fixes: secret migration safety, API error normalization, sort persistence, auth passed to polling methods
- **2.1.0** — Rewrote to pure `urllib` (removed curl/jq deps), added column filters, snapshot indicators, pool column, import/export
- **2.0.0** — Full GUI rewrite with multi-cluster support, themes, snapshot management, keyring integration
- **1.0.0** — Initial shell script wrapper for `remote-viewer`
