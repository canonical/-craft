---
name: operational-patterns
description: Actions, config validation, status management, backup/restore, diagnostics, secret rotation, and other operational readiness patterns a mature charm needs.
---

# Operational Patterns

A mature charm provides config validation, the full action set
(health-check, backup, restore, pause, resume, collect-diagnostics,
rotate-credentials), an actionable status story, and Juju-secret-backed
credentials. Add all of these — none are optional.

## Config

Declare options in `charmcraft.yaml`:
```yaml
config:
  options:
    log-level:
      type: string
      default: info
      description: "debug | info | warning | error"
    port:
      type: int
      default: 8080
      description: Port the workload listens on.
```

Validate on `config_changed` and set `BlockedStatus` with an actionable
message on invalid input — never silently accept:

```python
VALID_LOG_LEVELS = {"debug", "info", "warning", "error"}

def _on_config_changed(self, event: ops.ConfigChangedEvent) -> None:
    if self.config["log-level"] not in VALID_LOG_LEVELS:
        self.unit.status = ops.BlockedStatus(
            f"Invalid log-level: must be one of {sorted(VALID_LOG_LEVELS)}"
        )
        return
    if not (1 <= self.config["port"] <= 65535):
        self.unit.status = ops.BlockedStatus(f"Invalid port: {self.config['port']}")
        return
    self._apply_config()
    self._reconcile()
```

Config keys use hyphens; access with `self.config["log-level"]`.

## Actions (mature charm checklist)

A shippable charm provides **all** of these, declared in
`charmcraft.yaml` under `actions:`:

| Action | Purpose |
|---|---|
| `health-check` | Probe processes + API; return per-check booleans |
| `create-backup` | Snapshot workload state (DB dump, file archive) |
| `restore-backup` | Replay a backup; verify integrity first |
| `pause` | Stop the workload service for maintenance |
| `resume` | Restart and re-reconcile |
| `rotate-credentials` | Generate a new password / cert (leader-only) |
| `collect-diagnostics` | Bundle config (redacted) + service state for support |

### Action handler pattern
```python
def _on_backup(self, event: ops.ActionEvent) -> None:
    path = event.params["path"]
    try:
        backup_id = self._perform_backup(path)
        event.set_results({"backup-id": backup_id, "status": "success"})
    except FileNotFoundError:
        event.fail(f"Backup path does not exist: {path}")
```

Leader-only actions guard with `self.unit.is_leader()` and `event.fail()`
otherwise. Long-running actions call `event.log("...")` for progress so
`juju show-action-output` is readable.

### Diagnostics action — always redact

When bundling config or env for support, scrub anything containing
`password`, `secret`, `token`, `key`:
```python
safe = {
    k: ("***REDACTED***" if any(s in k.lower() for s in ("password","secret","token","key")) else str(v))
    for k, v in self.config.items()
}
event.set_results({"diagnostics": json.dumps({"config": safe, ...}, indent=2)})
```

### Backup snippet (Pebble exec)
```python
process = self._container.exec(
    ["pg_dump", "-Fc", "-f", backup_path], environment=self._db_env(),
)
process.wait_output()
```

## Status — single source of truth

Every code path ends with a status. Centralise in `_reconcile()`:

```python
def _reconcile(self) -> None:
    if self._is_paused():
        self.unit.status = ops.MaintenanceStatus("Paused — run 'resume' action")
        return
    if not self.model.get_relation("database"):
        self.unit.status = ops.BlockedStatus(
            "Integrate with a database: juju integrate <app> postgresql"
        )
        return
    relation = self.model.get_relation("database")
    if not relation.data[relation.app].get("connection-string"):
        self.unit.status = ops.WaitingStatus("Waiting for database credentials")
        return
    self.unit.status = ops.ActiveStatus()
```

Pick the right type:
- `BlockedStatus` — operator must do something (set config, integrate).
- `WaitingStatus` — waiting on Juju/another charm to deliver something.
- `MaintenanceStatus` — busy or intentionally paused.
- `ActiveStatus` — running normally.

## Health-check action shape

```python
def _on_health_check(self, event: ops.ActionEvent) -> None:
    checks = {
        "processes": all(s.is_running() for s in self._container.get_services().values()),
        "api": _probe(f"http://localhost:{self._port}/health"),
    }
    healthy = all(checks.values())
    event.set_results({"healthy": healthy, "checks": checks})
    if not healthy:
        event.fail(f"Unhealthy: {[k for k,v in checks.items() if not v]}")
```

## Pause / resume

```python
def _on_pause(self, event):
    self._container.stop("workload")
    self.unit.status = ops.MaintenanceStatus("Paused — run 'resume' to restart")

def _on_resume(self, event):
    self._container.start("workload")
    self._reconcile()
```

## Secrets — always Juju, never config

Generate on first leader hook; expose to relations via id, never value:
```python
secret = self.app.add_secret({"password": _generate_password()})
secret.grant(relation)
event.relation.data[self.app]["password-id"] = secret.id
```

Implement `_on_secret_rotate` (and observe `self.on.secret_rotate`):
```python
def _on_secret_rotate(self, event: ops.SecretRotateEvent) -> None:
    event.secret.set_content({"password": _generate_password()})
```

## Publishing to Charmhub

```bash
charmcraft pack
charmcraft analyse ./*.charm           # lint before upload
charmcraft register my-charm           # first time only
charmcraft upload ./*.charm --release=edge
charmcraft promote my-charm --from=edge --to=beta
```
Channel flow: `edge` → `beta` → `candidate` → `stable`.

## PyPI vs Charmhub libraries

Prefer PyPI — versioned, no `charmcraft fetch-libs` step:

| PyPI package | Replaces |
|---|---|
| `ops-tracing` | (new) |
| `cosl` | COS Lite utilities |
| `charmlibs-pathops` | Pebble / local filesystem ops |
| `charmlibs-apt` | `charms.operator_libs_linux.v0.apt` |
| `charmlibs-snap` | `charms.operator_libs_linux.v*.snap` |
| `charmlibs-systemd` | `charms.operator_libs_linux.v*.systemd` |

Still need `charmcraft fetch-libs` for: `loki_k8s`, `grafana_k8s`,
`prometheus_k8s`, `traefik_k8s`, `tempo_*`, `catalogue_k8s`,
`data_platform_libs`.
