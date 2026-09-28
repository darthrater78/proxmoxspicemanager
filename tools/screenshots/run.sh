#!/usr/bin/env bash
# Renders screenshots of both apps: the Windows app under Wine and Xvfb, the
# Linux app natively under Xvfb. See README.md.
# Usage: tools/screenshots/run.sh [output dir]   (default: dist/screenshots)
set -euo pipefail

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
cache=${XDG_CACHE_HOME:-$HOME/.cache}/proxmox-spice-screenshots
out=$(realpath -m "${1:-$repo/dist/screenshots}")

for tool in wine xvfb-run dotnet python3 curl unzip sha256sum realpath; do
    command -v "$tool" >/dev/null || { echo "missing tool: $tool" >&2; exit 1; }
done
for dir in liberation dejavu; do
    [[ -d /usr/share/fonts/truetype/$dir ]] || {
        echo "missing /usr/share/fonts/truetype/$dir (install fonts-liberation and fonts-dejavu-core)" >&2
        exit 1
    }
done

# Download once, verified against a pinned hash
fetch() { # url sha256 dest
    if [[ -f $3 ]] && echo "$2  $3" | sha256sum -c --quiet 2>/dev/null; then return; fi
    curl -fsSL -o "$3.part" "$1"
    echo "$2  $3.part" | sha256sum -c --quiet
    mv "$3.part" "$3"
}

mkdir -p "$cache/downloads" "$cache/src"
fetch https://github.com/microsoft/Selawik/releases/download/1.01/Selawik_Release.zip \
    3f62c51e05e3b5a1e6241cf92a371f0be2ea1183aa87b30718bbd40832a8d423 "$cache/downloads/selawik.zip"
fetch https://github.com/microsoft/cascadia-code/releases/download/v2407.24/CascadiaCode-2407.24.zip \
    e67a68ee3386db63f48b9054bd196ea752bc6a4ebb4df35adce6733da50c8474 "$cache/downloads/cascadia.zip"
[[ -d $cache/src/selawik ]] || unzip -qo "$cache/downloads/selawik.zip" -d "$cache/src/selawik"
[[ -d $cache/src/cascadia ]] || unzip -qo "$cache/downloads/cascadia.zip" -d "$cache/src/cascadia"
ln -sfn /usr/share/fonts/truetype/liberation "$cache/src/liberation"
ln -sfn /usr/share/fonts/truetype/dejavu "$cache/src/dejavu"

# Stand-in fonts renamed to the Windows families WPF asks for
[[ -x $cache/venv/bin/python ]] || python3 -m venv "$cache/venv"
"$cache/venv/bin/pip" install -q --disable-pip-version-check -r "$here/requirements.txt"
{
    echo 'REGEDIT4'
    echo
    echo '[HKEY_LOCAL_MACHINE\Software\Microsoft\Windows NT\CurrentVersion\Fonts]'
    "$cache/venv/bin/python" "$here/prep_fonts.py" "$cache/src" "$cache/fonts"
} > "$cache/fonts.reg"

# Wine prefix of its own, with the fonts installed and registered
# winedbg disabled: a crash then exits instead of waiting on a debugger nobody sees
export WINEPREFIX=$cache/prefix WINEDEBUG=-all WINEDLLOVERRIDES="winedbg.exe=d"
if [[ ! -f $WINEPREFIX/system.reg ]]; then
    # Skip the Mono and Gecko installers; the app brings its own .NET runtime.
    # Only here: disabling mscoree while the app runs breaks its assembly loading
    WINEDLLOVERRIDES="mscoree,mshtml=,winedbg.exe=d" xvfb-run -a wineboot -i
    wineserver -w
fi
cp "$cache"/fonts/*.ttf "$WINEPREFIX/drive_c/windows/Fonts/"
xvfb-run -a wine regedit "Z:$cache/fonts.reg"
wineserver -w

dotnet publish "$here/windows/Shots.csproj" -c Release -o "$cache/build" \
    -p:EnableWindowsTargeting=true -nologo -v quiet

mkdir -p "$out"
rm -f "$out"/*.png "$out/shots.log"
status=0
timeout 600 xvfb-run -a -s "-screen 0 1920x1200x24" \
    wine "$cache/build/Shots.exe" "Z:$out" "Z:$here/windows/proposals" || status=$?
wineserver -w
if [[ $status -ne 0 ]]; then
    echo "Windows screenshot run failed ($status); see $out/shots.log" >&2
    exit "$status"
fi

# The Linux app, natively. Tk comes from the distro (python3-tk), not pip.
if "$cache/venv/bin/python" -c 'import tkinter' 2>/dev/null; then
    timeout 300 xvfb-run -a -s "-screen 0 1920x1200x24" \
        "$cache/venv/bin/python" "$here/linux/shots.py" "$repo/proxmox-spice-manager.py" "$out"
else
    echo "skipping Linux screenshots: install python3-tk (Debian) or python3-tkinter (Fedora)" >&2
fi
echo "screenshots in $out"
