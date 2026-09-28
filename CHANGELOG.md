# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

From 3.0.0 on, the Windows app and the Linux script share one version number
and ship in the same GitHub release. A change made on one platform is carried
to the other where the platforms allow it.

## [Unreleased]

### Changed

- **Redesigned main window, on both platforms.** VMs are grouped by node with a
  running count per node, or in one flat list ("Group by node" toggles it; the
  flat list shows each VM's node). A search box (name, ID, IP, node, pool,
  notes, OS) and All / Running / Stopped filters replace the per-column
  filters and column dragging. Sort by name, ID, address, node, pool,
  snapshots, status or notes: Linux by clicking a column heading, Windows from
  the Sort button; picking the same key again reverses it. Grouping and sort
  are saved (`group_by_node`, `vm_sort`, `vm_sort_desc`, shared by both apps).
  Linux node headings are shaded and fold with a click. A panel on the right shows the selected VM's details,
  its notes and every action; Quick Rollback lives there as "Roll back to
  latest snapshot". Cluster editing, import and export, the debug log,
  prerequisites, the project links and (Linux) the app-menu and `.desktop`
  helpers move into a Settings menu in the sidebar. Double-click a cluster to
  edit it.
- Windows: each VM row has its own Connect button (Start when the VM is
  stopped). The Linux table can't hold buttons; double-click a VM, press Enter
  or use the panel's Open SPICE console.
- The checkbox column is gone. Select several VMs with Ctrl-click or
  Shift-click; actions apply to the whole selection, and Open console opens
  every running VM in it.
- Starting VMs no longer asks for confirmation. Shut down, reboot and force
  stop still do.

### Added

- Keyboard shortcuts: Enter opens the console, S starts, Shift+S shuts down,
  R reboots, P opens snapshots, Ctrl+. force stops, / jumps to search and F5
  refreshes. Each button shows its key.
- Accent colours. Orange is the default; Blue, Teal, Green, Purple, Red and
  Yellow are presets that take each theme's own shade. Theme and accent are
  picked from the Appearance button next to Settings. Text on the accent colour
  switches between dark and light for contrast. Saved as `accent` in the config.
- An OS badge and name per VM, read from the VM's `ostype`.
- `tools/screenshots/`: renders both apps with mock data, in every theme, for
  documentation and design review (Windows under Wine, Linux natively, both on
  Xvfb).

### Fixed

- Linux: editing a cluster kept using its old settings (host, token, TLS
  option) until the app was restarted.

## [3.0.0] - 2026-09-27

### Changed

- **One version for both platforms.** Windows moves from 1.2.1 and Linux from
  2.3.0 to 3.0.0. Each release now carries both `Proxmox-SPICE-Manager.exe` and
  `proxmox-spice-manager.py`, plus a `SHA256SUMS` file. Tags are plain
  `vX.Y.Z`; the `-wpf` suffix is retired.
- **Releases are built by GitHub Actions** from the tagged commit, instead of by
  hand, with a build provenance attestation for both files (see the README for
  how to verify a download).
- Windows: the window title and the Release Notes link come from the build's own
  version. The link opens this version's notes instead of the latest release.
- Windows: the single-file exe is compressed, so the download is smaller.
- Linux changes from 2.3.0, which was never released on its own: debug logging
  toggle with a rotating log file (5 MB cap), VM notes scoped by cluster name so
  they no longer collide across clusters, and a single-instance guard.

### Security

- Both apps refuse a host URL that is not `https://` when saving a cluster, and
  never send a password login over plain HTTP (an imported config could
  previously do so).
- Windows: the SPICE connection file, which holds the session password, gets a
  random name and is created fresh, instead of a predictable
  `pve-spice-<vmid>.vv` in `%TEMP%`.
- Windows: `remote-viewer.exe` is looked up in its install folders and the
  registry before `PATH`, and relative `PATH` entries are skipped. The Start
  Menu shortcut helper runs PowerShell from System32 by full path.

### Added

- Both apps show every address the guest agent reports, grouped by adapter in
  the details panel. The list's Address column widens with the window and
  shows as many as fit, with "+N" for the rest. Loopback and link-local
  addresses are left out. IPv6 addresses are hidden
  unless the "IPv6" chip beside "Group by node" is on (`show_ipv6`, shared by
  both apps).
- Both apps show each VM's Notes from Proxmox: the first line in the list's
  Notes column (this app's own note where Proxmox has none), and the text in
  a read-only "Proxmox" row of the details panel.
- Windows: notes get their own column in the VM list, instead of trailing the
  grey second line, and the list has column headings that sort when clicked,
  like on Linux.
- Windows: node headings are a shaded band that folds its VMs away when
  clicked, like on Linux.
- GitHub and Release notes links in the app header, moved out of Settings.
- Linux: Ctrl+A selects every VM on screen, as on Windows.
- MIT `LICENSE` file (the README already stated MIT).

### Fixed

- Linux: a node heading could not be folded while it held the selected VM.
- Linux: in narrow windows the Status and Notes columns were cut off the
  right edge. The least-needed columns (Pool, Snaps, Node, ID, Address) now
  make way instead, never the one the list is sorted by.
- A guest agent enabled as `enabled=1,…` in the VM config was not detected.
  Linux now also shows "no agent" and "agent error" like Windows.
- Linux: when launching a SPICE session failed, the error dialog never
  appeared (the handler raised `NameError`). It now shows the error.

## Before 3.0.0

Windows and Linux were versioned separately until 3.0.0.

### Windows (WPF)

- **1.2.1** — Improve SPICE launch speed: reuse HTTP connections across API calls (eliminates per-request TLS handshake), cache remote-viewer path after first lookup
- **1.2.0** — Add debug logging toggle, resilient VM refresh (guest-agent failures no longer block or crash the app), IP column shows "no agent"/"agent error" status, log rotation (5 MB cap)
- **1.1.2** — Fix selected row text turning blue for stopped VMs (preserve running/stopped color when selected)
- **1.1.1** — Fix notes ComboBox theming (dark background for edit field, dropdown, and selected item), adjust column widths for IP column fit
- **1.1.0** — Add live VM IP address column (via QEMU guest agent), running/stopped row color differentiation, release notes link uses /releases/latest
- **1.0.0** — Native WPF Windows app (C#/.NET 8): full feature parity with Python version, notes editing with dropdown, column filtering, parallel API refresh, single-instance guard

### Linux (Python)

- **2.3.0** — Never released on its own; shipped in 3.0.0 (see above)
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

[3.0.0]: https://github.com/darthrater78/proxmoxspicemanager/releases/tag/v3.0.0
