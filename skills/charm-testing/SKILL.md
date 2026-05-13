---
name: charm-testing
description: Unit tests with ops.testing (Scenario) and integration tests with Jubilant + pytest-jubilant.
---

# Charm Testing

## Unit Tests — Scenario (ops.testing)

**Never use Harness** — it is deprecated. Scenario tests are state-transition tests: declare an input `State`, fire an event, assert on the output `State`.

### Setup

```toml
[dependency-groups]
unit = ["ops[testing]", "pytest", "coverage"]
```

### Basic test

```python
import ops
from ops import testing

from src.charm import MyCharm


def test_start_sets_active():
    ctx = testing.Context(MyCharm)
    state = testing.State()
    out = ctx.run(ctx.on.start(), state)
    assert out.unit_status == testing.ActiveStatus("ready")
```

### Test with relations

```python
def test_database_relation_joined():
    rel = testing.Relation(
        endpoint="database",
        interface="mysql",
        remote_app_data={"host": "db.local", "port": "3306"},
    )
    state = testing.State(relations=[rel])
    ctx = testing.Context(MyCharm)
    out = ctx.run(ctx.on.relation_joined(rel), state)
    assert out.unit_status == testing.ActiveStatus()
```

### Test with config (parametrised)

```python
import pytest


@pytest.mark.parametrize(
    "log_level,expected",
    [
        ("debug", testing.ActiveStatus()),
        ("verbose", testing.BlockedStatus("invalid log-level")),
    ],
)
def test_config_validation(log_level, expected):
    state = testing.State(config={"log-level": log_level})
    ctx = testing.Context(MyCharm)
    out = ctx.run(ctx.on.config_changed(), state)
    assert out.unit_status == expected
```

### Test containers and pushed files

```python
def test_pebble_ready_pushes_config():
    container = testing.Container(name="workload", can_connect=True)
    state = testing.State(containers={container})
    ctx = testing.Context(MyCharm)

    out = ctx.run(ctx.on.pebble_ready(container), state)

    root = testing.get_filesystem(ctx, "workload")
    config = (root / "etc" / "workload" / "config.yaml").read_text()
    assert "log-level: info" in config
```

### Test actions

```python
def test_backup_action():
    ctx = testing.Context(MyCharm)
    state = testing.State()
    out = ctx.run(ctx.on.action("backup", params={"path": "/data"}), state)
    assert out.action_results["status"] == "success"
```

### Test secrets

```python
def test_secret_changed():
    secret = testing.Secret(
        tracked_content={"password": "old"},
        latest_content={"password": "new"},
    )
    state = testing.State(secrets=[secret])
    ctx = testing.Context(MyCharm)
    out = ctx.run(ctx.on.secret_changed(secret), state)
    assert out.unit_status == testing.ActiveStatus()
```

### Multi-event sequences

```python
import dataclasses


def test_install_then_config_change():
    ctx = testing.Context(MyCharm)
    initial = testing.State()

    after_start = ctx.run(ctx.on.start(), initial)
    assert after_start.unit_status == testing.ActiveStatus()

    next_state = dataclasses.replace(after_start, config={"log-level": "debug"})
    final = ctx.run(ctx.on.config_changed(), next_state)
    assert final.unit_status == testing.ActiveStatus()
```

### Key rules

- `Context` reads metadata from `charmcraft.yaml` — do **not** pass `meta=` or `config=`
- One event per test; chain with `dataclasses.replace()` for sequences
- Use `ctx.on.<event>()` — never instantiate events directly
- Compare statuses with `==` (checks message too)
- Container `can_connect=False` is the default
- Use `pebble_ready`, not `start`, for container tests

### Coverage audit

Run the `scenario_coverage` tool against the charm directory to map every `framework.observe` registration to test functions and flag missing container/relation-broken coverage.

## Integration Tests — Jubilant

**Never use pytest-operator or python-libjuju** — they are legacy.

### Setup

```toml
[dependency-groups]
integration = [
    "jubilant>=1.8,<2",
    "pytest-jubilant>=2,<3",
]
```

### Conftest

```python
# tests/integration/conftest.py
import os
import pathlib

import pytest


@pytest.fixture(scope="session")
def charm():
    charm = os.environ.get("CHARM_PATH")
    if not charm:
        charm_dir = pathlib.Path()
        charms = list(charm_dir.glob("*.charm"))
        assert charms, f"No charms found in {charm_dir.absolute()}"
        assert len(charms) == 1, f"Found multiple charms: {charms}"
        charm = charms[0]
    path = pathlib.Path(charm).resolve()
    assert path.is_file(), f"{path} is not a file"
    return path
```

### Basic deploy test

```python
import jubilant

APP_NAME = "my-charm"


def test_deploy(juju: jubilant.Juju, charm):
    juju.deploy(charm)
    juju.wait(jubilant.all_active, timeout=300)
    status = juju.status()
    assert status.apps[APP_NAME].is_active
```

### Test with related apps

```python
def test_database_integration(juju: jubilant.Juju, charm):
    juju.deploy(charm)
    juju.deploy("postgresql-k8s", channel="14/stable", trust=True)
    juju.integrate(APP_NAME, "postgresql-k8s")
    juju.wait(jubilant.all_active, timeout=10 * 60)
```

### Test actions

```python
def test_backup_action(juju: jubilant.Juju):
    task = juju.run(f"{APP_NAME}/0", "backup", {"path": "/data"})
    assert task.status == "completed"
    assert "backup-id" in task.results
```

### Test config changes

```python
def test_config_change(juju: jubilant.Juju):
    juju.config(APP_NAME, {"log-level": "debug"})
    juju.wait(jubilant.all_active, timeout=120)
```

### Cross-model COS test

```python
import json

import jubilant
import pytest
import pytest_jubilant
import requests


@pytest.fixture(scope="module")
def cos(juju_factory: pytest_jubilant.JujuFactory):
    yield juju_factory.get_juju(suffix="cos")


def test_deploy_cos(cos: jubilant.Juju):
    cos.deploy("cos-lite", trust=True)
    cos.wait(jubilant.all_active, timeout=10 * 60)


def test_integrate_loki(juju: jubilant.Juju, cos: jubilant.Juju):
    cos.offer("loki", endpoint="logging")
    juju.integrate(APP_NAME, f"{cos.model}.loki")
    juju.wait(jubilant.all_active)
    cos.wait(jubilant.all_active)
```

### Key rules

- `pytest-jubilant` provides the `juju` fixture — do **not** write your own
- Pass resolved `pathlib.Path` to `juju.deploy` — not a string
- Use `jubilant.all_active` instead of hand-rolled predicates
- Set generous timeouts: 300s for deploys, 600s+ for multi-app, 10×60 for COS
- Use `trust=True` for cluster-wide charms
- Don't hardcode unit names beyond `<app>/0`
