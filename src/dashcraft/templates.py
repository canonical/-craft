"""Charm scaffolding templates for dashcraft charm-init."""

from __future__ import annotations

from dashcraft.analysis import WorkloadAnalysis

# Config-option keys that should be exposed through a relation rather than
# a charm config option (e.g. DATABASE_URL comes from the postgresql_client
# relation, not a free-form config string).
_RELATION_ENV_KEYS = {
    'database-url',
    'db-url',
    'redis-url',
    'redis-host',
    'postgres-url',
    'datasource-url',
    'mysql-url',
}


def _to_class_name(name: str) -> str:
    """Convert kebab-case to PascalCase + Charm suffix."""
    return ''.join(part.capitalize() for part in name.split('-')) + 'Charm'


def _to_module_name(name: str) -> str:
    """Convert kebab-case to snake_case."""
    return name.replace('-', '_')


def _to_title(name: str) -> str:
    """Convert kebab-case to Title Case."""
    return ' '.join(part.capitalize() for part in name.split('-'))


def _gitignore() -> str:
    return 'venv/\nbuild/\n*.charm\n.tox/\n.coverage\n__pycache__/\n*.py[cod]\n.idea\n.vscode/\n.pi/\n'


def _license() -> str:
    return (
        '                                 Apache License\n'
        '                           Version 2.0, January 2004\n'
        '                        http://www.apache.org/licenses/\n'
        '\n'
        '   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION\n'
        '\n'
        '   Copyright 2026 Ubuntu\n'
        '\n'
        '   Licensed under the Apache License, Version 2.0 (the "License");\n'
        '   you may not use this file except in compliance with the License.\n'
        '   You may obtain a copy of the License at\n'
        '\n'
        '       http://www.apache.org/licenses/LICENSE-2.0\n'
        '\n'
        '   Unless required by applicable law or agreed to in writing, software\n'
        '   distributed under the License is distributed on an "AS IS" BASIS,\n'
        '   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.\n'
        '   See the License for the specific language governing permissions and\n'
        '   limitations under the License.\n'
    )


def _readme(name: str) -> str:
    return (
        f'# {_to_title(name)}\n'
        '\n'
        f'Charmhub package name: {name}\n'
        f'More information: https://charmhub.io/{name}\n'
        '\n'
        'Describe your charm in one or two sentences.\n'
        '\n'
        '## Other resources\n'
        '\n'
        '- [Contributing](CONTRIBUTING.md)\n'
        '\n'
        '- See the [Juju documentation](https://documentation.ubuntu.com/juju/latest/) for more information.\n'
    )


def _contributing() -> str:
    return (
        '# Contributing\n'
        '\n'
        "To make contributions to this charm, you'll need a working\n"
        '[development setup](https://documentation.ubuntu.com/juju/latest/).\n'
        '\n'
        'You can create an environment for development with `tox`:\n'
        '\n'
        '```shell\n'
        'tox devenv -e integration\n'
        'source venv/bin/activate\n'
        '```\n'
        '\n'
        '## Testing\n'
        '\n'
        '```shell\n'
        'tox run -e format        # update your code according to linting rules\n'
        'tox run -e lint          # code style\n'
        'tox run -e static        # static type checking\n'
        'tox run -e unit          # unit tests\n'
        'tox run -e integration   # integration tests\n'
        "tox                      # runs 'format', 'lint', 'static', and 'unit'\n"
        '```\n'
        '\n'
        '## Build the charm\n'
        '\n'
        '```shell\n'
        'charmcraft pack\n'
        '```\n'
    )


