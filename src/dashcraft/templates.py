"""Charm scaffolding templates for dashcraft charm-init."""

from __future__ import annotations


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
    return 'venv/\nbuild/\n*.charm\n.tox/\n.coverage\n__pycache__/\n*.py[cod]\n.idea\n.vscode/\n'


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
    _to_title(name)
    return (
        f'# {name}\n'
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


def _charmcraft_yaml(name: str, workload_image: str = '') -> str:
    title = _to_title(name)
    upstream_source = f'    upstream-source: {workload_image}\n' if workload_image else ''
    return (
        f'# {name} charm\n'
        'type: charm\n'
        f'name: {name}\n'
        f'title: {title} Charm\n'
        'summary: A very short one-line summary of the charm.\n'
        'description: |\n'
        '  A single sentence that says what the charm is, concisely and memorably.\n'
        '\n'
        '  A paragraph of one to three short sentences, that describe what the charm does.\n'
        '\n'
        '  A third paragraph that explains what need the charm meets.\n'
        '\n'
        '  Finally, a paragraph that describes whom the charm is useful for.\n'
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
        f'def test_deploy(charm: pathlib.Path, juju: jubilant.Juju):\n'
        '    """Deploy the charm under test."""\n'
        '    resources = {\n'
        '        "workload-image": METADATA["resources"]["workload-image"].get("upstream-source", "")\n'
        '    }\n'
        f'    juju.deploy(charm.resolve(), app="{name}", resources=resources)\n'
        '    juju.wait(jubilant.all_active)\n'
    )


def get_files(name: str, workload_image: str = '') -> dict[str, str]:
    """Return a mapping of relative path -> content for a scaffolded charm."""
    module_name = _to_module_name(name)
    return {
        '.gitignore': _gitignore(),
        'CONTRIBUTING.md': _contributing(),
        'LICENSE': _license(),
        'README.md': _readme(name),
        'charmcraft.yaml': _charmcraft_yaml(name, workload_image),
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
