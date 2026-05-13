"""Workload analysis — research a cloned upstream source tree.

The output is a :class:`WorkloadAnalysis` summary that the CLI uses to fill
charmcraft.yaml and src/charm.py before pi is launched. Running the analysis
server-side avoids a full LLM round-trip for the agent's first tool call.

Heuristics covered:

* Dockerfile: ``EXPOSE``, ``ENV K=V`` and legacy ``ENV K V``, ``CMD``/
  ``ENTRYPOINT`` (both shell-form and JSON-array-form), multi-stage builds
  (only the final stage's directives are kept).
* ``docker-compose.yml`` / ``.yaml``: parsed with PyYAML; per-service
  ``environment``/``ports`` are merged.
* ``package.json``: name/description/framework (express, next, fastify,
  koa), start command, ``.env`` / ``.env.example``.
* ``go.mod``: module name + web-framework hints.
* ``requirements.txt`` / ``pyproject.toml``: project name, framework
  (flask, django, fastapi) by *package-name* regex (not substring), startup
  command.
* ``Cargo.toml``: package name.
* ``README.md`` / ``README.rst``: first heading as fallback summary.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass
class WorkloadAnalysis:
    """Structured summary of a workload source tree."""

    name: str
    summary: str = ''
    description: str = ''
    language: str = 'unknown'
    framework: str = 'none'
    command: str = ''
    port: int = 0
    env_vars: dict[str, str] = field(default_factory=dict)
    has_dockerfile: bool = False
    has_docker_compose: bool = False
    docker_expose_ports: list[int] = field(default_factory=list)
    docker_cmd_hint: str = ''
    needs_database: bool = False
    needs_cache: bool = False
    is_web_app: bool = False
    has_postgres: bool = False


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ''


def _find_file(base: Path, names: list[str]) -> Path | None:
    for name in names:
        p = base / name
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# Dockerfile parsing
# ---------------------------------------------------------------------------


_DOCKER_STAGE_RE = re.compile(r'^\s*FROM\s+', re.IGNORECASE)
_DOCKER_EXPOSE_RE = re.compile(r'^\s*EXPOSE\s+(.+?)\s*$', re.IGNORECASE)
_DOCKER_ENV_KV_RE = re.compile(r'^\s*ENV\s+(\w+)\s*=\s*(.+?)\s*$', re.IGNORECASE)
_DOCKER_ENV_SPACE_RE = re.compile(r'^\s*ENV\s+(\w+)\s+(.+?)\s*$', re.IGNORECASE)
_DOCKER_CMD_RE = re.compile(r'^\s*(?:CMD|ENTRYPOINT)\s+(.+?)\s*$', re.IGNORECASE)


def _split_dockerfile_stages(text: str) -> list[str]:
    """Split a Dockerfile into per-stage chunks. The last entry is the final stage."""
    stages: list[list[str]] = [[]]
    for line in text.splitlines():
        if _DOCKER_STAGE_RE.match(line) and stages[-1]:
            stages.append([])
        stages[-1].append(line)
    return ['\n'.join(stage) for stage in stages if stage]


def _parse_docker_cmd(raw: str) -> str:
    """Normalise CMD/ENTRYPOINT value.

    JSON-array form ``["python", "app.py"]`` -> ``python app.py``. Other
    forms are returned with trailing comments stripped.
    """
    raw = raw.strip()
    # Strip a trailing inline comment, but only outside quoted/JSON forms.
    if '#' in raw and not raw.startswith(('"', '[')):
        raw = raw.split('#', 1)[0].strip()
    if raw.startswith('['):
        try:
            parts = json.loads(raw)
            if isinstance(parts, list):
                return ' '.join(str(p) for p in parts)
        except json.JSONDecodeError:
            pass
    return raw


def _parse_dockerfile(text: str) -> tuple[list[int], dict[str, str], str]:
    """Return ``(expose_ports, env, cmd_hint)`` for the *final* build stage."""
    stages = _split_dockerfile_stages(text)
    final = stages[-1] if stages else ''
    expose: list[int] = []
    env: dict[str, str] = {}
    cmd_hint = ''
    pending: list[str] = []
    for raw_line in final.splitlines():
        if raw_line.rstrip().endswith('\\'):
            pending.append(raw_line.rstrip()[:-1])
            continue
        line = ''.join(pending) + raw_line if pending else raw_line
        pending = []
        m = _DOCKER_EXPOSE_RE.match(line)
        if m:
            for tok in m.group(1).split():
                num = tok.split('/', 1)[0]
                if num.isdigit():
                    expose.append(int(num))
            continue
        m = _DOCKER_ENV_KV_RE.match(line)
        if m:
            env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
            continue
        m = _DOCKER_ENV_SPACE_RE.match(line)
        if m:
            env[m.group(1)] = m.group(2).strip().strip('"').strip("'")
            continue
        m = _DOCKER_CMD_RE.match(line)
        if m:
            cmd_hint = _parse_docker_cmd(m.group(1))
    return expose, env, cmd_hint


# ---------------------------------------------------------------------------
# docker-compose parsing
# ---------------------------------------------------------------------------


_INFRA_RESERVED = {
    'image',
    'ports',
    'environment',
    'command',
    'build',
    'depends_on',
    'restart',
    'volumes',
    'networks',
    'container_name',
    'expose',
    'env_file',
    'healthcheck',
    'labels',
    'logging',
    'security_opt',
    'user',
    'working_dir',
}


def _parse_compose(text: str) -> tuple[dict[str, str], list[int]]:
    """Pull env vars and host ports from a compose document."""
    try:
        doc = yaml.safe_load(text) or {}
    except yaml.YAMLError:
        return {}, []
    services = doc.get('services') if isinstance(doc, dict) else None
    if not isinstance(services, dict):
        return {}, []
    env: dict[str, str] = {}
    ports: list[int] = []
    for svc in services.values():
        if not isinstance(svc, dict):
            continue
        envs = svc.get('environment')
        if isinstance(envs, dict):
            for k, v in envs.items():
                if k not in _INFRA_RESERVED:
                    env[str(k)] = '' if v is None else str(v)
        elif isinstance(envs, list):
            for item in envs:
                if isinstance(item, str) and '=' in item:
                    k, v = item.split('=', 1)
                    if k and k not in _INFRA_RESERVED:
                        env[k] = v
        for p in svc.get('ports', []) or []:
            # forms: "8080:80", "127.0.0.1:8080:80", 8080, "8080"
            if isinstance(p, int):
                ports.append(p)
                continue
            if not isinstance(p, str):
                continue
            tail = p.split(':')[-1].split('/')[0]
            if tail.isdigit():
                ports.append(int(tail))
    return env, ports


# ---------------------------------------------------------------------------
# Language / framework detection
# ---------------------------------------------------------------------------


def _py_pkg_re(name: str) -> re.Pattern[str]:
    """Match *name* as a top-level package in requirements.txt or pyproject.toml.

    Accepts the name at start-of-line (requirements.txt) or after an opening
    quote (pyproject dependency list). Rejects matches followed by an
    identifier char so ``Flask-Login`` doesn't masquerade as ``flask``.
    """
    return re.compile(
        r'(?i)(?:^|["\'])\s*' + re.escape(name) + r'(?:[<>=!~"\'\s\[#]|$)',
        re.MULTILINE,
    )


def _detect_python_framework(reqs_text: str, pyproject_text: str) -> str:
    combined = reqs_text + '\n' + pyproject_text
    if _py_pkg_re('flask').search(combined):
        return 'flask'
    if _py_pkg_re('django').search(combined):
        return 'django'
    if _py_pkg_re('fastapi').search(combined):
        return 'fastapi'
    return 'none'


def _parse_env_file(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        eq = s.find('=')
        if eq <= 0:
            continue
        k = s[:eq]
        v = s[eq + 1 :].strip().strip('"').strip("'")
        out[k] = v
    return out


def _readme_summary(text: str) -> str:
    for line in text.splitlines():
        m = re.match(r'^\s*#\s+(.+)', line)
        if m:
            return re.sub(r'[`*_~]', '', m.group(1)).strip()
    return ''


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def analyse_workload(workload_dir: Path, charm_name: str) -> WorkloadAnalysis:
    """Research a cloned workload directory and return structured analysis.

    Args:
        workload_dir: Path to the cloned upstream source.
        charm_name: kebab-case charm name (used as a fallback for the
            workload's name/summary).
    """
    analysis = WorkloadAnalysis(name=charm_name)

    # Dockerfile (any of the common names; first hit wins).
    dockerfile = _find_file(workload_dir, ['Dockerfile', 'Dockerfile.prod', 'Dockerfile.dev'])
    if dockerfile is not None:
        analysis.has_dockerfile = True
        expose, env, cmd_hint = _parse_dockerfile(_read(dockerfile))
        analysis.docker_expose_ports = expose
        analysis.env_vars.update(env)
        analysis.docker_cmd_hint = cmd_hint

    # docker-compose
    compose = _find_file(workload_dir, ['docker-compose.yml', 'docker-compose.yaml'])
    if compose is not None:
        analysis.has_docker_compose = True
        env, ports = _parse_compose(_read(compose))
        analysis.env_vars.update(env)
        analysis.docker_expose_ports.extend(ports)

    # Language detection
    if (workload_dir / 'package.json').exists():
        analysis.language = 'nodejs'
        try:
            pkg = json.loads(_read(workload_dir / 'package.json'))
        except json.JSONDecodeError, ValueError:
            pkg = {}
        if pkg.get('name'):
            analysis.name = pkg['name']
        if pkg.get('description'):
            analysis.summary = pkg['description']
            analysis.description = pkg['description']
        deps = {**(pkg.get('dependencies') or {}), **(pkg.get('devDependencies') or {})}
        if 'express' in deps:
            analysis.framework = 'express'
        elif 'next' in deps:
            analysis.framework = 'nextjs'
        elif 'fastify' in deps:
            analysis.framework = 'fastify'
        elif 'koa' in deps:
            analysis.framework = 'koa'
        scripts = pkg.get('scripts') or {}
        if 'start' in scripts:
            analysis.command = 'npm start'
        elif 'dev' in scripts:
            analysis.command = 'npm run dev'
        elif pkg.get('main'):
            analysis.command = f'node {pkg["main"]}'
        dotenv = _find_file(workload_dir, ['.env.example', '.env'])
        if dotenv is not None:
            analysis.env_vars.update(_parse_env_file(_read(dotenv)))
        if analysis.env_vars.get('PORT', '').isdigit():
            analysis.port = int(analysis.env_vars['PORT'])
        analysis.is_web_app = analysis.framework in {'express', 'nextjs', 'fastify', 'koa'}

    elif (workload_dir / 'go.mod').exists():
        analysis.language = 'go'
        gomod = _read(workload_dir / 'go.mod')
        m = re.search(r'^module\s+(\S+)', gomod, re.MULTILINE)
        if m:
            analysis.name = m.group(1).rsplit('/', 1)[-1]
        if any(
            f in gomod for f in ('gin-gonic/gin', 'labstack/echo', 'gofiber/fiber', 'go-chi/chi')
        ):
            analysis.is_web_app = True
        analysis.command = f'/{analysis.name}'

    elif (workload_dir / 'requirements.txt').exists() or (
        workload_dir / 'pyproject.toml'
    ).exists():
        analysis.language = 'python'
        reqs = _read(workload_dir / 'requirements.txt')
        ppt = _read(workload_dir / 'pyproject.toml')
        analysis.framework = _detect_python_framework(reqs, ppt)
        # Try to grab project name from pyproject
        if ppt:
            m = re.search(r'^\s*name\s*=\s*"([^"]+)"', ppt, re.MULTILINE)
            if m:
                analysis.name = m.group(1)
        if analysis.framework == 'flask':
            analysis.command = 'python -m flask run --host=0.0.0.0'
            analysis.port = 5000
        elif analysis.framework == 'django':
            analysis.command = 'python manage.py runserver 0.0.0.0:8000'
            analysis.port = 8000
        elif analysis.framework == 'fastapi':
            analysis.command = 'uvicorn app.main:app --host 0.0.0.0 --port 8000'
            analysis.port = 8000
        analysis.is_web_app = analysis.framework in {'flask', 'django', 'fastapi'}

    elif (workload_dir / 'Cargo.toml').exists():
        analysis.language = 'rust'
        cargo = _read(workload_dir / 'Cargo.toml')
        m = re.search(r'^\s*name\s*=\s*"([^"]+)"', cargo, re.MULTILINE)
        if m:
            analysis.name = m.group(1)
        analysis.command = f'/{analysis.name}'

    # Dockerfile CMD/EXPOSE take precedence over heuristics
    if analysis.docker_cmd_hint:
        analysis.command = analysis.docker_cmd_hint
    if analysis.docker_expose_ports:
        analysis.port = analysis.docker_expose_ports[0]

    # README fallback for summary
    readme = _find_file(workload_dir, ['README.md', 'README.rst'])
    if readme is not None and not analysis.summary:
        summary = _readme_summary(_read(readme))
        if summary:
            analysis.summary = summary

    # Database / cache signals
    db_keys = {'DATABASE_URL', 'DB_URL', 'POSTGRES_URL', 'DATABASE_HOST'}
    cache_keys = {'REDIS_URL', 'REDIS_HOST'}
    if any(k in analysis.env_vars for k in db_keys):
        analysis.needs_database = True
    if any('POSTGRES' in k for k in analysis.env_vars):
        analysis.has_postgres = True
    if any(k in analysis.env_vars for k in cache_keys):
        analysis.needs_cache = True

    # Defaults to keep filled templates sane
    if not analysis.summary:
        analysis.summary = f'Charm for {analysis.name}'
    if not analysis.description:
        bits = [f'A Juju charm that deploys and manages {analysis.name}.']
        if analysis.language != 'unknown':
            suffix = f' ({analysis.framework})' if analysis.framework != 'none' else ''
            bits.append(f'Built with {analysis.language}{suffix}.')
        analysis.description = ' '.join(bits)
    if not analysis.command:
        analysis.command = '/bin/sh'

    return analysis
