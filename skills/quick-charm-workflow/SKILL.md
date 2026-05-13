---
name: quick-charm-workflow
description: End-to-end workflow for quickly building Juju charms — detect framework, choose path, scaffold, build, test, deploy.
---

# Quick Charm Builder Workflow

This skill covers the complete workflow for building a Juju charm from an existing application. The key principle: **inspect first, generate second**.

## Decision: Which Path?

Before doing anything, determine what kind of application you're charming:

| Application Type | Path | Skill |
|---|---|---|
| Flask, Django, FastAPI, Go, Express, Spring Boot | 12-factor PaaS | `twelve-factor` |
| Custom app (not a PaaS framework) | Custom ops charm | `custom-charm` |
| Database, cache, message broker, proxy, monitor | Infrastructure | `infrastructure-charm` |

### Quick Detection

1. Inspect the repository root for framework signals:
   - `requirements.txt` with `flask`/`django`/`fastapi` → Python web framework
   - `go.mod` → Go
   - `package.json` with Express → Node.js
   - `pom.xml`/`build.gradle` → Spring Boot
   - `Dockerfile` or `docker-compose.yml` → containerised app
   - `systemd` service files → machine app

2. If no PaaS framework matches, check for operational patterns:
   - Single binary/long-running service → custom charm
   - Replication/clustering/backup needs → infrastructure charm
   - Database/cache/broker → infrastructure charm

## Phase 1: Fit Assessment (All Paths)

Before generating any files, answer these questions:

1. **What framework/path?** — Confirm with the user if ambiguous
2. **K8s or machine substrate?** — Default to K8s; use machine for bare metal/GPU/systemd
3. **Target Juju controller and model?** — Get or create one
4. **Registry for OCI images?** — Local (`localhost:32000`) or remote
5. **Required relations?** — Database, ingress, observability, TLS, etc.
6. **Config options needed?** — Port, log level, secrets, etc.

## Phase 2: Scaffold

### 12-Factor Path

```bash
# Create charm/ subdirectory
mkdir charm

# Init with framework profile
charmcraft init --profile=flask-framework --name=my-app  # or django, fastapi, go, express, spring-boot

# Experimental profiles need:
export CHARMCRAFT_ENABLE_EXPERIMENTAL_EXTENSIONS=true
export ROCKCRAFT_ENABLE_EXPERIMENTAL_EXTENSIONS=true
```

Build both a **rock** and a **charm**:
1. `rockcraft init --profile=flask-framework` → generates `rockcraft.yaml`
2. Edit `rockcraft.yaml` for app-specific needs
3. `rockcraft pack`
4. Push rock to registry
5. `charmcraft pack` in `charm/` directory
6. Deploy with `--resource oci-image=...`

### Custom Charm Path

```bash
charmcraft init --profile=kubernetes  # or --profile=machine
```

Build directly — no rockcraft needed:
1. Edit `charmcraft.yaml` — add containers/resources/config/relations
2. Implement `src/charm.py` with Pebble (K8s) or systemd (machine)
3. `charmcraft pack`
4. `juju deploy ./my-app.charm`

### Infrastructure Charm Path

```bash
charmcraft init --profile=kubernetes  # or machine
```

Research first:
1. Search Charmhub for existing charms: `charmhub_search(query="redis")`
2. If exists: evaluate, fork, or extend
3. If building new: deep research of upstream docs, write `WORKLOAD.md`

Scaffold with extra metadata:
- Peer relations for clustering
- Storage for persistent data
- Actions for backup/restore
- Client relations for service access

## Phase 3: Implement

### Core Patterns (All Paths)

#### charmcraft.yaml essentials

```yaml
name: my-charm
type: charm
base: ubuntu@24.04
build-base: ubuntu@24.04
platforms:
  amd64:

parts:
  charm:
    plugin: uv
    source: .
    build-snaps:
      - astral-uv

assumes:
  - juju >= 3.6
  - k8s-api  # Remove for machine charms
```

#### src/charm.py K8s template

