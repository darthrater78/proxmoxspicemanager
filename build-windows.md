# Building Proxmox SPICE Manager for Windows

This guide walks through building a standalone `.exe` from `proxmox-spice-manager-win.py`.

## Prerequisites

1. **Python 3.9+** — download from [python.org](https://www.python.org/downloads/)
   - During install, check **"Add Python to PATH"**
   - Verify: open PowerShell and run `python --version`

2. **PyInstaller** — the tool that bundles Python + your script into a single `.exe`
   ```powershell
   pip install pyinstaller
   ```

## Build Steps

1. Open PowerShell and navigate to the project folder:
   ```powershell
   cd C:\path\to\proxmoxspicemanager
   ```

2. Run PyInstaller using the included `.spec` file:
   ```powershell
   pyinstaller "Proxmox SPICE Manager.spec"
   ```

   The `.spec` file configures single-file mode, windowed (no console), the app icon, and ensures the shared `proxmox_spice_common` module is bundled correctly.

3. Wait about 30–60 seconds. When it finishes you'll see:
   ```
   Building EXE from EXE-00.toc completed successfully.
   ```

4. Your executable is at:
   ```
   dist\Proxmox SPICE Manager.exe
   ```

## Output Structure

After building, your folder will look like:

```
your-folder/
├── proxmox_spice_common.py          ← shared base module (required for build)
├── proxmox-spice-manager-win.py     ← Windows entry point
├── Proxmox SPICE Manager.spec       ← PyInstaller config (committed to repo)
├── build/                            ← temp build files (safe to delete)
└── dist/
    └── Proxmox SPICE Manager.exe    ← your standalone app
```

The `build/` folder can be deleted — it's only needed during the build. The `.spec` file is part of the project and should be kept.

## What Gets Bundled

The `.exe` includes:

- Python interpreter
- tkinter (GUI framework)
- `proxmox_spice_common` — shared module with themes, API layer, dialogs, and base class
- All standard library modules the app uses (`json`, `ssl`, `urllib`, `ctypes`, etc.)
- DPAPI encryption (via `ctypes` — no extra packages)

## What Does NOT Get Bundled

- **virt-viewer / remote-viewer.exe** — must be installed separately from [spice-space.org](https://www.spice-space.org/download.html). The app will find it automatically via PATH, common install directories, or the Windows registry.

## Distributing

To share the app with others:

1. Give them `Proxmox SPICE Manager.exe` — that's the only file they need
2. They must install virt-viewer separately (the app's prereq checker will prompt them on first launch)
3. No Python installation required on the target machine

## Troubleshooting

| Problem | Solution |
|---|---|
| `pyinstaller` not recognized | Run `pip install pyinstaller` again, or use `python -m PyInstaller` instead |
| Antivirus flags the `.exe` | Common false positive with PyInstaller. Add an exclusion for the `dist/` folder, or sign the exe with a code signing certificate |
| App opens then immediately closes | Rebuild without `--windowed` to see error output in the console, then fix and rebuild with `--windowed` |
| "Failed to execute script" error | Same as above — rebuild without `--windowed` to diagnose |
| Large file size (30–50 MB) | Normal for PyInstaller `--onefile` — it bundles the entire Python runtime. Use `--exclude-module` to trim unused modules if needed |
| Build fails with import errors | Make sure you're building on the same Python version you tested with |
