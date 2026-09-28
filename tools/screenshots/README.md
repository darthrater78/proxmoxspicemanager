# Screenshots

Renders both apps on Linux, so screenshots and design reviews need neither a
Windows machine nor a Proxmox cluster. Each harness runs the app's real main
window, fills it with the same mock clusters and VMs (nothing touches a network,
a keyring or your own config), and saves PNGs:

- `windows/Shots.csproj` runs the WPF `MainWindow` under Wine.
- `linux/shots.py` loads `proxmox-spice-manager.py`, points its config at a
  temporary directory, replaces the refresh with mock VMs, and grabs the window
  with Pillow.

```sh
tools/screenshots/run.sh              # writes dist/screenshots/
tools/screenshots/run.sh /some/dir    # or anywhere else
```

Needs `wine`, `xvfb-run`, `dotnet` (8 or later), `python3`, `curl`, `unzip`, and
the Liberation and DejaVu fonts (`fonts-liberation`, `fonts-dejavu-core` on
Debian). The Linux screenshots also need Tk (`python3-tk`); without it they are
skipped with a warning. Everything else goes in
`~/.cache/proxmox-spice-screenshots/`: font downloads (checked against pinned
SHA-256 hashes), a Python venv with `requirements.txt`, a Wine prefix of its
own, and the build. A first run takes under a minute.

## Output

| File | What |
|---|---|
| `windows-main.png`, `linux-main.png` | The main window, Catppuccin Mocha, first VM selected |
| `*-main-<theme>.png` | The same in each theme |
| `*-state-*.png` | Multi-select, search, the Running filter, a search with no matches, the flat list sorted by address, and (Linux) a folded node |
| `linux-appearance.png`, `linux-settings.png` | The Linux popups (WPF popups can't be captured, see below) |
| `proposal-*.png` | Design prototypes from `windows/proposals/` |
| `shots.log` | Progress and errors |

## Fonts

The Linux app uses the system's fonts (DejaVu Sans on Debian), as it would on a
user's machine. For the Windows app, Segoe UI and the other Windows fonts can't be redistributed, so
`prep_fonts.py` renames open stand-ins to the family names WPF asks for:
Selawik (Microsoft's metric-compatible Segoe UI stand-in) for Segoe UI and
Tahoma, Liberation for Arial, Times New Roman and Courier New, and DejaVu Sans
for Segoe UI Symbol. Cascadia Code is the real font. Text metrics match Windows
closely, but glyph shapes differ a little from a real Windows screenshot.

## Design prototypes

`windows/proposals/*.xaml` are loose XAML files (no code-behind) bound to the
mock `ProposalData` in `Shots.cs`. One that uses the app's `Theme*` brushes is
rendered once per theme; one with an appearance flyout (`ShowAppearance`) is
also rendered with the flyout open, in every theme and every accent.

WPF popups (the appearance flyout, the Settings menu) open in windows of their
own, so they don't appear in captures of the real `MainWindow`. The Linux
harness grabs the screen area instead, so its popups do.
