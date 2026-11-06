#!/usr/bin/env bash
# Prepare dependencies only; scientific execution stays in the existing runner.
set -euo pipefail

usage() {
  cat <<'HELP'
Usage: bash scripts/bootstrap-codex-cloud.sh [--with-ai4science] [--with-semantic-retrieval]

Install the Python, reading, plotting, statistics, OCR and document-export tools
for this checkout. Optional flags install the declared heavier SDK/runtime groups;
they do not download model weights, call models or start research/experiments.
HELP
}

extras="reader,figures,research-quality,writing-tools,reference-tools"
with_ai4science=false
with_semantic=false
for argument in "$@"; do
  case "$argument" in
    --with-ai4science) with_ai4science=true; extras+=",ai4science" ;;
    --with-semantic-retrieval) with_semantic=true; extras+=",figure-retrieval" ;;
    --help|-h) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "This setup targets Codex Cloud Linux; use the existing Windows/WSL instructions locally." >&2
  exit 2
fi
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$repo_root"
runtime_root="$repo_root/.runtime"
mkdir -p "$runtime_root"/{pip-cache,huggingface,xdg-cache,xdg-data,tmp,matplotlib,paperqa,tooluniverse,torch}

python_command="${DR_OS_CLOUD_PYTHON:-python3}"
"$python_command" -c 'import sys; sys.exit("Python 3.10 or newer is required; Python 3.12 is recommended." if sys.version_info < (3, 10) else 0)'
if [[ "$with_ai4science" == true ]]; then
  "$python_command" -c 'import sys; sys.exit("The optional PaperQA2 SDK requires Python 3.11 or newer." if sys.version_info < (3, 11) else 0)'
fi
if [[ ! -d .venv ]]; then
  "$python_command" -m venv .venv
elif [[ ! -x .venv/bin/python ]]; then
  echo "The existing .venv is not a Linux Python environment. Preserve or move it before setup." >&2
  exit 2
fi
.venv/bin/python -c 'import sys; sys.exit("The existing .venv needs Python 3.10 or newer." if sys.version_info < (3, 10) else 0)'
if [[ "$with_ai4science" == true ]]; then
  .venv/bin/python -c 'import sys; sys.exit("Recreate the existing .venv with Python 3.11+ for PaperQA2." if sys.version_info < (3, 11) else 0)'
fi
.venv/bin/python -m pip --version >/dev/null

# This file contains paths and non-secret runtime settings only. It is ignored
# by Git and must be sourced by each task shell, not copied into a secret field.
env_file="$runtime_root/codex-cloud-env.sh"
cat > "$env_file" <<'ENV'
dr_os_cloud_runtime="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
export PIP_CACHE_DIR="$dr_os_cloud_runtime/pip-cache"
export HF_HOME="$dr_os_cloud_runtime/huggingface"
export XDG_CACHE_HOME="$dr_os_cloud_runtime/xdg-cache"
export XDG_DATA_HOME="$dr_os_cloud_runtime/xdg-data"
export TMPDIR="$dr_os_cloud_runtime/tmp"
export MPLCONFIGDIR="$dr_os_cloud_runtime/matplotlib"
export PAPERQA_HOME="$dr_os_cloud_runtime/paperqa"
export TOOLUNIVERSE_HOME="$dr_os_cloud_runtime/tooluniverse"
export TORCH_HOME="$dr_os_cloud_runtime/torch"
export MPLBACKEND=Agg
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
source "$dr_os_cloud_runtime/../.venv/bin/activate"
unset dr_os_cloud_runtime
ENV
# shellcheck source=/dev/null
source "$env_file"

# Install only missing packages, without upgrading the host or enabling Docker.
# Checking packages also detects an incomplete LibreOffice/TeX installation.
system_packages=(
  git poppler-utils tesseract-ocr tesseract-ocr-eng tesseract-ocr-chi-sim
  pandoc latexmk texlive-latex-base texlive-latex-extra texlive-fonts-recommended
  fonts-dejavu-core fonts-liberation libreoffice-writer libreoffice-impress
)
missing_packages=()
for package in "${system_packages[@]}"; do
  if ! command -v dpkg-query >/dev/null ||
     [[ "$(dpkg-query -W -f='${Status}' "$package" 2>/dev/null || true)" != "install ok installed" ]]; then
    missing_packages+=("$package")
  fi
done
if (( ${#missing_packages[@]} )); then
  if ! command -v apt-get >/dev/null; then
    echo "Install the missing document tools on a Debian/Ubuntu image: ${missing_packages[*]}" >&2
    exit 2
  fi
  privilege=()
  if (( EUID != 0 )); then
    if ! command -v sudo >/dev/null; then
      echo "Installing the missing document tools requires root or passwordless sudo." >&2
      exit 2
    fi
    privilege=(sudo -n)
  fi
  "${privilege[@]}" apt-get update -qq
  "${privilege[@]}" env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${missing_packages[@]}"
fi

python -m pip install --disable-pip-version-check -e ".[${extras}]" \
  'reportlab>=4,<5' 'Pillow>=10,<13' PyYAML seaborn jsonschema
python -m pip check
python - <<'PY'
import importlib
import sys

modules = (
    "matplotlib", "numpy", "pandas", "fitz", "pypdf", "pptx", "docx",
    "statsmodels", "proselint", "reportlab", "PIL", "yaml", "seaborn", "jsonschema",
)
for name in modules:
    importlib.import_module(name)
print(f"Python {sys.version.split()[0]}: core reading, figure, statistics and export imports passed.")
PY
for tool in git pdftotext pdftoppm tesseract pandoc latexmk pdflatex soffice; do
  command -v "$tool" >/dev/null
done
ref-verify --help >/dev/null
if [[ "$with_ai4science" == true ]]; then
  python -c 'import importlib.metadata as m; print("paper-qa", m.version("paper-qa")); print("tooluniverse", m.version("tooluniverse"))'
  pqa --help >/dev/null
fi
if [[ "$with_semantic" == true ]]; then
  python -c 'import onnxruntime, tokenizers; print("semantic runtimes", onnxruntime.__version__, tokenizers.__version__)'
fi
python scripts/check_env.py --mode api > "$runtime_root/codex-cloud-environment.json"
python -m compileall -q scripts
python scripts/validate_repo.py
printf '%s\n' "Cloud dependency checks passed. No model calls or research/experiment runs were started." \
  "In each new task shell: source .runtime/codex-cloud-env.sh"
