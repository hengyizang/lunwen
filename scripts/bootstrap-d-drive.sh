#!/usr/bin/env bash
set -euo pipefail

repo_root="${DR_OS_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)}"
repo_root="$(cd "$repo_root" && pwd -P)"
required_root="/mnt/d/ad/lunwen"
if [[ "${repo_root,,}" != "${required_root,,}" ]]; then
  printf '%s\n' "Refusing to install outside ${required_root}." "Move or clone the repository to D:\\ad\\lunwen first." >&2
  exit 2
fi
cd "$repo_root"
runtime_root="$repo_root/.runtime"
mkdir -p "$runtime_root"/{pip-cache,huggingface,xdg-cache,xdg-data,tmp,matplotlib,paperqa,tooluniverse,docker-desktop}
export PIP_CACHE_DIR="$runtime_root/pip-cache"
export HF_HOME="$runtime_root/huggingface"
export XDG_CACHE_HOME="$runtime_root/xdg-cache"
export XDG_DATA_HOME="$runtime_root/xdg-data"
export TMPDIR="$runtime_root/tmp"
export MPLCONFIGDIR="$runtime_root/matplotlib"
export PAPERQA_HOME="$runtime_root/paperqa"
export TOOLUNIVERSE_HOME="$runtime_root/tooluniverse"
if [[ ! -x .venv/bin/python ]]; then
  python3 -m venv .venv
elif ! .venv/bin/python -m pip --version >/dev/null 2>&1; then
  printf '%s\n' "Repairing incomplete virtual environment at $repo_root/.venv."
  python3 -m venv --clear .venv
fi
.venv/bin/python -m pip --version >/dev/null
.venv/bin/python -m pip install --disable-pip-version-check --upgrade pip
.venv/bin/python -m pip install --disable-pip-version-check -e ".[figures,reader,reference-tools,writing-tools,research-quality,ai4science]"
env_file="$runtime_root/env.sh"
{
  printf 'export PIP_CACHE_DIR=%q\n' "$PIP_CACHE_DIR"
  printf 'export HF_HOME=%q\n' "$HF_HOME"
  printf 'export XDG_CACHE_HOME=%q\n' "$XDG_CACHE_HOME"
  printf 'export XDG_DATA_HOME=%q\n' "$XDG_DATA_HOME"
  printf 'export TMPDIR=%q\n' "$TMPDIR"
  printf 'export MPLCONFIGDIR=%q\n' "$MPLCONFIGDIR"
  printf 'export PAPERQA_HOME=%q\n' "$PAPERQA_HOME"
  printf 'export TOOLUNIVERSE_HOME=%q\n' "$TOOLUNIVERSE_HOME"
} > "$env_file"
chmod 600 "$env_file"
.venv/bin/python scripts/check_env.py --mode api --install-root "$required_root"
.venv/bin/python -m unittest discover -s tests -q
.venv/bin/python scripts/validate_repo.py
printf '%s\n' "D-drive environment installed under D:\\ad\\lunwen." "Before each session: source /mnt/d/ad/lunwen/.runtime/env.sh"