def _charmcraft_yaml(
    name: str, workload_image: str = '', summary: str = '', description: str = ''
) -> str:
    title = _to_title(name)
    upstream_source = f'    upstream-source: {workload_image}\n' if workload_image else ''
    summary_line = (
        f'summary: {summary}\n'
        if summary
        else 'summary: A very short one-line summary of the charm.\n'
    )
    if description:
        # Indent each line of the description under the '|' block scalar
        desc_lines = description.split('\n')
        desc_block = '\n'.join(f'  {line}' for line in desc_lines)
        description_block = f'description: |\n{desc_block}\n'
    else:
        description_block = (
            'description: |\n'
            '  A single sentence that says what the charm is, concisely and memorably.\n'
            '\n'
            '  A paragraph of one to three short sentences, that describe what the charm does.\n'
            '\n'
            '  A third paragraph that explains what need the charm meets.\n'
            '\n'
            '  Finally, a paragraph that describes whom the charm is useful for.\n'
        )
    return (
        f'# {name} charm\n'
        'type: charm\n'
        f'name: {name}\n'
        f'title: {title} Charm\n'
        f'{summary_line}'
        f'{description_block}'
        '\n'
        'base: ubuntu@24.04\n'
        'platforms:\n'
        '  amd64:\n'
        '  arm64:\n'
        '\n'
        'parts:\n'
        '  charm:\n'
        '    plugin: uv\n'
        '    source: .\n'
        '    build-snaps:\n'
        '      - astral-uv\n'
        '\n'
        'config:\n'
        '  options:\n'
        '    log-level:\n'
        '      description: |\n'
        '        Configures the log level of the workload.\n'
        '        Acceptable values are: "info", "debug", "warning", "error"\n'
        '      default: "info"\n'
        '      type: string\n'
        '\n'
        'containers:\n'
        '  workload:\n'
        '    resource: workload-image\n'
        '\n'
        'resources:\n'
        '  workload-image:\n'
        '    type: oci-image\n'
        '    description: OCI image for the workload container\n'
        f'{upstream_source}'
    )


def _pyproject_toml(name: str) -> str:
    return (
        '# Copyright 2026 Ubuntu\n'
        '# See LICENSE file for licensing details.\n'
        '\n'
        '[project]\n'
        f'name = "{name}"\n'
        'version = "0.1.0"\n'
        'requires-python = ">=3.10"\n'
        '\n'
        'dependencies = [\n'
        '    "ops>=3,<4",\n'
        ']\n'
        '\n'
        '[dependency-groups]\n'
        'lint = [\n'
        '    "ruff",\n'
        '    "codespell",\n'
        '    "pyright",\n'
        ']\n'
        'unit = [\n'
        '    "coverage[toml]",\n'
        '    "ops[testing]",\n'
        '    "pytest",\n'
        ']\n'
        'integration = [\n'
        '    "jubilant",\n'
        '    "pytest",\n'
        '    "PyYAML",\n'
        ']\n'
        '\n'
        '[tool.coverage.run]\n'
        'branch = true\n'
        '\n'
        '[tool.coverage.report]\n'
        'show_missing = true\n'
        '\n'
        '[tool.pytest.ini_options]\n'
        'minversion = "6.0"\n'
        'log_cli_level = "INFO"\n'
        '\n'
        '[tool.ruff]\n'
        'line-length = 99\n'
        'lint.select = ["E", "W", "F", "C", "N", "D", "I001"]\n'
        'lint.ignore = [\n'
        '    "D105", "D107", "D203", "D204", "D213", "D215",\n'
        '    "D400", "D404", "D406", "D407", "D408", "D409", "D413",\n'
        ']\n'
        'extend-exclude = ["__pycache__", "*.egg_info"]\n'
        'lint.per-file-ignores = {"tests/*" = ["D100","D101","D102","D103","D104"]}\n'
        '\n'
        '[tool.ruff.lint.mccabe]\n'
        'max-complexity = 10\n'
        '\n'
        '[tool.codespell]\n'
        'skip = "build,lib,venv,icon.svg,.tox,.git,.mypy_cache,.ruff_cache,.coverage"\n'
        '\n'
        '[tool.pyright]\n'
        'include = ["src", "tests"]\n'
    )