```python
#!/usr/bin/env python3
"""Charm for my-app on Kubernetes."""

import ops
import ops_tracing


class MyAppCharm(ops.CharmBase):
    """Charm the application using Pebble."""

    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self._tracing = ops_tracing.Tracing(self, "tracing")
        self._container = self.unit.get_container("workload")

        framework.observe(self.on["workload"].pebble_ready, self._on_pebble_ready)
        framework.observe(self.on.config_changed, self._on_config_changed)

    def _on_pebble_ready(self, event: ops.PebbleReadyEvent) -> None:
        """Start the workload when the container is ready."""
        self._container.add_layer("workload", self._pebble_layer(), combine=True)
        self._container.autostart()
        self.unit.status = ops.ActiveStatus()

    def _on_config_changed(self, event: ops.ConfigChangedEvent) -> None:
        """Update the workload config and restart if running."""
        if not self._container.can_connect():
            event.defer()
            return
        self._container.add_layer("workload", self._pebble_layer(), combine=True)
        self._container.replan()
        self.unit.status = ops.ActiveStatus()

    def _pebble_layer(self) -> ops.pebble.LayerDict:
        """Return the Pebble layer configuration."""
        return {
            "summary": "workload layer",
            "services": {
                "workload": {
                    "override": "replace",
                    "summary": "workload service",
                    "command": "/usr/bin/my-app",
                    "startup": "enabled",
                    "environment": {
                        "PORT": str(self.config.get("port", 8080)),
                        "LOG_LEVEL": self.config.get("log-level", "info"),
                    },
                },
            },
        }


if __name__ == "__main__":
    ops.main(MyAppCharm)
```

#### Machine charm variant

```python
def _on_install(self, event: ops.InstallEvent) -> None:
    self.unit.status = ops.MaintenanceStatus("Installing dependencies")
    subprocess.check_call(["apt-get", "update", "-y"])
    subprocess.check_call(["apt-get", "install", "-y", "my-app"])

def _on_start(self, event: ops.StartEvent) -> None:
    subprocess.check_call(["systemctl", "enable", "--now", "my-app"])
    self.unit.status = ops.ActiveStatus()

def _on_config_changed(self, event: ops.ConfigChangedEvent) -> None:
    self._write_config()
    subprocess.check_call(["systemctl", "restart", "my-app"])
    self.unit.status = ops.ActiveStatus()
```

### Status Patterns

Every hook must end with a defined status:

```python
def _reconcile(self) -> None:
    """Single source of truth for unit status."""
    if not self.model.get_relation("database"):
        self.unit.status = ops.BlockedStatus("Integrate with a database")
        return
    self.unit.status = ops.ActiveStatus()
```

### Relation Patterns

**Requires (consumer) side:**
```python
framework.observe(self.on.database_relation_changed, self._on_database_changed)

def _on_database_changed(self, event: ops.RelationChangedEvent) -> None:
    if not event.relation.data.get(event.app):
        return
    data = event.relation.data[event.app]
    host = data.get("host")
    if not host:
        self.unit.status = ops.WaitingStatus("Waiting for database credentials")
        return
    # Configure workload
```

**Provides (provider) side:**
```python
def _on_website_relation_joined(self, event: ops.RelationJoinedEvent) -> None:
    if not self.unit.is_leader():
        return
    event.relation.data[self.app]["url"] = f"http://{self._hostname}:8080"
```

### Secrets

```python
# Store
secret = self.app.add_secret({"password": generated_password})
secret.grant(relation)
event.relation.data[self.app]["password-id"] = secret.id

# Retrieve
secret_id = event.relation.data[event.app].get("password-id")
secret = self.model.get_secret(id=secret_id)
password = secret.get_content()["password"]
```

## Phase 4: Build, Deploy, Verify

### 12-Factor

```bash
# Build rock
rockcraft pack

# Push to registry
skopeo copy --insecure-policy --dest-tls-verify=false \
  oci-archive:my-app_0.1_amd64.rock \
  docker://localhost:32000/my-app:latest

# Build charm
charmcraft pack

# Deploy with resource
juju deploy ./my-app_amd64.charm --resource oci-image=localhost:32000/my-app:latest
```

### Custom / Infrastructure

```bash
charmcraft pack
juju deploy ./my-app_amd64.charm
```

### Verify

```bash
juju status --watch 5s
juju debug-log
```

## Phase 5: Iterate

Fast dev cycle (no repack):
```bash
# Push source changes to running unit
jhack sync src/ my-app/0
# Fire event to test
jhack utils fire my-app/0 config-changed
```

Full cycle when metadata changes:
```bash
charmcraft pack → juju refresh --path → juju status → verify
```

## Common Pitfalls

1. **Forgetting `--trust`** on K8s charms that need cluster-wide access
2. **Wrong container name** — must match between `charmcraft.yaml` and `self.on["name"]`
3. **Missing `can_connect()` guard** — always check before Pebble calls
4. **Not setting status** — every code path must set a status
5. **Writing app data from non-leader** — guard with `self.unit.is_leader()`
6. **Secrets in config** — use Juju secrets, never plain config for credentials
7. **Blocking I/O in hooks** — use actions for long-running operations
8. **No `replan()` after layer change** — service won't restart without it
