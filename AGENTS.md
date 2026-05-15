# Agent guide for the `dashcraft` repo

`dashcraft` (aliased on PATH as `-craft`) is a fast, AI-driven charm
generator in the spirit of Canonical's "crafts" (charmcraft, snapcraft,
…) but **not** built on the upstream craft framework — it's a small,
lightweight prototype.

Given an upstream git repo and a model name, `dashcraft pack` produces
a fully-featured Juju charm (observability, ingress, relations, config
options, actions) and packs it into a `.charm` file ready for
`juju deploy`.

## Project shape

```
dashcraft.yaml                # user-facing config (see below)
src/dashcraft/
  cli.py        argparse entry point; orchestrates the pack pipeline
  config.py     dashcraft.yaml parsing
  upstream.py   git clone helper
  analysis.py   deterministic workload research (Dockerfile, package.json, etc.)
  templates.py  skeleton + filled charm templates (charmcraft.yaml, src/charm.py, …)
  pi.py         pi (AI agent) RPC client
  .pi/          extension + skills bundled with each generated charm
tests/unit/                   pytest suite — kept fast and offline
tests/spread/                 end-to-end suites (require pi + sometimes juju)
```

## `dashcraft.yaml`

```yaml
name: ...
summary: ...
description: ...
type: charm

parts:
  charm:
    plugin: -craft
    upstream: <git URL>          # the workload's source repo
    workload: <oci-image:tag>    # the workload's published image (optional)
    model: <model name>          # AI model (optional, default: gemini/gemini-2.5-flash)
    language: <reserved>
```

`dashcraft pack` does, in order:

1. parse `dashcraft.yaml`
2. clone `upstream` into `.dashcraft-tmp/upstream/`
3. analyse the cloned tree (`analysis.py`) → `WorkloadAnalysis`
4. scaffold a charm into `.dashcraft-tmp/charm/` with templates filled
   from the analysis (no AI yet — purely deterministic)
5. run pi against the scaffold via the bundled `.pi` extension to
   polish, lint, and unit-test
6. `quickpack` the result; move the `.charm` beside `dashcraft.yaml`

## Required local tooling

- `git`, `uv` (we depend on `>=3.14`), `node` + npm
- `quickpack` — `uv tool install juju-cantrip`
- `pi` — `sudo npm install -g @earendil-works/pi-coding-agent`
- One of the supported pi API-key env vars set
  (`OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, …)

## Agent workflow

Before reporting work complete, the agent **must** run:

```
make format    # ruff format + ruff check --fix --unsafe-fixes
make lint      # ruff check, ruff format --diff, ty check
make unit      # pytest tests/unit (with coverage)
```

All three must pass cleanly. If anything fails, fix and re-run until
`make all` is green.

## Spread tests

Two tracks under `tests/spread/`:

- `pack-*`, `dashcraft-*` — end-to-end pack pipeline (including pi)
  followed by unzip-and-verify. Require an OpenRouter (or equivalent)
  API key in the environment.
- `deploy-*` — pack **and** deploy on a concierge-microk8s controller.
  Require concierge + juju, slow; gated behind the `run-deploy-tests`
  PR label in CI.

Both tracks share `tests/spread/charm-helpers.sh`. New pack suites are
a 4-line `task.yaml` that sources the helpers and calls
`pack_and_verify`; new deploy suites call `pack_and_deploy`.

## Things to avoid

- Don't reach for `dashcraft_rpc.py` or `clone_upstream` — both have
  been removed.
- Don't reintroduce `.tmp/` as a working dir name; use the existing
  `.dashcraft-tmp/` (rationale: too easy to clobber unrelated user
  data when `--project-dir` is misdirected).
- Don't add comments that just restate the next line of code, and
  don't add docstrings to private one-liners.
