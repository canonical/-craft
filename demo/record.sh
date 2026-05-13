#!/usr/bin/env bash
# Record an asciinema demo of dashcraft.
#
# Lays out a tmux session with 6 panes:
#   ┌──────────────────┬──────────────────┐
#   │  upvote-rss      │  suite-docs      │   (claude-sonnet-4.6)  (gpt-5)
#   ├──────────────────┼──────────────────┤
#   │  booklore        │  ironcalc        │   (gemini-2.5-pro)     (grok-4)
#   ├──────────────────┼──────────────────┤
#   │  juju status     │  juju debug-log  │
#   └──────────────────┴──────────────────┘
#
# Each of the top four panes types out its own `-craft.yaml`, then runs
# `dashcraft pack` followed by the printed `juju deploy ... --resource ...`
# command.  The bottom two panes give live infrastructure context.
#
# Prerequisites:
#   - tmux, python3
#   - asciinema (or uvx asciinema)
#   - juju with a bootstrapped controller
#   - dashcraft, pi, quickpack on $PATH
#   - $OPENROUTER_API_KEY set
#
# Usage:
#   demo/record.sh [--model NAME] [--output FILE] [--clean] [--cols N] [--rows N]
#
# Re-running:
#   The script is idempotent — it kills any prior demo tmux session and
#   recreates the juju model when --clean is passed.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Four demos, each on a different OpenRouter-routed provider.
#   name | openrouter-model | upstream git url | oci workload image
DEMOS=(
    "upvote-rss|anthropic/claude-sonnet-4.6|https://github.com/johnwarne/upvote-rss.git|ghcr.io/johnwarne/upvote-rss:latest"
    "suite-docs|openai/gpt-5|https://github.com/suitenumerique/docs.git|ghcr.io/suitenumerique/docs-backend:latest"
    "booklore|google/gemini-2.5-pro|https://github.com/booklore-app/booklore.git|ghcr.io/booklore-app/booklore:latest"
    "ironcalc|x-ai/grok-4|https://github.com/ironcalc/IronCalc.git|ghcr.io/ironcalc/ironcalc:latest"
)

SESSION="${DASHCRAFT_DEMO_SESSION:-dashcraft-demo}"
JUJU_MODEL="${JUJU_MODEL:-dashcraft-demo}"
COLS="${COLS:-220}"
ROWS="${ROWS:-64}"
OUTPUT="${OUTPUT:-$SCRIPT_DIR/dashcraft-demo.cast}"
CLEAN=0
IDLE_LIMIT="${IDLE_LIMIT:-2}"

while [ $# -gt 0 ]; do
    case "$1" in
        --model) JUJU_MODEL="$2"; shift 2 ;;
        --output) OUTPUT="$2"; shift 2 ;;
        --cols) COLS="$2"; shift 2 ;;
        --rows) ROWS="$2"; shift 2 ;;
        --idle-limit) IDLE_LIMIT="$2"; shift 2 ;;
        --clean) CLEAN=1; shift ;;
        -h|--help)
            sed -n '2,33p' "$0"
            exit 0 ;;
        *) echo "unknown flag: $1" >&2; exit 2 ;;
    esac
done

# Pick the asciinema invocation: prefer the system one, fall back to uvx.
if command -v asciinema >/dev/null 2>&1; then
    ASCIINEMA=(asciinema)
else
    ASCIINEMA=(uvx asciinema)
fi

# ---------------------------------------------------------------------------
# Prereq checks
# ---------------------------------------------------------------------------

need() {
    local prog="$1" hint="${2:-}"
    if ! command -v "$prog" >/dev/null 2>&1; then
        echo "✗ Missing required tool: $prog${hint:+  ($hint)}" >&2
        exit 1
    fi
}

need tmux
need python3
need juju
need dashcraft "is your venv activated?"
need pi "npm install -g @earendil-works/pi-coding-agent"
need quickpack "uv tool install juju-cantrip"

