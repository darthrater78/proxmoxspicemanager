# Proxmox SPICE Connection Manager

A desktop GUI application for managing and launching SPICE console sessions to Proxmox VE virtual machines. No browser required.

- **Windows** — native WPF app (C#/.NET 8), single-file exe with zero dependencies
- **Linux** — Python + tkinter

![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20Windows-blue)
![License](https://img.shields.io/badge/license-MIT-green)

**Current version: 3.0.0** · [GitHub](https://github.com/darthrater78/proxmoxspicemanager) · [Release notes](https://github.com/darthrater78/proxmoxspicemanager/releases/tag/v3.0.0) · [Changelog](CHANGELOG.md)

Both platforms share one version number, and each release carries both the Windows exe and the Linux script.

## Features

- **Multi-cluster management** — connect to multiple Proxmox clusters with saved credentials
- **Auto-discovery** — automatically detects SPICE-enabled VMs across all cluster nodes
- **Live IP address** — shows each running VM's IP via QEMU guest agent (requires `VM.GuestAgent.Audit` permission)
- **One-click SPICE launch** — opens `remote-viewer` sessions from a VM's Connect button (Windows), a double-click, or Enter
- **VMs grouped by node, or one flat list** — each node shows how many of its VMs are running; sort by any column, search by name, ID, IP, pool, notes or OS, and filter to running or stopped VMs
- **VM power controls** — Start, ACPI Shutdown, Reboot and Force Stop; Ctrl-click or Shift-click to act on several VMs at once
- **Keyboard shortcuts** — Enter opens the console, S starts, Shift+S shuts down, R reboots, P opens snapshots, Ctrl+. force stops, / searches, F5 refreshes
- **Snapshot management** — create, rollback, and delete snapshots with a full dialog, plus quick-rollback to the latest snapshot
- **Secure credential storage** — Linux: OS keyring (GNOME Keyring, KDE Wallet, etc.); Windows: DPAPI encryption tied to your Windows user account
- **5 built-in themes and 7 accent colours** — Catppuccin Mocha, Catppuccin Latte, Nord, Dracula, OLED Dark; orange accent by default, switchable from the Appearance button next to Settings
- **Import / Export** — share cluster configurations between machines (with plaintext secret warning on export)
- **App menu integration** — install as a desktop app (Linux: `.desktop` file; Windows: Start Menu shortcut)
- **Prerequisite checker** — first-run dialog detects missing dependencies and helps you install them
- **Debug logging** — optional timestamped log file for diagnosing API connectivity issues (toggle in the Settings menu; Linux: `~/.config/proxmox-spice/debug.log`, Windows: `%APPDATA%\proxmox-spice\debug.log`)

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
> - **Linux** — download `proxmox-spice-manager.py` from [Releases](../../releases/latest) and run it (Fedora/Debian walkthrough with screenshots) → [linux-setup.md](linux-setup.md)

### Verifying a download

Release files are built by GitHub Actions from the tagged commit. Each release has a `SHA256SUMS` file, and both files carry a build provenance attestation that you can check with the [GitHub CLI](https://cli.github.com/):

```bash
sha256sum -c SHA256SUMS --ignore-missing
gh attestation verify Proxmox-SPICE-Manager.exe -R darthrater78/proxmoxspicemanager
gh attestation verify proxmox-spice-manager.py -R darthrater78/proxmoxspicemanager
```

## Configuration

### Config file locations

| Platform | Path |
|---|---|
| Linux | `~/.config/proxmox-spice/connections.json` |
| Windows | `%APPDATA%\proxmox-spice\connections.json` |

The config file stores cluster definitions, theme and accent, VM notes, and (on Windows) DPAPI-encrypted token secrets. On Linux, secrets are stored separately in the OS keyring.

### Import / Export

Use Import clusters and Export clusters in the Settings menu to transfer cluster configurations between machines:

- **Export** decrypts secrets and writes them as plaintext JSON — treat the exported file as sensitive
- **Import** handles name collisions by appending "(Imported)". On Linux it moves secrets into the keyring. On Windows, imported secrets are not yet re-encrypted and must be re-entered by editing the cluster (known issue).
- Export files are not yet interchangeable between the Windows and Linux apps (known issue).

## Security Notes

- **Linux:** Token secrets are stored in your desktop environment's keyring (GNOME Keyring, KDE Wallet, etc.) via the `keyring` Python package. They are never written to the JSON config file.
- **Windows:** Token secrets are encrypted using Windows DPAPI (`CryptProtectData`), which ties the encryption key to your Windows user account. The encrypted blobs are stored as base64 in `connections.json`. They cannot be decrypted by another user or on another machine.
- **TLS:** Certificates signed by a CA your system trusts work as they are. Proxmox's own self-signed certificate is shown with its SHA-256 fingerprint the first time you connect; compare it with Node → System → Certificates → Fingerprint in Proxmox and confirm, and the app pins it for that cluster (like SSH host keys). After that only that certificate is accepted, and a changed one brings up a warning before anything is sent. The check happens before the API token or password leaves your machine. Host URLs must use `https://`; the apps refuse to save or log in to a plain `http://` URL.
- **Export files** contain plaintext secrets — handle them accordingly.

## Tips

- **Clipboard sharing** requires `spice-vdagent` running inside the guest VM with a graphical session (not a raw TTY). For CLI-only VMs, use SSH for copy/paste.
- **ACPI Shutdown** sends a graceful shutdown signal — the guest OS must handle ACPI events. **Force Stop** kills the QEMU process immediately (unsaved data will be lost).
- **Polling** — after power or snapshot actions, the Linux app polls every 10 seconds (up to 2 minutes) for state changes, then refreshes the VM list. The Windows app waits a few seconds and refreshes once.

## Troubleshooting

| Problem | Solution |
|---|---|
| No VMs appear after connecting | Verify your API token has `VM.Audit` permission and that VMs use QXL display. Turn on the debug log in the Settings menu and check the log file for details (Linux: `~/.config/proxmox-spice/debug.log`, Windows: `%APPDATA%\proxmox-spice\debug.log`) |
| IP column shows "no agent" | The VM does not have `agent: 1` enabled in its Proxmox config — this is expected |
| IP column shows "agent error" | The QEMU guest agent is enabled but not responding — check that `qemu-guest-agent` is installed and running inside the VM |
| "Token secret not found" error | Re-edit the cluster and re-enter the token secret |
| SPICE window opens but is black | Install `spice-vdagent` and a QXL driver inside the guest VM |
| remote-viewer not found (Windows) | Install virt-viewer from [spice-space.org](https://www.spice-space.org/download.html) and restart the app |
| Clipboard not working | Ensure `spice-vdagent` is running in a graphical session, not a TTY |

## Project Structure

```
windows/                        # Native WPF Windows app (C#/.NET 8)
proxmox-spice-manager.py        # Linux edition (standalone, single file)
scripts/                        # check.sh, build.sh, version.sh (used by CI and locally)
.github/                        # CI, release and workflow-lint workflows; Dependabot config
CHANGELOG.md                    # Release history
README.md                       # This file
proxmox-setup.md                # Proxmox server config and app setup (all platforms)
linux-setup.md                  # Linux installation walkthrough with screenshots
```

The Linux script is a standalone single-file Python app. The WPF app in `windows/` is a standalone C#/.NET 8 project. Features are kept in parity where the platforms allow; the known gaps are noted above.

## Development

```bash
pip install -r requirements-dev.txt
bash scripts/check.sh    # version agreement, changelog entry, Python lint, shellcheck
bash scripts/build.sh    # Windows exe into dist/ (needs the .NET 8 SDK; works on Linux too)
```

The version is declared in `windows/ProxmoxSpiceManager.csproj` and in `APP_VERSION` plus the docstring of `proxmox-spice-manager.py`; `scripts/version.sh` fails if they disagree. To release, merge a version bump with its `CHANGELOG.md` entry, then push a `vX.Y.Z` tag on `main`. A `vX.Y.Z-dev.N` tag on a branch builds a pre-release.

## Version History

See [CHANGELOG.md](CHANGELOG.md).
