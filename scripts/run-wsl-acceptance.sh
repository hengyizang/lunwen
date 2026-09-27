#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

project=""
paper=""
corpus=""
tool_request=""
ref_claims=""
actor=""
question="Which evidence contradicts the proposed mechanism?"
settings="fast"
output="artifacts/acceptance/wsl2-full.json"

usage() {
  printf '%s\n' \
    "Usage: bash scripts/run-wsl-acceptance.sh --project <slug> --paper <Pxx> --corpus <project-relative-dir> \\" \
    "  --tool-request <project-relative-json> --ref-claims <paper-relative-jsonl> --actor <name> [--question <text>] [--settings <name>] [--output <path>]"
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --project) project="${2:-}"; shift 2 ;;
    --paper) paper="${2:-}"; shift 2 ;;
    --corpus) corpus="${2:-}"; shift 2 ;;
    --tool-request) tool_request="${2:-}"; shift 2 ;;
    --ref-claims) ref_claims="${2:-}"; shift 2 ;;
    --actor) actor="${2:-}"; shift 2 ;;
    --question) question="${2:-}"; shift 2 ;;
    --settings) settings="${2:-}"; shift 2 ;;
    --output) output="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

if [[ -z "$project" || -z "$paper" || -z "$corpus" || -z "$tool_request" || -z "$ref_claims" || -z "$actor" ]]; then
  usage >&2
  exit 2
fi

if [[ "${repo_root,,}" != "/mnt/d/ad/lunwen" ]]; then
  printf '%s\n' "Full acceptance must run from /mnt/d/ad/lunwen." >&2
  exit 2
fi
[[ -f .runtime/env.sh ]] && source .runtime/env.sh

python_bin=".venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  printf '%s\n' \
    "Missing repository virtual environment." \
    "Run: bash scripts/bootstrap-d-drive.sh" >&2
  exit 2
fi

"$python_bin" -c \
  'from scripts.live_acceptance import environment_report; import sys; report=environment_report(); print(report); raise SystemExit(0 if report["is_wsl2"] else 2)'
"$python_bin" -c \
  'import importlib.metadata as m; from packaging.version import Version; assert Version(m.version("paper-qa")) == Version("2026.08.12"); assert Version(m.version("tooluniverse")) == Version("1.5.1"); assert Version(m.version("ref-verify")) == Version("1.2.0")'
"$python_bin" scripts/check_env.py --mode api --install-root /mnt/d/ad/lunwen
docker info >/dev/null
"$python_bin" - <<'PY'
import json
from pathlib import Path
p=Path('.runtime/docker-location.json')
if not p.is_file(): raise SystemExit('Missing Docker D-drive receipt; rerun install-d-drive.ps1')
v=json.loads(p.read_text(encoding='utf-8-sig'));x=str(v.get('configured_path','')).lower().rstrip('\\');root=r'd:\ad\lunwen\.runtime\docker-desktop'
if v.get('verified') is not True or not (x==root or x.startswith(root+'\\')): raise SystemExit('Docker location receipt does not verify D-drive storage')
PY

mkdir -p "$(dirname "$output")"
"$python_bin" scripts/live_acceptance.py wsl --output "$output"

printf '%s\n' "PaperQA2 can make a billable model call; the configured provider controls its charge."
"$python_bin" scripts/ai4science_evidence.py paperqa \
  --project "$project" \
  --corpus "$corpus" \
  --settings "$settings" \
  --question "$question" \
  --actor "$actor" \
  --purpose "Real WSL2 acceptance over a human-authorized local corpus."

"$python_bin" scripts/ai4science_evidence.py tooluniverse \
  --project "$project" \
  --request "$tool_request" \
  --actor "$actor" \
  --purpose "Real WSL2 acceptance of one explicitly selected public-data tool."

"$python_bin" scripts/ai4science_evidence.py validate --project "$project"
"$python_bin" scripts/ref_verify_adapter.py --project "$project" --paper "$paper" --claims "$ref_claims"
printf '%s\n' "Full WSL2 acceptance passed. Report: $output"
