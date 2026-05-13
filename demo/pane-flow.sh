#!/usr/bin/env bash
# Per-pane workflow for the dashcraft asciicinema demo.
#
# Usage:
#   pane-flow.sh <name> <openrouter-model> <upstream-git-url> <workload-image> <work-dir> <sentinel-dir>
#
# Effect inside the pane:
#   1. Prints a banner naming the charm + model.
#   2. Types out a -craft.yaml file char-by-char.
#   3. Runs `dashcraft pack` and pipes its output to a log.
#   4. Extracts the `Deploy with:` line from the log and runs it.
#   5. Touches a sentinel file so record.sh knows when this pane is done.

set -uo pipefail

if [ $# -lt 6 ]; then
    echo "usage: $(basename "$0") <name> <model> <upstream> <workload> <work-dir> <sentinel-dir>" >&2
    exit 2
fi

NAME="$1"
MODEL="$2"
UPSTREAM="$3"
WORKLOAD="$4"
WORK_DIR="$5"
SENTINEL_DIR="$6"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TYPEWRITER="$SCRIPT_DIR/typewriter.py"
TYPE_DELAY="${TYPE_DELAY:-0.008}"

mkdir -p "$WORK_DIR"
cd "$WORK_DIR" || exit 1

# Colourful escapes (rendered fine by asciinema-player).
B="\033[1m"; DIM="\033[2m"; C="\033[36m"; G="\033[32m"; Y="\033[33m"; R="\033[0m"

clear
printf "${B}${C}┌─────────────────────────────────────────────────────────────┐${R}\n"
printf "${B}${C}│${R}  dashcraft demo: ${B}%-43s${R}${B}${C}│${R}\n" "$NAME"
printf "${B}${C}│${R}  model:          ${Y}openrouter/%-32s${R}${B}${C}│${R}\n" "$MODEL"
printf "${B}${C}│${R}  upstream:       ${DIM}%-43s${R}${B}${C}│${R}\n" "${UPSTREAM:0:43}"
printf "${B}${C}└─────────────────────────────────────────────────────────────┘${R}\n"
echo
sleep 1.2

printf "${G}\$${R} ${B}cat > -craft.yaml${R}\n"
sleep 0.4

# Use a heredoc-style YAML body. The typewriter writes it to the file *and*
# echoes it to the pane so the viewer sees it appear character-by-character.
YAML_BODY="name: $NAME
summary: $NAME charm
description: A charm for $NAME.
type: charm

parts:
  charm:
    plugin: -craft
    upstream: $UPSTREAM
    workload: $WORKLOAD
    model: openrouter/$MODEL
"

printf '%s' "$YAML_BODY" | python3 "$TYPEWRITER" -d "$TYPE_DELAY" -o -craft.yaml

echo
sleep 0.6
printf "${G}\$${R} ${B}dashcraft pack${R}\n"
sleep 0.3

LOG="$WORK_DIR/pack.log"
# stdbuf -oL keeps pi's streamed output line-buffered through `tee`.
stdbuf -oL -eL dashcraft pack 2>&1 | tee "$LOG"
PACK_RC=${PIPESTATUS[0]}

if [ "$PACK_RC" -ne 0 ]; then
    printf "\n${B}\033[31m✗ dashcraft pack exited %s${R}\n" "$PACK_RC"
    touch "$SENTINEL_DIR/done.$NAME.failed"
    sleep 3600
    exit "$PACK_RC"
fi

# The CLI prints:
#   Deploy with:
#     juju deploy ./<file>.charm --resource ...
# Extract the indented command on the line *after* "Deploy with:".
DEPLOY=$(awk '/^Deploy with:/{getline; sub(/^[[:space:]]+/,""); print; exit}' "$LOG")

if [ -z "$DEPLOY" ]; then
    printf "\n${B}\033[31m✗ Could not find deploy command in pack output.${R}\n"
    touch "$SENTINEL_DIR/done.$NAME.failed"
    sleep 3600
    exit 1
fi

echo
sleep 0.6
printf "${G}\$${R} ${B}%s${R}\n" "$DEPLOY"
sleep 0.4

# The script that called us already activated the right juju model.
eval "$DEPLOY"
DEPLOY_RC=$?

if [ "$DEPLOY_RC" -ne 0 ]; then
    printf "\n${B}\033[31m✗ juju deploy exited %s${R}\n" "$DEPLOY_RC"
    touch "$SENTINEL_DIR/done.$NAME.failed"
else
    printf "\n${B}${G}▶ %s deployed.${R}\n" "$NAME"
    touch "$SENTINEL_DIR/done.$NAME"
fi

# Stay alive so the pane keeps its final output visible until record.sh
# tears the session down.
sleep 3600
