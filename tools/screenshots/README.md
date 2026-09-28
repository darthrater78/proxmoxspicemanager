# Screenshots

Renders the Windows app on Linux, so screenshots and design reviews don't need a
Windows machine. `windows/Shots.csproj` is a small harness that runs the app's
real `MainWindow` under Wine, fills it with mock clusters and VMs (it never
touches a network), and saves PNGs.

```sh
tools/screenshots/run.sh              # writes dist/screenshots/
tools/screenshots/run.sh /some/dir    # or anywhere else
```

Needs `wine`, `xvfb-run`, `dotnet` (8 or later), `python3`, `curl`, `unzip`, and
the Liberation and DejaVu fonts (`fonts-liberation`, `fonts-dejavu-core` on
Debian). Everything else goes in `~/.cache/proxmox-spice-screenshots/`: font
downloads (checked against pinned SHA-256 hashes), a Python venv for fontTools,
a Wine prefix of its own, and the build. A first run takes under a minute.

## Output

| File | What |
|---|---|
| `windows-main.png` | The main window, Catppuccin Mocha, first VM selected |
| `windows-main-<theme>.png` | The same in each theme |
| `windows-state-*.png` | Multi-select, search, the Running filter, and a search with no matches |
| `proposal-*.png` | Design prototypes from `windows/proposals/` |
| `shots.log` | Progress and errors |

## Fonts

Segoe UI and the other Windows fonts can't be redistributed, so
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

Popups (the appearance flyout, the Settings menu) open in windows of their own,
so they don't appear in captures of the real `MainWindow`.
