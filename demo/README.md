# dashcraft recorded demo

A re-runnable asciinema recording of `dashcraft pack` charming four upstream
projects in parallel, each through a different OpenRouter provider, while two
panes show live `juju status` and `juju debug-log`.

```
┌──────────────────┬──────────────────┐
│  upvote-rss      │  suite-docs      │   anthropic/claude-sonnet-4.6   openai/gpt-5
├──────────────────┼──────────────────┤
│  booklore        │  ironcalc        │   google/gemini-2.5-pro         x-ai/grok-4
├──────────────────┼──────────────────┤
│  juju status     │  juju debug-log  │
└──────────────────┴──────────────────┘
```

## Prerequisites

- `tmux`, `python3`, `bash` — usually already installed.
- `asciinema` — `uvx asciinema` works if you'd rather not install it.
- `juju` with a bootstrapped controller.
- `dashcraft`, `pi`, `quickpack` on `$PATH`
  (`uv sync && uv tool install juju-cantrip && sudo npm install -g @earendil-works/pi-coding-agent`).
- `OPENROUTER_API_KEY` exported.

## Record

```bash
export OPENROUTER_API_KEY=sk-or-…
demo/record.sh --clean
```

Useful flags:

| flag | default | meaning |
|---|---|---|
| `--model NAME` | `dashcraft-demo` | juju model name to deploy the four charms into |
| `--output FILE` | `demo/dashcraft-demo.cast` | where to write the asciinema cast |
| `--cols N` | `220` | recording width in columns |
| `--rows N` | `64` | recording height in rows |
| `--idle-limit S` | `2` | cap idle gaps to S seconds in the cast file (huge speedup) |
| `--clean` | off | destroy the juju model first so the demo starts from scratch |

Re-running is safe: `record.sh` kills any previous demo tmux session and
(with `--clean`) recreates the juju model. The four charm packs run in
parallel; the recording stops once each pane has produced its sentinel.

## Play

```bash
cd demo
python3 -m http.server 8000
# open http://localhost:8000
```

The player defaults to **4x playback** so a ~20-min recording finishes in
roughly five minutes. Switch with the speed dropdown (1x–8x).

## How the speedup works

Three knobs combine to fit a long real run into a short playback:

1. `asciinema rec --idle-time-limit 2` — long silent gaps in the cast file
   are capped at 2 s.
2. The HTML player runs at 4x by default (configurable up to 8x).
3. Network-bound waits (model downloads, AI streams) compress
   well at high speed since they emit output frequently.

## Layout

The 6-pane layout lives in `record.sh` (see the diagram at the top of the
file). Adjust pane proportions by changing the `-p` / `-l` percentages
passed to `tmux split-window`.

## Files

| file | role |
|---|---|
| `record.sh` | entry point — validates prereqs, builds the tmux layout, drives the demo, records |
| `pane-flow.sh` | runs inside each of the four demo panes (types yaml → pack → deploy) |
| `typewriter.py` | char-by-char "typing" output used by pane-flow |
| `index.html` | asciinema-player for playback |
| `dashcraft-demo.cast` | produced by `record.sh` |
