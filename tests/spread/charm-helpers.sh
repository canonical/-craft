#!/usr/bin/env bash
# Shared helpers, sourced from each task.yaml.
#
# Each task is expected to ship a sibling `dashcraft.yaml` describing the
# charm (name, upstream, workload). The helpers read everything from there
# — task.yaml does not need to set any environment variables.

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

# Pack the charm described by this task's dashcraft.yaml and deploy it.
pack_and_deploy() {
  local config="$(task_dir)/dashcraft.yaml"
  [[ -f "$config" ]] || { echo "FAIL: $config not found" >&2; return 1; }

  local name workload
  name="$(yaml_get "$config" name)"
  workload="$(yaml_get "$config" parts.charm.workload)"
  [[ -n "$name" ]] || { echo "FAIL: name missing in $config" >&2; return 1; }
  [[ -n "$workload" ]] || {
    echo "FAIL: parts.charm.workload missing in $config" >&2
    return 1
  }

  local work_dir="/root/work-${name}"
  rm -rf "$work_dir"
  mkdir -p "$work_dir"
  cp "$config" "$work_dir/dashcraft.yaml"

  dashcraft pack --project-dir "$work_dir"

  local charm_file
  charm_file="$(ls -1 "$work_dir"/*.charm 2>/dev/null | head -n1)"
  [[ -n "$charm_file" ]] || {
    echo "FAIL: no .charm produced in $work_dir" >&2
    return 1
  }
  echo "Packed: $charm_file"

  juju switch "$JUJU_MODEL"
  juju deploy "$charm_file" "$name" --resource "${name}-image=${workload}"
  juju wait-for application "$name" --query='status=="active"' --timeout=10m
}

# Remove the deployed app and the workdir.
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