if [ -z "${OPENROUTER_API_KEY:-}" ]; then
    echo "✗ OPENROUTER_API_KEY must be set in the environment." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Juju model
# ---------------------------------------------------------------------------

ensure_juju_model() {
    if [ "$CLEAN" -eq 1 ] && juju models --format=json 2>/dev/null \
        | python3 -c "import json,sys; m=json.load(sys.stdin); print(any(x['short-name']=='$JUJU_MODEL' for x in m.get('models', [])))" \
        | grep -q True; then
        echo "Cleaning juju model $JUJU_MODEL..."
        juju destroy-model -y --destroy-storage --force --no-wait "$JUJU_MODEL" 2>/dev/null || true
        # destroy-model is async; wait briefly for it to disappear.
        for _ in $(seq 1 30); do
            if ! juju models --format=json 2>/dev/null \
                | python3 -c "import json,sys; m=json.load(sys.stdin); sys.exit(0 if any(x['short-name']=='$JUJU_MODEL' for x in m.get('models', [])) else 1)"; then
                break
            fi
            sleep 2
        done
    fi

    if ! juju models --format=json 2>/dev/null \
        | python3 -c "import json,sys; m=json.load(sys.stdin); sys.exit(0 if any(x['short-name']=='$JUJU_MODEL' for x in m.get('models', [])) else 1)"; then
        echo "Creating juju model $JUJU_MODEL..."
        juju add-model "$JUJU_MODEL"
    else
        echo "Using existing juju model $JUJU_MODEL."
        juju switch "$JUJU_MODEL"
    fi
}

ensure_juju_model

# ---------------------------------------------------------------------------
# Work area
# ---------------------------------------------------------------------------

DEMO_RUN_DIR="$(mktemp -d -t dashcraft-demo.XXXXXX)"
SENTINEL_DIR="$DEMO_RUN_DIR/sentinels"
mkdir -p "$SENTINEL_DIR"
echo "Work dir: $DEMO_RUN_DIR"