def _tox_ini() -> str:
    return (
        '# Copyright 2026 Ubuntu\n'
        '# See LICENSE file for licensing details.\n'
        '\n'
        '[tox]\n'
        'no_package = True\n'
        'skip_missing_interpreters = True\n'
        'env_list = format, lint, unit\n'
        'min_version = 4.0.0\n'
        '\n'
        '[vars]\n'
        'src_path = {tox_root}/src\n'
        'tests_path = {tox_root}/tests\n'
        'all_path = {[vars]src_path} {[vars]tests_path}\n'
        '\n'
        '[testenv]\n'
        'set_env =\n'
        '    PYTHONPATH = {tox_root}/lib:{[vars]src_path}\n'
        '    PYTHONBREAKPOINT=pdb.set_trace\n'
        '    PY_COLORS=1\n'
        'pass_env =\n'
        '    PYTHONPATH\n'
        '    CHARM_BUILD_DIR\n'
        '    MODEL_SETTINGS\n'
        '\n'
        '[testenv:format]\n'
        'description = Apply coding style standards to code\n'
        'deps =\n'
        '    ruff\n'
        'commands =\n'
        '    ruff format {[vars]all_path}\n'
        '    ruff check --fix {[vars]all_path}\n'
        '\n'
        '[testenv:lint]\n'
        'description = Check code against coding style standards, and static checks\n'
        'runner = uv-venv-lock-runner\n'
        'dependency_groups =\n'
        '    lint\n'
        '    unit\n'
        '    integration\n'
        'commands =\n'
        '    codespell {tox_root}\n'
        '    ruff check {[vars]all_path}\n'
        '    ruff format --check --diff {[vars]all_path}\n'
        '    pyright {posargs}\n'
        '\n'
        '[testenv:unit]\n'
        'description = Run unit tests\n'
        'runner = uv-venv-lock-runner\n'
        'dependency_groups =\n'
        '    unit\n'
        'commands =\n'
        '    coverage run --source={[vars]src_path} -m pytest \n'
        '        -v -s --tb native {[vars]tests_path}/unit {posargs}\n'
        '    coverage report\n'
        '\n'
        '[testenv:integration]\n'
        'description = Run integration tests\n'
        'runner = uv-venv-lock-runner\n'
        'dependency_groups =\n'
        '    integration\n'
        'pass_env =\n'
        '    CHARM_PATH\n'
        'commands =\n'
        '    pytest -v -s --tb native --log-cli-level=INFO \n'
        '        {[vars]tests_path}/integration {posargs}\n'
    )


def _src_charm_py(name: str) -> str:
    class_name = _to_class_name(name)
    module_name = _to_module_name(name)
    return (
        '#!/usr/bin/env python3\n'
        '# Copyright 2026 Ubuntu\n'
        '# See LICENSE file for licensing details.\n'
        '\n'
        '"""Charm the application."""\n'
        '\n'
        'import logging\n'
        '\n'
        'import ops\n'
        '\n'
        f'import {module_name}\n'
        '\n'
        'logger = logging.getLogger(__name__)\n'
        '\n'
        'SERVICE_NAME = "workload"\n'
        '\n'
        '\n'
        f'class {class_name}(ops.CharmBase):\n'
        '    """Charm the application."""\n'
        '\n'
        '    def __init__(self, framework: ops.Framework):\n'
        '        super().__init__(framework)\n'
        '        framework.observe(self.on["workload"].pebble_ready, self._on_pebble_ready)\n'
        '        self.container = self.unit.get_container("workload")\n'
        '\n'
        '    def _on_pebble_ready(self, event: ops.PebbleReadyEvent) -> None:\n'
        '        """Handle pebble-ready event."""\n'
        '        self.unit.status = ops.MaintenanceStatus("starting workload")\n'
        '        layer: ops.pebble.LayerDict = {\n'
        '            "services": {\n'
        '                SERVICE_NAME: {\n'
        '                    "override": "replace",\n'
        '                    "summary": "Workload service",\n'
        '                    "command": "/bin/foo",  # Change this!\n'
        '                    "startup": "enabled",\n'
        '                    "environment": {},\n'
        '                }\n'
        '            }\n'
        '        }\n'
        '        self.container.add_layer("base", layer, combine=True)\n'
        '        self.container.replan()\n'
        f'        version = {module_name}.get_version()\n'
        '        if version is not None:\n'
        '            self.unit.set_workload_version(version)\n'
        '        self.unit.status = ops.ActiveStatus()\n'
        '\n'
        '\n'
        'if __name__ == "__main__":  # pragma: nocover\n'
        f'    ops.main({class_name})\n'
    )


