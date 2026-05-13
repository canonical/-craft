---
name: operational-patterns
description: Actions, config validation, status management, backup/restore, and other operational readiness patterns.
---

# Operational Patterns

## Config Options

Declared in `charmcraft.yaml`:

```yaml
config:
  options:
    log-level:
      type: string
      default: info
      description: Logging verbosity: debug, info, warning, error.
    port:
      type: int
      default: 8080
      description: Port the workload listens on.
```

### Config validation

```python
VALID_LOG_LEVELS = {"debug", "info", "warning", "error"}


def _on_config_changed(self, event: ops.ConfigChangedEvent) -> None:
    log_level = self.config.get("log-level", "info")
    if log_level not in VALID_LOG_LEVELS:
        self.unit.status = ops.BlockedStatus(
            f"Invalid log-level: {log_level!r}. "
            f"Must be one of: {', '.join(sorted(VALID_LOG_LEVELS))}"
        )
        return

    port = self.config["port"]
    if not (1 <= port <= 65535):
        self.unit.status = ops.BlockedStatus(f"Invalid port: {port}")
        return

    self._apply_config()
    self.unit.status = ops.ActiveStatus()
```

Config names use hyphens; access with `self.config["log-level"]`.

## Actions

Declared in `charmcraft.yaml`:

```yaml
actions:
  backup:
    description: Create a backup of application data.
    params:
      path:
        type: string
        description: Destination path.
        default: /var/backups
    required: [path]
    additionalProperties: false
```

### Action handler

```python
def _on_backup(self, event: ops.ActionEvent) -> None:
    path = event.params["path"]
    try:
        backup_id = self._perform_backup(path)
        event.set_results({"backup-id": backup_id, "status": "success"})
    except FileNotFoundError:
        event.fail(f"Backup path does not exist: {path}")
```

### Leader-only actions

```python
def _on_rotate_credentials(self, event: ops.ActionEvent) -> None:
    if not self.unit.is_leader():
        event.fail("Credential rotation must run on the leader.")
        return
    self._rotate_password()
    event.set_results({"status": "rotated"})
```

### Long-running actions

```python
def _on_backup(self, event: ops.ActionEvent) -> None:
    event.log("Starting backup...")
    self._dump_database(event.params["path"])
    event.log("Compressing...")
    archive = self._compress_backup(event.params["path"])
    event.log("Backup complete.")
    event.set_results({"archive": str(archive)})
```

## Status Management

Use actionable messages — the operator should know what to do:

```python
# Missing config
if not self.config.get("database-uri"):
    self.unit.status = ops.BlockedStatus("Set 'database-uri' config to continue")
    return

# Missing relation
if not self.model.get_relation("database"):
    self.unit.status = ops.BlockedStatus("Integrate with a database: juju integrate <app> postgresql")
    return

# Waiting for data
if not relation.data[relation.app].get("connection-string"):
    self.unit.status = ops.WaitingStatus("Waiting for database credentials")
    return

# All good
self.unit.status = ops.ActiveStatus()
```

### Reconciliation pattern

```python
def _reconcile(self) -> None:
    """Single source of truth for unit status."""
    if self._is_paused():
        self.unit.status = ops.MaintenanceStatus("Paused — run 'resume' action")
        return
    if not self.model.get_relation("database"):
        self.unit.status = ops.BlockedStatus("Missing database relation")
        return
    self.unit.status = ops.ActiveStatus()
```

## Health-Check Action

```python
def _on_get_health(self, event: ops.ActionEvent) -> None:
    checks = {}

    # Core processes
    try:
        services = self._container.get_services()
        checks["processes"] = all(svc.is_running() for svc in services.values())
    except ops.pebble.ConnectionError:
        checks["processes"] = False

    # API check
    try:
        resp = httpx.get(f"http://localhost:{self._port}/health", timeout=5)
        checks["api"] = resp.status_code == 200
    except httpx.HTTPError:
        checks["api"] = False

    healthy = all(checks.values())
    event.set_results({"healthy": healthy, "checks": checks})
    if not healthy:
        event.fail(f"Unhealthy: {[k for k, v in checks.items() if not v]}")
```

## Pause and Resume

```python
def _on_pause(self, event: ops.ActionEvent) -> None:
    self._container.stop("workload")
    self._paused = True
    self.unit.status = ops.MaintenanceStatus("Paused — run 'resume' to restart")
    event.set_results({"status": "paused"})

def _on_resume(self, event: ops.ActionEvent) -> None:
    self._container.start("workload")
    self._paused = False
    self._reconcile()
    event.set_results({"status": "resumed"})
```

## Backup and Restore

```python
def _on_create_backup(self, event: ops.ActionEvent) -> None:
    timestamp = datetime.datetime.now(tz=datetime.UTC).strftime("%Y%m%d-%H%M%S")
    backup_path = f"/backups/{self.app.name}-{timestamp}.tar.gz"

    try:
        process = self._container.exec(
            ["pg_dump", "-Fc", "-f", backup_path],
            environment=self._db_env(),
        )
        process.wait_output()
    except ops.pebble.ExecError as e:
        event.fail(f"Backup failed: {e.stderr}")
        return

    event.set_results({"backup-id": timestamp, "path": backup_path, "status": "completed"})
```

## Diagnostics Bundle

```python
def _on_collect_diagnostics(self, event: ops.ActionEvent) -> None:
    bundle = {}

    # Config (scrub secrets)
    safe_config = {}
    for key, value in self.config.items():
        if any(s in key.lower() for s in ("password", "secret", "token", "key")):
            safe_config[key] = "***REDACTED***"
        else:
            safe_config[key] = str(value)
    bundle["config"] = safe_config

    # Services
    try:
        services = self._container.get_services()
        bundle["services"] = {
            name: {"running": svc.is_running()}
            for name, svc in services.items()
        }
    except ops.pebble.ConnectionError:
        bundle["services"] = "pebble not ready"

    event.set_results({"diagnostics": json.dumps(bundle, indent=2)})
```

## Secret Rotation

```python
def _on_secret_rotate(self, event: ops.SecretRotateEvent) -> None:
    new_password = self._generate_password()
    event.secret.set_content({"password": new_password})
```

## Publishing to Charmhub

```bash
# 1. Validate
charmcraft pack
charmcraft analyse ./my-charm.charm

# 2. Register (first time only)
charmcraft register my-charm

# 3. Upload
charmcraft upload ./my-charm.charm --release=edge

# 4. Promote through channels
charmcraft release my-charm --revision=5 --channel=beta
charmcraft promote my-charm --from=beta --to=stable
```

Channel flow: `edge` → `beta` → `candidate` → `stable`

## PyPI vs Charmhub Libraries

Prefer PyPI packages when available — they're versioned and avoid `charmcraft fetch-libs`:

| PyPI Package | Replaces |
|---|---|
| `ops-tracing` | — |
| `cosl` | COS Lite utilities |
| `charmlibs-pathops` | Pebble/local filesystem ops |
| `charmlibs-apt` | `charms.operator_libs_linux.v0.apt` |
| `charmlibs-snap` | `charms.operator_libs_linux.v*.snap` |
| `charmlibs-systemd` | `charms.operator_libs_linux.v*.systemd` |

Still need `charmcraft fetch-libs` for: `charms.loki_k8s.*`, `charms.grafana_k8s.*`, `charms.prometheus_k8s.*`, `charms.traefik_k8s.*`, `charms.tempo_*`, `charms.catalogue_k8s.*`, `charms.data_platform_libs.*`.
