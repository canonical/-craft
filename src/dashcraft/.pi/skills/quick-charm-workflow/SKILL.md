---
name: quick-charm-workflow
description: End-to-end workflow for quickly building a *mature* Juju charm — detect framework, choose path, scaffold, add the full set of bells and whistles, build, test, deploy.
---

# Quick Charm Builder Workflow

Core principle: **inspect first, generate second**. When invoked from
`dashcraft pack` the CLI has already analysed the workload and pre-filled
`charmcraft.yaml` + `src/charm.py` — do not regenerate. Polish, then add
every maturity feature below; a shipping charm needs all of them.

## Pick a path

| Workload | Path | Reference skill |
|---|---|---|
| Flask, Django, FastAPI, Go (web), Express, Spring Boot | 12-factor PaaS | `twelve-factor` |
| Bespoke long-running service / custom logic | Custom ops charm | `custom-charm` |
| DB, cache, broker, proxy, monitor (replication / clustering needs) | Infrastructure | `infrastructure-charm` |

Detection (first match wins): `requirements.txt`/`pyproject.toml` →
Python; `package.json` → Node; `go.mod` → Go; `pom.xml`/`build.gradle` →
JVM; `Dockerfile` → containerised. Then check framework deps inside.

## Fit-assessment checklist

Before touching files, settle:

1. Path (12-factor / custom / infrastructure).
2. K8s vs machine substrate. Default K8s; machine for bare metal, GPU,
   or systemd-only workloads.
3. Target Juju controller / model.
4. OCI registry (`localhost:32000` for local, remote for prod).
5. Required relations (database, ingress, observability, TLS).
6. Config surface (port, log level, secrets).

## Scaffold (path-specific)

### 12-factor
```bash
export CHARMCRAFT_ENABLE_EXPERIMENTAL_EXTENSIONS=true
export ROCKCRAFT_ENABLE_EXPERIMENTAL_EXTENSIONS=true
rockcraft init --profile=flask-framework        # or django/fastapi/go/express/spring-boot
rockcraft pack && skopeo copy oci-archive:*.rock docker://localhost:32000/...
mkdir charm && cd charm
charmcraft init --profile=flask-framework --name=my-app
charmcraft pack
```

### Custom
```bash
charmcraft init --profile=kubernetes   # or --profile=machine
# Edit charmcraft.yaml (containers/resources/config/relations) and src/charm.py.
charmcraft pack
```

### Infrastructure
Same scaffold as custom, plus:
- Search Charmhub first (`charmhub_search(query="redis")`) — extend rather
  than rebuild when there's an existing charm.
- Add peer relations for clustering, storage for persistence, actions for
  backup/restore/rotate-credentials.
- Document the workload's operations contract in `WORKLOAD.md` before
  writing code.

## Required maturity features

A charm is **not done** without these. The pre-filled scaffold declares
the relations and stubs in `charmcraft.yaml`, but Python wiring for each
must be added in `src/charm.py`. Load the linked skill for each.

| Feature | What it gives operators | Skill |
|---|---|---|
| **Metrics scraping** | Prometheus picks up workload metrics | `/skill:observability` |
| **Log forwarding** | Loki receives charm + workload logs | `/skill:observability` |
| **Grafana dashboards** | Auto-provisioned dashboards on integrate | `/skill:observability` |
| **Tracing** | `ops_tracing.Tracing(self, "tracing")` so charm hooks export OTLP spans | `/skill:observability` |
| **Ingress** (web apps) | External access via Traefik | `/skill:relations` |
| **Database relation** (stateful apps) | postgresql_client / mysql_client | `/skill:relations` |
| **TLS** (where applicable) | Per-unit certs via `tls-certificates` interface | `/skill:relations` |
| **Health-check action** | `juju run my-app/0 health-check` | `/skill:operational-patterns` |
| **Backup / restore actions** | Operator-driven data safety | `/skill:operational-patterns` |
| **Pause / resume actions** | Maintenance window control | `/skill:operational-patterns` |
| **Diagnostics action** | Bundled config + service state for support | `/skill:operational-patterns` |
| **Secrets** (any credential) | Juju secrets, never plain config | `/skill:operational-patterns` |
| **Status pattern** | A single `_reconcile()` setting `ActiveStatus` / `BlockedStatus("do X")` / `WaitingStatus` | `/skill:operational-patterns` |
| **Unit tests** | `ops.testing` Scenario-style tests for every hook | `/skill:charm-testing` |
| **Integration tests** | Jubilant tests that deploy + assert relations | `/skill:charm-testing` |

After dropping into a fresh charm directory, walk this table top-to-bottom
and add anything still missing. Do not stop at "the workload starts."

## Core hook shape

K8s charm (the pre-filled `src/charm.py` follows this — edit, don't recreate):
- `__init__` subscribes to `pebble_ready` (per container), `config_changed`,
  `secret_rotate`, every `<rel>_relation_changed`. Constructs
  `ops_tracing.Tracing(self, "tracing")` and observability libs from
  `cosl`/`charmlibs-*`. Stores `self.container = self.unit.get_container(...)`.
- `_on_pebble_ready` builds the Pebble layer, calls
  `add_layer(..., combine=True)` then `replan()`, sets `ActiveStatus`.
- `_on_config_changed` rebuilds + replans. Guard every Pebble call with
  `container.can_connect()` and `event.defer()` if not.

Machine charm differs in three places:
- `_on_install` runs apt to install the workload package.
- `_on_start` runs `systemctl enable --now`.
- `_on_config_changed` writes config to disk and restarts the service.

## Build, deploy, verify

```bash
charmcraft pack
juju deploy ./*.charm --resource oci-image=...   # --resource only for K8s
juju status --watch 5s
juju debug-log
```

## Fast iteration

In-place sync (no repack) while deployed:
```bash
jhack sync src/ my-app/0
jhack utils fire my-app/0 config-changed
```

Full cycle when metadata changes:
```bash
charmcraft pack && juju refresh my-app --path ./my-app_amd64.charm
```

## Common pitfalls

1. Forgetting `--trust` for K8s charms that need cluster-wide access.
2. Container name mismatch between `charmcraft.yaml` and `self.on["..."]`.
3. Missing `container.can_connect()` before Pebble calls.
4. Hook ends without setting a status.
5. Writing app-data from a non-leader unit (guard with `unit.is_leader()`).
6. Plain-text credentials in config (use Juju secrets).
7. Long-running blocking I/O in a hook (use an action instead).
8. Forgetting `container.replan()` after `add_layer()` — service won't restart.
9. Skipping the maturity table — a charm without metrics, logs, tracing,
   and the standard actions is not shippable.
