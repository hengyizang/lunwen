#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

install_kdense=false
install_writing_tools=false
install_research_quality_tools=false
install_ai4science=false
install_figures=false
install_reference_tools=false
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
    --with-ai4science)
      install_ai4science=true
      ;;
    --with-figures)
      install_figures=true
      ;;
    --with-reference-tools)
      install_reference_tools=true
      ;;
    *)
      echo "Usage: bash scripts/bootstrap-wsl.sh [--with-kdense] [--with-writing-tools] [--with-research-quality-tools] [--with-ai4science] [--with-figures] [--with-reference-tools]" >&2
      exit 2
      ;;
  esac
  shift
done

if [[ "$install_reference_tools" == true ]]; then
  if [[ ! -x ".venv/bin/python" ]]; then
    python3 -m venv .venv
  fi
  if ! .venv/bin/python -c "import importlib.metadata as m; raise SystemExit(m.version('ref-verify') != '1.2.0')" >/dev/null 2>&1; then
    .venv/bin/python -m pip install 'ref-verify==1.2.0'
  fi
  .venv/bin/ref-verify --help >/dev/null
  .venv/bin/python -c "import importlib.metadata as m; print('ref-verify', m.version('ref-verify'))"
fi

if [[ "$install_figures" == true ]]; then
  if [[ ! -x ".venv/bin/python" ]]; then
    python3 -m venv .venv
  fi
  .venv/bin/python -m pip install 'matplotlib>=3.8,<4' 'numpy>=1.26,<3' 'pandas>=2.1,<3'
  .venv/bin/python -c "import matplotlib,numpy,pandas; print('figure stack', matplotlib.__version__, numpy.__version__, pandas.__version__)"
fi

if [[ "$install_writing_tools" == true ]]; then
  if [[ ! -x ".venv/bin/python" ]]; then
    python3 -m venv .venv
  fi
  if ! .venv/bin/python -c "import importlib.metadata as m; raise SystemExit(m.version('proselint') != '0.16.0')" >/dev/null 2>&1; then
    .venv/bin/python -m pip install 'proselint==0.16.0'
  fi
  .venv/bin/proselint version
fi

if [[ "$install_ai4science" == true ]]; then
  if ! python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 11))'; then
    echo "PaperQA2 requires Python 3.11 or newer." >&2
    exit 2
  fi
  if [[ ! -x ".venv/bin/python" ]]; then
    python3 -m venv .venv
  fi
  if ! .venv/bin/python -c "import importlib.metadata as m; raise SystemExit(m.version('paper-qa') != '2026.08.12' or m.version('tooluniverse') != '1.5.1')" >/dev/null 2>&1; then
    .venv/bin/python -m pip install 'paper-qa==2026.08.12' 'tooluniverse==1.5.1'
  fi
  .venv/bin/python -c "import importlib.metadata as m; print('paper-qa', m.version('paper-qa')); print('tooluniverse', m.version('tooluniverse'))"
  .venv/bin/pqa --help >/dev/null
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
echo "PaperQA2 and ToolUniverse adapters: bash scripts/bootstrap-wsl.sh --with-ai4science"
echo "Publication figure renderer: bash scripts/bootstrap-wsl.sh --with-figures"
echo "DOI-bound abstract claim checks: bash scripts/bootstrap-wsl.sh --with-reference-tools"
echo "Optional CLI-mode check: python3 scripts/check_env.py --mode cli"