def _src_workload_py(name: str) -> str:
    return (
        '# Copyright 2026 Ubuntu\n'
        '# See LICENSE file for licensing details.\n'
        '\n'
        '"""Functions for interacting with the workload."""\n'
        '\n'
        'import logging\n'
        '\n'
        'logger = logging.getLogger(__name__)\n'
        '\n'
        '\n'
        'def get_version() -> str | None:\n'
        '    """Get the running version of the workload."""\n'
        '    return None\n'
    )


def _unit_test_charm(name: str) -> str:
    class_name = _to_class_name(name)
    return (
        '# Copyright 2026 Ubuntu\n'
        '# See LICENSE file for licensing details.\n'
        '\n'
        'import pytest\n'
        'from ops import pebble, testing\n'
        '\n'
        f'from charm import SERVICE_NAME, {class_name}\n'
        '\n'
        '\n'
        'def test_pebble_ready():\n'
        '    """Test that the charm reaches active status after pebble-ready."""\n'
        f'    ctx = testing.Context({class_name})\n'
        '    container = testing.Container("workload", can_connect=True)\n'
        '    state = testing.State(containers={container})\n'
        '    out = ctx.run(ctx.on.pebble_ready(container), state)\n'
        '    assert out.unit_status == testing.ActiveStatus()\n'
        '\n'
    )


def _integration_conftest() -> str:
    return (
        '# Copyright 2026 Ubuntu\n'
        '# See LICENSE file for licensing details.\n'
        '\n'
        'import logging\n'
        'import os\n'
        'import pathlib\n'
        'import sys\n'
        'import time\n'
        '\n'
        'import jubilant\n'
        'import pytest\n'
        '\n'
        'logger = logging.getLogger(__name__)\n'
        '\n'
        '\n'
        '@pytest.fixture(scope="module")\n'
        'def juju(request: pytest.FixtureRequest):\n'
        '    """Create a temporary Juju model for running tests."""\n'
        '    with jubilant.temp_model() as juju:\n'
        '        yield juju\n'
        '\n'
        '        if request.session.testsfailed:\n'
        '            logger.info("Collecting Juju logs...")\n'
        '            time.sleep(0.5)\n'
        '            log = juju.debug_log(limit=1000)\n'
        '            print(log, end="", file=sys.stderr)\n'
        '\n'
        '\n'
        '@pytest.fixture(scope="session")\n'
        'def charm():\n'
        '    """Return the path of the charm under test."""\n'
        '    if "CHARM_PATH" in os.environ:\n'
        "        charm_path = pathlib.Path(os.environ['CHARM_PATH'])\n"
        '        if not charm_path.exists():\n'
        '            raise FileNotFoundError(f"Charm does not exist: {charm_path}")\n'
        '        return charm_path\n'
        "    charm_paths = list(pathlib.Path('.').glob('*.charm'))\n"
        '    if not charm_paths:\n'
        '        raise FileNotFoundError("No .charm file in current directory")\n'
        '    if len(charm_paths) > 1:\n'
        '        path_list = ", ".join(str(path) for path in charm_paths)\n'
        '        raise ValueError(f"More than one .charm file: {path_list}")\n'
        '    return charm_paths[0]\n'
    )


