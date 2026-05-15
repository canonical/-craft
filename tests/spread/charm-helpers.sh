#!/usr/bin/env bash
# Shared helpers, sourced from each task.yaml.
#
# Each task ships a sibling `dashcraft.yaml` describing the charm
# (name, upstream, workload). The helpers read everything from there —
# task.yaml does not need to set environment variables.

set -euo pipefail

JUJU_MODEL="concierge-microk8s:admin/testing"

# Print a dotted key from a YAML file.
# Usage: yaml_get <file> <dotted.key>
yaml_get() {
  python3 - "$1" "$2" <<'PY'
import sys
import yaml

data = yaml.safe_load(open(sys.argv[1])) or {}
for key in sys.argv[2].split('.'):
    if not isinstance(data, dict):
        data = ''
        break
    data = data.get(key, '')
print(data or '')
PY
}

# Resolve the directory of the currently-running spread task.
task_dir() {
  # SPREAD_TASK looks like "tests/spread/pack-booklore" (possibly with a
  # ":variant" suffix). Strip the variant and prepend SPREAD_PATH.
  echo "$SPREAD_PATH/${SPREAD_TASK%%:*}"
}

# Prepare a fresh work directory for this task, copy the sibling
# dashcraft.yaml in, and echo the path. Cleanup is the caller's job.
task_workdir() {
  local config="$(task_dir)/dashcraft.yaml"
  [[ -f "$config" ]] || { echo "FAIL: $config not found" >&2; return 1; }

  local name
  name="$(yaml_get "$config" name)"
  [[ -n "$name" ]] || { echo "FAIL: name missing in $config" >&2; return 1; }

  local work_dir="/root/work-${name}"
  rm -rf "$work_dir"
  mkdir -p "$work_dir"
  cp "$config" "$work_dir/dashcraft.yaml"
  echo "$work_dir"
}

# Pack the charm in `$1` and assert a .charm file landed beside the
# config. Echoes the .charm path on stdout. Exits non-zero on failure.
pack_charm() {
  local work_dir="$1"
  dashcraft pack --project-dir "$work_dir"

  local charm_file
  charm_file="$(ls -1 "$work_dir"/*.charm 2>/dev/null | head -n1)"
  [[ -n "$charm_file" ]] || {
    echo "FAIL: no .charm produced in $work_dir" >&2
    return 1
  }
  echo "$charm_file"
}

# Unzip a packed charm into `$2` and assert it contains real content:
#   - metadata.yaml and src/charm.py exist
#   - metadata.yaml has the expected `name` from the supplied
#     dashcraft.yaml (NOT a "TODO" placeholder)
#   - src/charm.py is not the skeleton-only `/bin/foo` placeholder
verify_charm() {
  local charm_file="$1"
  local verify_dir="$2"
  local expected_name="$3"

  mkdir -p "$verify_dir"
  unzip -q "$charm_file" -d "$verify_dir"

  local missing=()
  for f in metadata.yaml src/charm.py; do
    [[ -f "$verify_dir/$f" ]] || missing+=("$f")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    echo "FAIL: missing files in charm: ${missing[*]}" >&2
    return 1
  fi

  local got_name
  got_name="$(yaml_get "$verify_dir/metadata.yaml" name)"
  if [[ "$got_name" != "$expected_name" ]]; then
    echo "FAIL: metadata.yaml name='$got_name', expected '$expected_name'" >&2
    return 1
  fi

  # No raw placeholder commands or TODO markers should survive into the
  # packed charm — these would indicate the skeleton was never filled.
  if grep -q '/bin/foo' "$verify_dir/src/charm.py"; then
    echo "FAIL: src/charm.py still has skeleton placeholder '/bin/foo'" >&2
    return 1
  fi
  if grep -Eq '\bTODO\b' "$verify_dir/src/charm.py"; then
    echo "FAIL: src/charm.py still contains TODO markers" >&2
    return 1
  fi

  echo "Charm verification passed (name=$got_name)"
}

# Compose pack + verify into one helper used by every pack-* task.
# Reads `name` from the sibling dashcraft.yaml; cleans up on exit.
pack_and_verify() {
  local work_dir charm_file expected_name
  work_dir="$(task_workdir)"
  expected_name="$(yaml_get "$work_dir/dashcraft.yaml" name)"

  charm_file="$(pack_charm "$work_dir")"
  echo "Packed: $charm_file"

  verify_charm "$charm_file" "$work_dir/verify" "$expected_name"
  rm -rf "$work_dir"
}

# Pack + deploy a charm via concierge-bootstrapped microk8s, then wait
# for it to reach `active`. Reads workload-image from dashcraft.yaml.
pack_and_deploy() {
  local config work_dir charm_file name workload
  config="$(task_dir)/dashcraft.yaml"
  [[ -f "$config" ]] || { echo "FAIL: $config not found" >&2; return 1; }

  name="$(yaml_get "$config" name)"
  workload="$(yaml_get "$config" parts.charm.workload)"
  [[ -n "$name" ]] || { echo "FAIL: name missing in $config" >&2; return 1; }
  [[ -n "$workload" ]] || {
    echo "FAIL: parts.charm.workload missing in $config" >&2
    return 1
  }

  work_dir="$(task_workdir)"
  charm_file="$(pack_charm "$work_dir")"
  echo "Packed: $charm_file"

  juju switch "$JUJU_MODEL"
  juju deploy "$charm_file" "$name" --resource "workload-image=${workload}"
  juju wait-for application "$name" --query='status=="active"' --timeout=10m
}

# Remove the deployed app and the workdir for the current task.
cleanup() {
  local config="$(task_dir)/dashcraft.yaml"
  if [[ -f "$config" ]]; then
    local name
    name="$(yaml_get "$config" name)"
    if [[ -n "$name" ]]; then
      juju remove-application "$name" --force --no-prompt --no-wait 2>/dev/null || true
      rm -rf "/root/work-${name}"
    fi
  fi
}
