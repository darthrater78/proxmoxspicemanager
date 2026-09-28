#!/usr/bin/env bash
# Checks CI runs on every push. Run locally before committing:
#   pip install -r requirements-dev.txt && bash scripts/check.sh
set -euo pipefail
cd "$(dirname "$0")/.."

version="$(bash scripts/version.sh)"
echo "Version: $version (all declarations agree)"

if ! grep -Eq "^## \[${version//./\\.}\] - [0-9]{4}-[0-9]{2}-[0-9]{2}$" CHANGELOG.md; then
  echo "check.sh: CHANGELOG.md has no '## [$version] - YYYY-MM-DD' entry" >&2
  exit 1
fi
echo "Changelog: entry for $version present"

python3 -c 'import ast, sys; ast.parse(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1])' \
  proxmox-spice-manager.py
echo "Python: proxmox-spice-manager.py parses"

for tool in ruff shellcheck; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "check.sh: $tool not found. Install it with: pip install -r requirements-dev.txt" >&2
    exit 1
  fi
done
# Correctness rules only (syntax errors, undefined names, unused code).
ruff check --isolated --select E9,F proxmox-spice-manager.py

shellcheck scripts/*.sh tools/screenshots/run.sh
echo "Shell: scripts pass shellcheck"
