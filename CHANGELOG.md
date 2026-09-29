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
  snapshots, status or notes, by clicking a column heading or from the Sort
  button; picking the same key again reverses it. Grouping and sort
  are saved (`group_by_node`, `vm_sort`, `vm_sort_desc`, shared by both apps).
  Node headings are shaded bands that fold with a click. A panel on the right shows the selected VM's details,
  its notes and every action; Quick Rollback lives there as "Roll back to
  latest snapshot". Cluster editing, import and export, the debug log,
  prerequisites, the project links and (Linux) the app-menu and `.desktop`
  helpers move into a Settings menu in the sidebar. Double-click a cluster to
  edit it.
- Each VM row has its own Connect button (Start when the VM is stopped), and
  its status in colour. The Linux list is now drawn the same way as the Windows
  one: OS badge, name over ID and pool, addresses, notes, snapshot count,
  status and the button.
- Loading a cluster is much faster when a node is down. Both apps skip VMs on
  nodes Proxmox reports offline (asking about them made Proxmox wait seconds
  before answering 595) and name those nodes under the cluster name
  ("1 node offline (pve-daruk)"). Windows drops the per-node VM list requests,
  which repeated what `cluster/resources` already returns. Linux fetches VM
  configs and snapshots in parallel and fills in guest-agent addresses after
  the list is on screen, as Windows does.
- The checkbox column is gone. Select several VMs with Ctrl-click or
  Shift-click; actions apply to the whole selection, and Open console opens
  every running VM in it.
- Starting VMs no longer asks for confirmation. Shut down, reboot and force
  stop still do.
- Linux: buttons use the same line icons as Windows (play, power, refresh,
  camera, undo, stop, monitor, plus, gear, search) in place of text symbols.
- Linux: requests to a cluster reuse an open HTTPS connection instead of a new
  TLS handshake each time, as Windows does. Only reads reuse one; actions
  (start, snapshot, …) always get a fresh connection, so one can never be sent
  twice.

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

### Security

- **"Skip TLS verification" is replaced by certificate pinning.** The option
  accepted any certificate, so anyone able to intercept the connection could
  pose as the Proxmox server and receive the API token or password. Now a
  certificate this system doesn't trust (Proxmox's self-signed one) is shown
  with its SHA-256 fingerprint on first connect, and saved for that cluster
  (`tls_fingerprint`) once you confirm it; after that only that certificate is
  accepted. A different certificate brings up a warning with the new
  fingerprint, defaulting to No. The check runs in the TLS handshake, before a
  token or password is sent. Clusters that had the option on are asked once.
  The cluster dialog shows the pinned fingerprint with a Forget button, and a
  pin is dropped when the host changes.
- Windows: importing clusters saved each token secret in plain text in
  `connections.json` (and the cluster then couldn't log in). Import now
  encrypts it with DPAPI, as adding a cluster does.

### Fixed

- Password logins stopped working after two hours, when Proxmox's ticket
  expired, because the apps kept using it. A ticket is now renewed after an
  hour without asking (Proxmox accepts the current ticket in place of the
  password), and the password is asked again only if renewal fails. API
  token logins have no ticket and are unchanged.
- After Start, Shut down, Reboot, Force stop, a rollback or a snapshot change,
  the list could show the old state: Windows refreshed after a fixed 3 seconds
  (2–3 s in the Snapshots window), Linux checked every 10 seconds. Both apps
  now follow the Proxmox task the action started, checking each second, and
  refresh as soon as it ends. A task that fails shows Proxmox's reason (for
  example "start failed: …"); Windows used to say nothing. Windows also skips
  VMs already in the target state, as Linux does.
- Linux: "Export .desktop for selected VM" made a launcher that opened the
  manager, not the VM, and assumed the script was `~/proxmox-spice-manager.py`.
  The launcher now runs `proxmox-spice-manager.py --connect "<cluster>" <vmid>`
  from where the script really is: it logs in as the manager does (keyring
  token or password prompt, pinned certificate), offers to start a stopped VM,
  opens the console and exits, and works while the manager is open. Its file
  name includes the cluster, so the same VM ID on two clusters no longer clashes.
- Linux: when the system keyring couldn't store a token secret (no keyring
  running, or a locked wallet), the cluster looked saved but couldn't log in
  later. The app now says which cluster's secret wasn't saved and why.
- Export files work across platforms. Both apps write the token secret as
  `token_secret` and read that, plus the older Windows exports that put the
  plaintext secret in `token_secret_enc`. A secret that is a DPAPI blob (from a
  Windows config file) can't be read by another user or machine; import names
  those clusters so the secret can be entered again.
- Linux: editing a cluster kept using its old settings (host, token, TLS
  option) until the app was restarted.
- At the smallest window size (1000×600), on both platforms: the search box
  covered the cluster name, the IPv6, Group and Sort buttons overlapped the
  filters, and the details panel cut off its last actions (Windows lost Force
  stop). Now the search box narrows first, then Refresh drops its label, and a
  name that still doesn't fit ends in "…"; the view buttons move to a second
  row; and the details panel scrolls with Force stop kept in view. Windows
  also drops the Notes, Snapshots and Address columns as the window narrows,
  as Linux does, instead of cutting off Status and Connect.
- Linux: closing the window while VMs were loading printed "Exception in
  thread … main thread is not in main loop".

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
  like on Linux. On both apps every heading carries a ↕ mark, and the sorted
  one shows ▲ or ▼ (in the accent colour on Windows).
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
