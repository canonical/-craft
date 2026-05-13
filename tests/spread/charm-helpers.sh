#!/usr/bin/env bash
# Shared helpers, sourced from each task.yaml.
#
# Tests set NAME (kebab-case charm name) and WORKLOAD_IMAGE (OCI ref)
# before sourcing this file and calling one of the functions below.

set -euo pipefail

JUJU_MODEL="concierge-microk8s:admin/testing"

# Scaffold a charm with dashcraft into a clean workdir.
scaffold_charm() {
  local name="${NAME:?NAME is required}"
  local image="${WORKLOAD_IMAGE:-}"
  local work_dir="/root/work-${name}"

  rm -rf "$work_dir"
  mkdir -p "$work_dir"
  cd "$work_dir"

  # Currently fails: dashcraft has no CLI yet. This is the intended
  # failure point until the CLI lands.
  if [[ -n "$image" ]]; then
    dashcraft charm-init "$name" --workload "$image"
  else
    dashcraft charm-init "$name"
  fi

  cd "$name"
}

# Run `charmcraft pack` and echo the produced *.charm path.
pack_charm() {
  charmcraft pack
  local charm_file
  charm_file="$(ls -1 ./*.charm 2>/dev/null | head -n1)"
  if [[ -z "$charm_file" ]]; then
    echo "FAIL: charmcraft produced no .charm file" >&2
    return 1
  fi
  echo "Packed: $charm_file"
  echo "$charm_file"
}

# Scaffold + pack + deploy + wait-for-active.
pack_and_deploy() {
  local name="${NAME:?NAME is required}"
  local image="${WORKLOAD_IMAGE:?WORKLOAD_IMAGE is required}"

  scaffold_charm
  local charm_file
  charm_file="$(pack_charm | tail -n1)"

  juju switch "$JUJU_MODEL"
  juju deploy "$charm_file" "$name" --resource "${name}-image=${image}"
  juju wait-for application "$name" --query='status=="active"' --timeout=10m
}

# Remove the deployed app (if any) and the workdir.
cleanup() {
  local name="${NAME:?NAME is required}"
  juju remove-application "$name" --force --no-prompt --no-wait 2>/dev/null || true
  rm -rf "/root/work-${name}"
}
