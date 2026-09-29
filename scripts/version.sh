#!/usr/bin/env bash
# Print the app version, after checking that every place declaring it agrees.
# Windows and Linux share one version number (see CHANGELOG.md).
set -euo pipefail
cd "$(dirname "$0")/.."

declare -A found=(
  [windows/ProxmoxSpiceManager.csproj]="$(sed -n 's:.*<Version>\(.*\)</Version>.*:\1:p' windows/ProxmoxSpiceManager.csproj)"
  [proxmox-spice-manager.py APP_VERSION]="$(sed -n 's/^APP_VERSION = "\(.*\)"$/\1/p' proxmox-spice-manager.py)"
  [proxmox-spice-manager.py docstring]="$(sed -n 's/^VERSION \(.*\)$/\1/p' proxmox-spice-manager.py)"
)

expected="${found[windows/ProxmoxSpiceManager.csproj]}"
status=0
for where in "${!found[@]}"; do
  v="${found[$where]}"
  if [ -z "$v" ]; then
    echo "version.sh: no version found in $where" >&2
    status=1
  elif [ "$v" != "$expected" ]; then
    echo "version.sh: $where declares $v, csproj declares $expected" >&2
    status=1
  fi
done

if ! printf '%s\n' "$expected" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$'; then
  echo "version.sh: '$expected' is not MAJOR.MINOR.PATCH" >&2
  status=1
fi

[ "$status" -eq 0 ] && echo "$expected"
exit "$status"
