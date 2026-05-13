---
name: observability
description: Adding COS observability integration and ops-tracing to charms.
---

# Observability and COS Integration

Every production charm should integrate with the **Canonical Observability Stack (COS)**.

## Required Relations

Add to `charmcraft.yaml`:

```yaml
requires:
  tracing:
    interface: tracing
    limit: 1
  logging:
    interface: loki_push_api
provides:
  metrics-endpoint:
    interface: prometheus_scrape
  grafana-dashboard:
    interface: grafana_dashboard
```

## ops-tracing Setup

```toml
[project.dependencies]
ops-tracing = ["ops-tracing"]
```

```python
import ops
import ops_tracing


class MyCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self._tracing = ops_tracing.Tracing(self, "tracing")
```

The relation name passed to `Tracing` must match the `tracing:` entry under `requires:`. Do **not** use the legacy `ops_tracing.setup(self)` — it has been removed.

## Metrics Endpoint

```python
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider


class MyCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self._metrics = MetricsEndpointProvider(
            self,
            relation_name="metrics-endpoint",
            jobs=[{
                "static_configs": [{"targets": ["*:8080"]}],
                "scrape_interval": "30s",
            }],
        )
```

Alert rules go in `src/prometheus_alert_rules/*.yaml` and are forwarded automatically.

## Log Forwarding

```python
from charms.loki_k8s.v1.loki_push_api import LogForwarder


class MyCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self._log_forwarder = LogForwarder(self, relation_name="logging")
```

## Grafana Dashboards

```python
from charms.grafana_k8s.v0.grafana_dashboards import GrafanaDashboardProvider


class MyCharm(ops.CharmBase):
    def __init__(self, framework: ops.Framework):
        super().__init__(framework)
        self._grafana = GrafanaDashboardProvider(self)
```

Place dashboard JSON in `src/grafana_dashboards/`.

## Deploy COS and Relate

```bash
# Separate model for COS
juju add-model cos
juju deploy cos-lite --trust

# Cross-model relate from dev model
juju integrate my-charm:tracing cos.tempo:tracing
juju integrate my-charm:metrics-endpoint cos.prometheus:metrics-endpoint
juju integrate my-charm:logging cos.loki:logging
juju integrate my-charm:grafana-dashboard cos.grafana:grafana-dashboard
```

## Key Pitfalls

- `ops-tracing` is on PyPI, but `charms.prometheus_k8s.*`, `charms.loki_k8s.*`, `charms.grafana_k8s.*` need `charmcraft fetch-libs`
- Use `--trust` when deploying COS
- In Grafana queries for Pebble-forwarded logs, use `{charm="my-charm"}` not `{juju_charm="my-charm"}`
