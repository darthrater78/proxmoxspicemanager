#!/usr/bin/env bash
# Build the Windows single-file exe into dist/. Used by CI, the release
# workflow and local dev. Needs the .NET SDK; also works on Linux.
set -euo pipefail
cd "$(dirname "$0")/.."

extra=()
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*) ;;
  *) extra+=(-p:EnableWindowsTargeting=true) ;;
esac

rm -rf dist
dotnet publish windows/ProxmoxSpiceManager.csproj -c Release -o dist "${extra[@]}"

exe=dist/Proxmox-SPICE-Manager.exe
if [ ! -s "$exe" ]; then
  echo "build.sh: $exe was not produced" >&2
  exit 1
fi
echo "Built $exe ($(du -h "$exe" | cut -f1))"