def _integration_test_charm(name: str) -> str:
    return (
        '# Copyright 2026 Ubuntu\n'
        '# See LICENSE file for licensing details.\n'
        '\n'
        'import pathlib\n'
        '\n'
        'import jubilant\n'
        'import yaml\n'
        '\n'
        'METADATA = yaml.safe_load(pathlib.Path("charmcraft.yaml").read_text())\n'
        '\n'
        '\n'
        'def test_deploy(charm: pathlib.Path, juju: jubilant.Juju):\n'
        '    """Deploy the charm under test."""\n'
        '    resources = {\n'
        '        "workload-image": METADATA["resources"]["workload-image"].get("upstream-source", "")\n'
        '    }\n'
        f'    juju.deploy(charm.resolve(), app="{name}", resources=resources)\n'
        '    juju.wait(jubilant.all_active)\n'
    )


def get_files(
    name: str, workload_image: str = '', summary: str = '', description: str = ''
) -> dict[str, str]:
    """Return a mapping of relative path -> content for a scaffolded charm."""
    module_name = _to_module_name(name)
    return {
        '.gitignore': _gitignore(),
        'CONTRIBUTING.md': _contributing(),
        'LICENSE': _license(),
        'README.md': _readme(name),
        'charmcraft.yaml': _charmcraft_yaml(name, workload_image, summary, description),
        'pyproject.toml': _pyproject_toml(name),
        'tox.ini': _tox_ini(),
        'src/charm.py': _src_charm_py(name),
        f'src/{module_name}.py': _src_workload_py(name),
        'tests/__init__.py': '',
        'tests/unit/__init__.py': '',
        'tests/unit/test_charm.py': _unit_test_charm(name),
        'tests/integration/__init__.py': '',
        'tests/integration/conftest.py': _integration_conftest(),
        'tests/integration/test_charm.py': _integration_test_charm(name),
    }


# ── Filled templates (from workload analysis) ─────────────────────────────


