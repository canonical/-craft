This is the repository for the `-craft` (dashcraft) application. This is a 'craft' application in the spirit of Canonical's crafts (charmcraft, snapcraft, etc) -- but not a real craft application using the core craft library, a lightweight prototype of a new craft in the sprit of the crafts. This craft is for charming, but a dashing version (charming but fast :)). Here's the intended UX:

```
# dashcraft.yaml
name: ...
summary: ...
description: ...
type: charm

parts:
  charm:
    plugin: -craft
    upstream: <the software to charm, a git URL>
    model: <the AI model to use>
    language: <reserved for future use>
```

The user calls `-craft pack`, which produces a packed charm for the upstream software. Then the user can call `juju deploy <packed charm>`, and everything just works.

-craft is an application that uses AI to write a charm for a specified workload on the fly. The charm is a mature charm with all the recommended integrations (observability, ingress, authentication, etc), as well as all the features needed to provide an opinionated and fully featured experience for the administrator of this deployment (config, actions, workfload specific relations, etc).

## Agent workflow

Before reporting that work is complete, the agent **must** always run:

```
make format
make lint
make unit
```

All three must pass cleanly. If any command fails, fix the problem and re-run until the suite passes. Do not report work as complete until `make all` (`format` + `lint` + `unit`) succeeds.

- `make format` — runs ruff format + ruff check --fix to auto-format and fix autofixable lint issues
- `make lint` — runs ruff check, ruff format --diff, and pyright for static type checking
- `make unit` — runs pytest with coverage on tests/unit
