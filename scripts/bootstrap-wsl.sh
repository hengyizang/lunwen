#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

install_kdense=false
install_writing_tools=false
install_research_quality_tools=false
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --with-kdense)
      install_kdense=true
      ;;
    --with-writing-tools)
      install_writing_tools=true
      ;;
    --with-research-quality-tools)
      install_research_quality_tools=true
      ;;
    *)
      echo "Usage: bash scripts/bootstrap-wsl.sh [--with-kdense] [--with-writing-tools] [--with-research-quality-tools]" >&2
      exit 2
      ;;
  esac
  shift
done

if [[ "$install_writing_tools" == true ]]; then
  if [[ ! -x ".venv/bin/python" ]]; then
    python3 -m venv .venv
  fi
  if ! .venv/bin/python -c "import importlib.metadata as m; raise SystemExit(m.version('proselint') != '0.16.0')" >/dev/null 2>&1; then
    .venv/bin/python -m pip install 'proselint==0.16.0'
  fi
  .venv/bin/proselint version
fi

if [[ "$install_research_quality_tools" == true ]]; then
  if [[ ! -x ".venv/bin/python" ]]; then
    python3 -m venv .venv
  fi
  if ! .venv/bin/python -c "import importlib.metadata as m; raise SystemExit(m.version('statsmodels') != '0.15.0')" >/dev/null 2>&1; then
    .venv/bin/python -m pip install 'statsmodels==0.15.0'
  fi
  .venv/bin/python -c "import statsmodels; print('statsmodels', statsmodels.__version__)"
fi

runtime_python="python3"
if [[ -x ".venv/bin/python" ]]; then
  runtime_python=".venv/bin/python"
fi

"$runtime_python" scripts/check_env.py --mode api --soft
"$runtime_python" -m unittest discover -s tests -v
"$runtime_python" scripts/validate_repo.py

if [[ "$install_kdense" == true ]]; then
  bash scripts/install-kdense-core.sh --install
  "$runtime_python" scripts/validate_repo.py
fi

echo "Bootstrap checks complete."
echo "Visual dashboard: bash scripts/start-dashboard.sh"
echo "API-first CLI: follow docs/UUAPI-CC-SWITCH.md"
echo "Optional local prose checks: bash scripts/bootstrap-wsl.sh --with-writing-tools"
echo "Executable power analysis: bash scripts/bootstrap-wsl.sh --with-research-quality-tools"
echo "Optional CLI-mode check: python3 scripts/check_env.py --mode cli"
