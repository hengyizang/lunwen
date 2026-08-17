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

python3 scripts/check_env.py --soft
python3 -m unittest discover -s tests -v
python3 scripts/validate_repo.py

if [[ "$install_kdense" == true ]]; then
  bash scripts/install-kdense-core.sh --install
  python3 scripts/validate_repo.py
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "Claude Code is not on PATH. Install/authenticate it before using the plugin."
fi

if ! command -v codex >/dev/null 2>&1; then
  echo "Codex is not on PATH. Install/authenticate it before using codex-review MCP."
fi

echo "Bootstrap checks complete."
echo "Start with: claude --plugin-dir ."
echo "Then run: /doctoral-research-os:start my-phd"
