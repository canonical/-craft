---
name: relations
description: Designing and implementing relation data bags for charm integrations.
---

# Relation Data Bag Design

## Data Bag Scopes

- **Application data bag** — shared across all units. Only the **leader** can write. Use for shared config (connection strings, endpoints).
- **Unit data bag** — per-unit data. Any unit can write. Use for unit-specific info (IP addresses).

## Define in Metadata

```yaml
provides:
  website:
    interface: http

requires:
  database:
    interface: postgresql_client
    optional: true
    limit: 1

peers:
  cluster:
    interface: cluster
```

**Always include `optional: true` or `optional: false`** for `requires` relations.

## Consumer Side (Requires)

```python
def _on_database_changed(self, event: ops.RelationChangedEvent) -> None:
    if not event.relation.data.get(event.app):
        return
    data = event.relation.data[event.app]
    host = data.get("host")
    port = data.get("port")
    if not host or not port:
        self.unit.status = ops.WaitingStatus("Waiting for database credentials")
        return
    # Configure workload
```

## Provider Side (Provides)

```python
def _on_website_relation_joined(self, event: ops.RelationJoinedEvent) -> None:
    if not self.unit.is_leader():
        return
    event.relation.data[self.app]["url"] = f"http://{self._hostname}:8080"
```

## Peer Relations

```python
def _on_cluster_relation_changed(self, event: ops.RelationChangedEvent) -> None:
    for unit in event.relation.units:
        unit_data = event.relation.data[unit]
        ip = unit_data.get("ip")
        if ip:
            # Add to cluster membership
            ...

def _set_unit_address(self) -> None:
    rel = self.model.get_relation("cluster")
    if rel:
        rel.data[self.unit]["ip"] = str(
            self.model.get_binding("cluster").network.bind_address
        )
```

## Design Principles

1. **App data for shared config, unit data for per-unit info.**
2. **Only the leader writes app data.** Guard with `self.unit.is_leader()`.
3. **Validate before using.** Remote data may be incomplete.
4. **Use `relation-changed` for updates.** Handle partial data gracefully.
5. **Use `relation-broken` for cleanup.** Remove dependent config.
6. **All values must be strings.** Serialize complex data with JSON if needed.
7. **Keep data bags small.** Under 1 KB per key. Store references, not payloads.
8. **Use interface libraries where possible.** They handle serialization and versioning.

## Secrets in Relation Data

Put only the **secret ID** (opaque string) in the relation databag — never the secret body.

```python
# Owner side
secret = self.model.get_secret(label="db-password")
secret.grant(event.relation)
event.relation.data[self.app]["password-id"] = secret.id

# Consumer side
secret_id = event.relation.data[event.app].get("password-id")
if not secret_id:
    return
secret = self.model.get_secret(id=secret_id)
password = secret.get_content()["password"]
```

Rules:
- Secret IDs are opaque — do not parse or assume format
- Only the offering application can call `secret.grant(relation)`
- Consumers just `get_secret(id=...)` — never manage grants

## Common Pitfalls

- Writing app data from non-leader → use `is_leader()` guard
- Reading `event.relation.data[event.app]` without None guard
- Putting secret bodies in relation data
- Not handling `relation-broken`
- Forgetting `optional` on requires relations
