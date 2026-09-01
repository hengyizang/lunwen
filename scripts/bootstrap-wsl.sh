#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

install_kdense=false
if [[ "${1:-}" == "--with-kdense" ]]; then
  install_kdense=true
  shift
fi
if [[ "$#" -ne 0 ]]; then
  echo "Usage: bash scripts/bootstrap-wsl.sh [--with-kdense]" >&2
  exit 2
fi

python3 scripts/check_env.py --mode api --soft
python3 -m unittest discover -s tests -v
python3 scripts/validate_repo.py

if [[ "$install_kdense" == true ]]; then
  bash scripts/install-kdense-core.sh --install
  python3 scripts/validate_repo.py
fi

echo "Bootstrap checks complete."
echo "API-first start: follow docs/UUAPI-CC-SWITCH.md"
echo "Optional CLI-mode check: python3 scripts/check_env.py --mode cli"