def filled_charmcraft_yaml(name: str, analysis: WorkloadAnalysis) -> str:
    """Render charmcraft.yaml populated from a workload analysis."""
    title = _to_title(name)
    parts: list[str] = []
    parts.append('# This file configures Charmcraft.')
    parts.append(
        '# See https://documentation.ubuntu.com/charmcraft/stable/reference/files/charmcraft-yaml-file/'
    )
    parts.append('type: charm')
    parts.append(f'name: {name}')
    parts.append(f'title: {title} Charm')
    parts.append(f'summary: {analysis.summary or "Charm for " + title}')
    parts.append('description: |')
    description = analysis.description or f'A Juju charm for deploying and operating {title}.'
    parts.extend(f'  {line}' for line in description.split('\n'))
    parts.append('')
    parts.append('base: ubuntu@24.04')
    parts.append('platforms:')
    parts.append('  amd64:')
    parts.append('  arm64:')
    parts.append('')
    parts.append('assumes:')
    parts.append('  - juju >= 3.6')
    parts.append('  - k8s-api')
    parts.append('')
    parts.append('parts:')
    parts.append('  charm:')
    parts.append('    plugin: uv')
    parts.append('    source: .')
    parts.append('    build-snaps:')
    parts.append('      - astral-uv')
    parts.append('')

    # ── Config ───────────────────────────────────────────────────────
    parts.append('config:')
    parts.append('  options:')
    parts.append('    log-level:')
    parts.append('      description: |')
    parts.append('        Configures the log level of the workload.')
    parts.append(
        '        Acceptable values are: "debug", "info", "warning", "error" and "critical"'
    )
    parts.append('      default: "info"')
    parts.append('      type: string')
    if analysis.port:
        parts.append('    port:')
        parts.append('      description: The port the workload listens on.')
        parts.append(f'      default: {analysis.port}')
        parts.append('      type: int')
    for key, val in analysis.env_vars.items():
        config_key = key.lower().replace('_', '-')
        if config_key in _RELATION_ENV_KEYS:
            continue
        parts.append(f'    {config_key}:')
        parts.append(f'      description: Sets the {key} environment variable.')
        # Escape any double quotes in the default value
        safe_val = val.replace('\\', '\\\\').replace('"', '\\"')
        parts.append(f'      default: "{safe_val}"')
        parts.append('      type: string')
    parts.append('')

    # ── Relations ────────────────────────────────────────────────────
    parts.append('provides:')
    parts.append('  metrics-endpoint:')
    parts.append('    interface: prometheus_scrape')
    parts.append('  grafana-dashboard:')
    parts.append('    interface: grafana_dashboard')
    if analysis.is_web_app:
        parts.append('  ingress:')
        parts.append('    interface: ingress')
    parts.append('')
    parts.append('requires:')
    parts.append('  tracing:')
    parts.append('    interface: tracing')
    parts.append('    limit: 1')
    parts.append('    optional: true')
    parts.append('  logging:')
    parts.append('    interface: loki_push_api')
    parts.append('    optional: true')
    if analysis.needs_database or analysis.has_postgres:
        parts.append('  database:')
        parts.append('    interface: postgresql_client')
        parts.append('    optional: true')
        parts.append('    limit: 1')
    parts.append('')

    # ── Actions ──────────────────────────────────────────────────────
    parts.append('actions:')
    parts.append('  health-check:')
    parts.append('    description: Run a comprehensive health check on the workload.')
    parts.append('  collect-diagnostics:')
    parts.append('    description: Collect diagnostic information about the deployment.')
    parts.append('')

    # ── Containers & resources ───────────────────────────────────────
    parts.append('containers:')
    parts.append('  workload:')
    parts.append('    resource: workload-image')
    parts.append('')
    parts.append('resources:')
    parts.append('  workload-image:')
    parts.append('    type: oci-image')
    parts.append('    description: OCI image for the workload container')
    parts.append(f'    upstream-source: {analysis.name}:latest  # TODO: confirm image tag')
    parts.append('')

    return '\n'.join(parts)


