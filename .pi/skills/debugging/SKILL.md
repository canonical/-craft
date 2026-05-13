---
name: debugging
description: Systematic diagnosis, debug iteration, and developer tooling for charms.
---

# Charm Debugging

## Five-Step Inspection

When a charm is stuck or misbehaving, inspect in this order:

### 1. Status

```bash
juju status
```

Read the **message** beside each unit — charms encode their diagnosis there.

### 2. Logs

```bash
juju debug-log --unit my-charm/0
```

Look for: ERROR/CRITICAL, Tracebacks, repeated hook failures, Pebble errors.

### 3. Relation Data

```bash
jhack show-relation my-charm postgresql
```

Check: databag exists, leader wrote app data, JSON parses, secret refs resolve.

### 4. Config

```bash
juju config my-charm
```

Compare against defaults and status messages.

### 5. Secrets

```bash
juju list-secrets
juju show-secret <id>
```

Check: ownership, latest revision vs referenced, grants present.

## Symptom → Cause → Action

| Symptom | Likely Cause | Next Action |
|---|---|---|
| `blocked`, message names relation | Missing `juju integrate` | `juju integrate` or check partner charm |
| `waiting` with "for Pebble" | Container crashloop / image pull fail | Check Pebble services, OCI image tag |
| `active` but workload broken | Status too permissive | Check workload reachability in status logic |
| `error` with exception | Uncaught hook failure | Read traceback; fix config or charm code |
| Repeating `update-status` failures | Long check without timeout | Add Pebble exec timeout |
| Relation data empty | Provider not leader or never wrote | Check leader, leader-elected handler |
| Secret ref fails to read | Rotation without update, or no grant | Check grants, re-emit databag value |
| Config change "does nothing" | No `_on_config_changed` or early return | Check reconciliation path |

## Iterate-Fix Strategy

### Categorise the failure

- **Environment** — concierge/Juju/controller issues (not charm bugs)
- **Deployment** — `juju deploy` failed, relation hook errored
- **Workload** — charm deployed but app crash-loops or misbehaves
- **Test** — integration/acceptance test failed

### Fix priority

1. Blockers (Error/Blocked status)
2. Crash-loops
3. Test failures with clear messages
4. Intermittent failures (check retry budget)
5. Warnings/cosmetic issues

### Retry budgets

- Never more than 3 fix attempts on the same failure
- If the same test/status fails across 2 attempts with fixes applied, escalate

## jhack Commands

```bash
# Inspection
jhack show-relation <app> <app>      # View relation data
jhack show-stored <unit>              # View stored state
jhack tail [unit]                     # Watch events live

# Rapid iteration
jhack sync src/ my-charm/0            # Push source to unit
jhack utils fire my-charm/0 config-changed  # Fire event manually

# Pebble (K8s)
jhack pebble -c workload my-charm/0 services
jhack pebble -c workload my-charm/0 logs myservice

# Debugging
jhack debug-log my-charm/0            # Unified logs
jhack eval my-charm/0 "self.unit.status"
jhack scenario snapshot my-charm/0    # Capture state for tests

# Cleanup
jhack nuke my-charm                   # Safe removal
jhack utils this-is-fine              # Auto-resolve errors
```

## Interactive Debugging

- **pdb in Scenario tests**: Drop `breakpoint()` in charm code, run `pytest -s` — no deploy needed
- **ops.Framework.breakpoint()**: Drops into pdb on next hook; attach with `juju debug-code`
- **debugpy**: Remote IDE debugger; add `debugpy.listen()` in `__init__`

## Structured Iteration Report

```
[iterate-fix] attempt <N>/<max>: <outcome>
What failed first: <summary>
What I tried: <fixes applied>
What's still broken: <remaining issues>
Next step: <specific tool call or question>
```
