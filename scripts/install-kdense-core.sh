#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--install" || "$#" -ne 1 ]]; then
  echo "Usage: bash scripts/install-kdense-core.sh --install" >&2
  echo "This opt-in command downloads a pinned third-party MIT-licensed skill subset." >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
lock_path="$repo_root/integrations/upstreams.lock.json"
source_id="kdense-scientific-agent-skills"

mapfile -t lock_values < <(
  python3 - "$lock_path" "$source_id" <<'PY'
import json
import sys

lock_path, source_id = sys.argv[1:]
value = json.load(open(lock_path, encoding="utf-8"))
source = next(item for item in value["sources"] if item["id"] == source_id)
print(source["repository"])
print(source["commit"])
for skill in source["selected_skills"]:
    print(skill)
PY
)

upstream_url="${lock_values[0]}"
upstream_commit="${lock_values[1]}"
selected_skills=("${lock_values[@]:2}")
vendor_root="$repo_root/.vendor"
source_dir="$vendor_root/kdense-scientific-agent-skills-$upstream_commit"

mkdir -p "$vendor_root"
if [[ ! -d "$source_dir/.git" ]]; then
  if [[ -e "$source_dir" ]]; then
    echo "Refusing to reuse non-Git path: $source_dir" >&2
    exit 2
  fi
  git init --quiet "$source_dir"
  git -C "$source_dir" remote add origin "$upstream_url"
  git -C "$source_dir" fetch --quiet --depth 1 origin "$upstream_commit"
  git -C "$source_dir" -c advice.detachedHead=false checkout --quiet --detach FETCH_HEAD
fi

resolved_commit="$(git -C "$source_dir" rev-parse HEAD)"
if [[ "$resolved_commit" != "$upstream_commit" ]]; then
  echo "Pinned commit mismatch: expected $upstream_commit, found $resolved_commit" >&2
  exit 2
fi
if ! grep -q "MIT License" "$source_dir/LICENSE.md"; then
  echo "Expected MIT license marker was not found; refusing installation." >&2
  exit 2
fi

for skill_name in "${selected_skills[@]}"; do
  source_skill="$source_dir/skills/$skill_name"
  if [[ ! -f "$source_skill/SKILL.md" ]]; then
    echo "Pinned source is missing $skill_name/SKILL.md" >&2
    exit 2
  fi
  for host_root in "$repo_root/skills" "$repo_root/.agents/skills"; do
    destination="$host_root/$skill_name"
    if [[ -e "$destination" ]]; then
      if ! diff -qr "$source_skill" "$destination" >/dev/null; then
        echo "Existing destination differs; refusing overwrite: $destination" >&2
        exit 2
      fi
    else
      cp -a "$source_skill" "$destination"
    fi
  done
done

echo "Installed ${#selected_skills[@]} pinned K-Dense skills for Claude Code and Codex."
echo "Restart both hosts, inspect third-party scripts before first use, then run repository validation."