def filled_src_charm_py(name: str, analysis: WorkloadAnalysis) -> str:
    """Render src/charm.py populated from a workload analysis."""
    class_name = _to_class_name(name)
    module_name = _to_module_name(name)
    title = _to_title(name)
    env_present = bool(analysis.env_vars)
    safe_command = analysis.command.replace('\\', '\\\\').replace('"', '\\"')

    lines: list[str] = [
        '#!/usr/bin/env python3',
        '# Copyright 2026 Ubuntu',
        '# See LICENSE file for licensing details.',
        '',
        f'"""Charm for {title}."""',
        '',
        'import logging',
        'import time',
        '',
        'import ops',
        '',
        f'import {module_name}',
        '',
        'logger = logging.getLogger(__name__)',
        '',
        'SERVICE_NAME = "workload"',
        'CHECK_NAME = "service-ready"',
        '',
        '',
        f'class {class_name}(ops.CharmBase):',
        f'    """Charm for {title}."""',
        '',
        '    def __init__(self, framework: ops.Framework):',
        '        super().__init__(framework)',
        '        framework.observe(self.on["workload"].pebble_ready, self._on_pebble_ready)',
        '        self.container = self.unit.get_container("workload")',
    ]
    if analysis.needs_database:
        lines.append(
            '        framework.observe(self.on.database_relation_changed, self._on_database_changed)'
        )
    if analysis.is_web_app:
        lines.append(
            '        framework.observe(self.on.ingress_relation_joined, self._on_ingress_joined)'
        )
    lines += [
        '',
        '    def _on_pebble_ready(self, event: ops.PebbleReadyEvent) -> None:',
        '        """Handle pebble-ready event."""',
        '        self.unit.status = ops.MaintenanceStatus("starting workload")',
    ]
    if env_present:
        lines.append('        env = {')
        for key, val in analysis.env_vars.items():
            config_key = key.lower().replace('_', '-')
            safe_val = val.replace('\\', '\\\\').replace('"', '\\"')
            lines.append(f'            "{key}": self.config.get("{config_key}", "{safe_val}"),')
        lines.append('        }')

    lines += [
        '        layer: ops.pebble.LayerDict = {',
        '            "services": {',
        '                SERVICE_NAME: {',
        '                    "override": "replace",',
        f'                    "summary": "{title} service",',
        f'                    "command": "{safe_command}",',
        '                    "startup": "enabled",',
    ]
    if env_present:
        lines.append('                    "environment": env,')
    lines += [
        '                },',
        '            },',
    ]
    if analysis.port:
        lines += [
            '            "checks": {',
            '                CHECK_NAME: {',
            '                    "override": "replace",',
            '                    "level": "ready",',
            '                    "http": {',
            f'                        "url": "http://localhost:{analysis.port}",',
            '                    },',
            '                },',
            '            },',
        ]
    lines += [
        '        }',
        '        self.container.add_layer("workload", layer, combine=True)',
        '        self.container.replan()',
        '        self.wait_for_ready()',
        f'        version = {module_name}.get_version()',
        '        if version is not None:',
        '            self.unit.set_workload_version(version)',
        '        self.unit.status = ops.ActiveStatus()',
        '',
    ]

    if analysis.needs_database:
        lines += [
            '    def _on_database_changed(self, event: ops.RelationChangedEvent) -> None:',
            '        """Handle database relation changes."""',
            '        if not event.relation.data.get(event.app):',
            '            return',
            '        # TODO: configure workload with database credentials',
            '',
        ]

    if analysis.is_web_app:
        # Split the inner config lookup out so the f-string has no nested
        # double quotes — keeps it valid on Python < 3.12.
        lines += [
            '    def _on_ingress_joined(self, event: ops.RelationJoinedEvent) -> None:',
            '        """Handle ingress relation."""',
            '        if not self.unit.is_leader():',
            '            return',
            f'        port = self.config.get("port", {analysis.port or 8080})',
            '        event.relation.data[self.app]["url"] = f"http://{self.app.name}:{port}"',
            '',
        ]

    lines += [
        '    def is_ready(self) -> bool:',
        '        """Check whether the workload is ready to use."""',
        '        for name, service_info in self.container.get_services().items():',
        '            if not service_info.is_running():',
        '                logger.info(',
        '                    "the workload is not ready (service \'%s\' is not running)", name',
        '                )',
        '                return False',
        '        checks = self.container.get_checks(level=ops.pebble.CheckLevel.READY)',
        '        for check_info in checks.values():',
        '            if check_info.status != ops.pebble.CheckStatus.UP:',
        '                return False',
        '        return True',
        '',
        '    def wait_for_ready(self) -> None:',
        '        """Wait for the workload to be ready to use."""',
        '        for _ in range(3):',
        '            if self.is_ready():',
        '                return',
        '            time.sleep(1)',
        '        logger.error("the workload was not ready within the expected time")',
        '        raise RuntimeError("workload is not ready")',
        '',
        '',
        'if __name__ == "__main__":  # pragma: nocover',
        f'    ops.main({class_name})',
        '',
    ]

    return '\n'.join(lines)


def get_filled_files(
    name: str, analysis: WorkloadAnalysis, workload_image: str = ''
) -> dict[str, str]:
    """Return path -> content with charmcraft.yaml and src/charm.py filled from analysis."""
    files = get_files(
        name,
        workload_image=workload_image,
        summary=analysis.summary,
        description=analysis.description,
    )
    files['charmcraft.yaml'] = filled_charmcraft_yaml(name, analysis)
    files['src/charm.py'] = filled_src_charm_py(name, analysis)
    return files