cleanup() {
    tmux kill-session -t "$SESSION" 2>/dev/null || true
    if [ -n "${DRIVER_PID:-}" ]; then
        kill "$DRIVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Build tmux session
# ---------------------------------------------------------------------------

tmux kill-session -t "$SESSION" 2>/dev/null || true

# A neutral tmux config: no status bar, ANSI-friendly, big history.
TMUX_CONF="$DEMO_RUN_DIR/tmux.conf"
cat > "$TMUX_CONF" <<EOF
set -g status off
set -g default-terminal "tmux-256color"
set -g history-limit 50000
set -g pane-border-status top
set -g pane-border-format "  #[bold]#{pane_title}  "
set -g pane-border-style "fg=colour240"
set -g pane-active-border-style "fg=colour39"
set -g remain-on-exit on
EOF

tmux -f "$TMUX_CONF" new-session -d -s "$SESSION" -x "$COLS" -y "$ROWS"

# Split the window into the six panes described in the header diagram.
TOP_LEFT=$(tmux list-panes -t "$SESSION" -F '#{pane_id}' | head -1)

# 1. Carve off the bottom 25% for the monitoring row.
MON_LEFT=$(tmux split-window -P -F '#{pane_id}' -v -l '25%' -t "$TOP_LEFT")

# 2. Split the top region into 2 columns, then each column into 2 rows.
TOP_RIGHT=$(tmux split-window -P -F '#{pane_id}' -h -p 50 -t "$TOP_LEFT")
MID_LEFT=$(tmux split-window -P -F '#{pane_id}' -v -p 50 -t "$TOP_LEFT")
MID_RIGHT=$(tmux split-window -P -F '#{pane_id}' -v -p 50 -t "$TOP_RIGHT")

# 3. Split the monitor row into status (left) and debug-log (right).
MON_RIGHT=$(tmux split-window -P -F '#{pane_id}' -h -p 50 -t "$MON_LEFT")

# Pane assignment matches the DEMOS order above.
PANES=("$TOP_LEFT" "$TOP_RIGHT" "$MID_LEFT" "$MID_RIGHT")
STATUS_PANE="$MON_LEFT"
LOG_PANE="$MON_RIGHT"

# Label each pane visibly.
for i in "${!DEMOS[@]}"; do
    IFS='|' read -r name model _ _ <<< "${DEMOS[$i]}"
    tmux select-pane -t "${PANES[$i]}" -T " ${name}  ·  openrouter/${model} "
done
tmux select-pane -t "$STATUS_PANE" -T " juju status --relations --watch=1s "
tmux select-pane -t "$LOG_PANE"    -T " juju debug-log --tail "

# Disable any per-pane shell prompts that would clutter the recording.
quiet_prompt='export PS1="\\[\\e[2m\\]\\W \\[\\e[0m\\]\\$ "; clear'
for p in "${PANES[@]}" "$STATUS_PANE" "$LOG_PANE"; do
    tmux send-keys -t "$p" "$quiet_prompt" Enter
done

# Give shells a beat to settle.
sleep 0.5

# Queue the per-pane commands without pressing Enter yet — they only start
# once asciinema is recording.
for i in "${!DEMOS[@]}"; do
    IFS='|' read -r name model upstream workload <<< "${DEMOS[$i]}"
    work_dir="$DEMO_RUN_DIR/$name"
    cmd=$(printf 'bash %q %q %q %q %q %q %q' \
        "$SCRIPT_DIR/pane-flow.sh" "$name" "$model" "$upstream" "$workload" "$work_dir" "$SENTINEL_DIR")
    tmux send-keys -t "${PANES[$i]}" "$cmd"
done

tmux send-keys -t "$STATUS_PANE" "juju status --relations --watch 1s --color"
tmux send-keys -t "$LOG_PANE"    "juju debug-log --tail --color --replay"

# ---------------------------------------------------------------------------
# Driver: press Enter in every pane once recording is rolling, then wait
# for the four demo panes to finish.
# ---------------------------------------------------------------------------

drive() {
    # Wait for asciinema to attach to tmux.  As soon as a client is present
    # the panes are visible, so we can safely start the commands.
    for _ in $(seq 1 40); do
        if tmux list-clients -t "$SESSION" 2>/dev/null | grep -q .; then
            break
        fi
        sleep 0.25
    done
    sleep 1.5

    # Kick off the monitors first so they're already rendering when the
    # demo panes start producing output.
    tmux send-keys -t "$STATUS_PANE" Enter
    tmux send-keys -t "$LOG_PANE"    Enter
    sleep 1.0

    # Stagger the four demos by a couple of seconds so their initial output
    # is interleaved rather than identical.
    for p in "${PANES[@]}"; do
        tmux send-keys -t "$p" Enter
        sleep 1.5
    done

    # Wait for all four sentinels (success or failure).
    local expected="${#DEMOS[@]}"
    while :; do
        local count
        count=$(find "$SENTINEL_DIR" -maxdepth 1 -name 'done.*' 2>/dev/null | wc -l)
        if [ "$count" -ge "$expected" ]; then
            break
        fi
        sleep 5
    done

    # Linger so the final state is visible.
    sleep 8

    tmux kill-session -t "$SESSION" 2>/dev/null || true
}

drive &
DRIVER_PID=$!

# ---------------------------------------------------------------------------
# Record
# ---------------------------------------------------------------------------

rm -f "$OUTPUT"
echo "Recording to $OUTPUT ..."
"${ASCIINEMA[@]}" rec \
    --overwrite \
    --cols "$COLS" \
    --rows "$ROWS" \
    --idle-time-limit "$IDLE_LIMIT" \
    --title "dashcraft demo" \
    --command "tmux -f $TMUX_CONF attach -t $SESSION" \
    "$OUTPUT"

wait "$DRIVER_PID" 2>/dev/null || true
echo "Done.  Cast file: $OUTPUT"
echo "View it with:"
echo "    cd $SCRIPT_DIR && python3 -m http.server 8000"
echo "    open http://localhost:8000"
