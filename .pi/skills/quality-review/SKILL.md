---
name: quality-review
description: Security review and bug-hunting for charm code before finishing.
---

# Quality Review

Run these before declaring a BUILD task done.

## Security Review

### HIGH (fix before finishing)

- **Shell injection**: No `shell=True` in `subprocess.run` with user input; always use list arguments
- **Secrets in config**: No `password`, `token`, `key` in `charmcraft.yaml` config; use Juju secrets
- **Secrets logged**: Never write secrets to `logger.info/debug`, exceptions, or status messages
- **Path traversal**: Resolve paths with `Path(base).resolve()` and verify `is_relative_to(base)`

### MEDIUM (fix silently if one-liner)

- Unbounded `subprocess.run` without timeout
- Missing `str.format` validation
- Broad `except Exception`

### Security Checklist

- [ ] No `shell=True` anywhere unless command is entirely literal
- [ ] No `os.system`, `os.popen`, `commands.getoutput`
- [ ] No secrets in config options
- [ ] Secret content never logged — use "[redacted]"
- [ ] Numeric fields parsed with `int()`/`float()` in `try/except`
- [ ] URL scheme validated as `http`/`https`
- [ ] Private IPs rejected unless explicitly needed
- [ ] `except Exception:` not used in auth/TLS/secret paths
- [ ] `yaml.safe_load`, never `yaml.load`
- [ ] No `pickle.load` on untrusted data
- [ ] `verify=False` / `ssl.CERT_NONE` never appear
- [ ] Cert files written with `chmod 0o400`/`0o600`

## Bug Hunting (find-bugs)

### Checks

1. **Status handling**: Every hook sets `self.unit.status` before every `return`
2. **Event observers**: All registered in `__init__`, not in hook handlers
3. **Pebble layers**: `add_layer(..., combine=True)` + `replan()` (not `restart()`)
4. **Relation data**: App writes guarded by `is_leader()`; reads handle empty case
5. **Secrets**: Observers registered; `get_content(refresh=True)` in `secret_changed`
6. **Storage**: `storage-attached` handler exists if storage declared
7. **Actions**: `event.set_results()` or `event.fail()` called; never bare raise
8. **COS**: `tracing` relation present; `ops_tracing.Tracing(self, "...")` in `__init__`

### Anti-patterns

- `except Exception: pass` — swallows failures, leaves status stale
- `try: self.container.push(...) except ChangeError: pass` — hides Pebble failures
- `threading.Thread` in hooks — hooks must complete within ~30 seconds

## Report Format

```
[security-review] <N> HIGH, <M> MEDIUM fixed silently

HIGH: src/charm.py:142 — shell=True with config-derived arg
  Evidence: subprocess.run(f"migrate {self.config['db-url']}", shell=True)
  Fix: passed args as list; removed shell=True
```

```
[find-bugs] <N> HIGH, <M> MEDIUM, <K> LOW

HIGH: src/charm.py:87 — missing status update on error path
  Fix: set BlockedStatus("invalid config: ...") before returning
```
