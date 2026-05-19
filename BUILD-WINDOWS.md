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

1. Open PowerShell and navigate to the folder containing `proxmox-spice-manager-win.py`:
   ```powershell
   cd C:\path\to\your\folder
   ```

2. Run PyInstaller:
   ```powershell
   pyinstaller --onefile --windowed --name "Proxmox SPICE Manager" proxmox-spice-manager-win.py
   ```

   | Flag | Purpose |
   |---|---|
   | `--onefile` | Bundles everything into a single `.exe` instead of a folder |
   | `--windowed` | Suppresses the console window (GUI app) |
   | `--name` | Sets the output filename |

3. Wait about 30–60 seconds. When it finishes you'll see:
   ```
   Building EXE from EXE-00.toc completed successfully.
   ```

4. Your executable is at:
   ```
   dist\Proxmox SPICE Manager.exe
   ```

## Optional: Custom Icon

If you have a `.ico` file, add `--icon` to the build command:

```powershell
pyinstaller --onefile --windowed --icon=app-icon.ico --name "Proxmox SPICE Manager" proxmox-spice-manager-win.py
```

To convert a `.png` to `.ico`, you can use an online tool like [convertio.co](https://convertio.co/png-ico/) or ImageMagick:

```powershell
magick convert app-icon.png -define icon:auto-resize=256,128,64,48,32,16 app-icon.ico
```

## Output Structure

After building, your folder will look like:

```
your-folder/
├── proxmox-spice-manager-win.py    ← source (keep this)
├── Proxmox SPICE Manager.spec      ← PyInstaller config (auto-generated)
├── build/                           ← temp build files (safe to delete)
└── dist/
    └── Proxmox SPICE Manager.exe   ← your standalone app
```

The `build/` folder and `.spec` file can be deleted — they're only needed during the build. If you want to rebuild later, PyInstaller will recreate them.

## What Gets Bundled

The `.exe` includes:

- Python interpreter
- tkinter (GUI framework)
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
