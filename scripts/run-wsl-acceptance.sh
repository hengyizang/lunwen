#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

project=""
corpus=""
tool_request=""
actor=""
question="Which evidence contradicts the proposed mechanism?"
settings="fast"
output="artifacts/acceptance/wsl2-full.json"

usage() {
  printf '%s\n' \
    "Usage: bash scripts/run-wsl-acceptance.sh --project <slug> --corpus <project-relative-dir> \\" \
    "  --tool-request <project-relative-json> --actor <name> [--question <text>] [--settings <name>] [--output <path>]"
}

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --project) project="${2:-}"; shift 2 ;;
    --corpus) corpus="${2:-}"; shift 2 ;;
    --tool-request) tool_request="${2:-}"; shift 2 ;;
    --actor) actor="${2:-}"; shift 2 ;;
    --question) question="${2:-}"; shift 2 ;;
    --settings) settings="${2:-}"; shift 2 ;;
    --output) output="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

if [[ -z "$project" || -z "$corpus" || -z "$tool_request" || -z "$actor" ]]; then
  usage >&2
  exit 2
fi

python_bin=".venv/bin/python"
if [[ ! -x "$python_bin" ]]; then
  printf '%s\n' \
    "Missing repository virtual environment." \
    "Run: bash scripts/bootstrap-wsl.sh --with-ai4science --with-figures" >&2
  exit 2
fi

"$python_bin" -c \
  'from scripts.live_acceptance import environment_report; import sys; report=environment_report(); print(report); raise SystemExit(0 if report["is_wsl2"] else 2)'
"$python_bin" -c \
  'import importlib.metadata as m; assert m.version("paper-qa") == "2026.08.12"; assert m.version("tooluniverse") == "1.5.1"'
"$python_bin" scripts/check_env.py --mode api
docker info >/dev/null

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
printf '%s\n' "Full WSL2 acceptance passed. Report: $output"
