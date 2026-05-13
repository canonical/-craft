"""Tests for the filled (analysis-driven) charm templates."""

from __future__ import annotations

import ast

import pytest
import yaml

from dashcraft.analysis import WorkloadAnalysis
from dashcraft.templates import (
    filled_charmcraft_yaml,
    filled_src_charm_py,
    get_filled_files,
)

# A small set of analyses that exercise the conditional branches in the
# templates. ``parametrize`` lets us assert "the output always parses" without
# duplicating the assertion code per scenario.

_ANALYSES = {
    'minimal_no_port': WorkloadAnalysis(
        name='my-charm', command='/bin/run', summary='S', description='D'
    ),
    'web_app_with_port': WorkloadAnalysis(
        name='my-charm',
        command='python -m flask run',
        port=5000,
        framework='flask',
        language='python',
        is_web_app=True,
        summary='Flask app',
        description='A flask app.',
    ),
    'with_envvars': WorkloadAnalysis(
        name='svc',
        command='node index.js',
        port=3000,
        env_vars={'PORT': '3000', 'LOG_LEVEL': 'info'},
        is_web_app=True,
        framework='express',
        language='nodejs',
    ),
    'needs_database': WorkloadAnalysis(
        name='db-svc',
        command='/db-svc',
        port=8080,
        needs_database=True,
        has_postgres=True,
        env_vars={'DATABASE_URL': 'postgres://x', 'OTHER': '1'},
    ),
    'tricky_chars': WorkloadAnalysis(
        name='quoter',
        command='python -c "print(1)"',
        port=8000,
        env_vars={'GREETING': 'hello "world"'},
    ),
}


@pytest.mark.parametrize('analysis', _ANALYSES.values(), ids=list(_ANALYSES.keys()))
class TestSrcCharmPyParses:
    def test_generated_charm_py_parses(self, analysis: WorkloadAnalysis):
        src = filled_src_charm_py('my-charm', analysis)
        ast.parse(src)

    def test_generated_charm_py_imports_check_name(self, analysis: WorkloadAnalysis):
        assert 'CHECK_NAME = "service-ready"' in filled_src_charm_py('my-charm', analysis)

    def test_no_unresolved_typescript_artifacts(self, analysis: WorkloadAnalysis):
        # A common port bug from TS was a literal ${...} or `lines.push(`
        # leaking through. Spot-check.
        src = filled_src_charm_py('my-charm', analysis)
        assert '${' not in src
        assert 'lines.push' not in src


@pytest.mark.parametrize('analysis', _ANALYSES.values(), ids=list(_ANALYSES.keys()))
class TestCharmcraftYamlIsValid:
    def test_generated_yaml_parses(self, analysis: WorkloadAnalysis):
        text = filled_charmcraft_yaml('my-charm', analysis)
        doc = yaml.safe_load(text)
        assert isinstance(doc, dict)
        assert doc['type'] == 'charm'
        assert doc['name'] == 'my-charm'

    def test_resources_workload_image_present(self, analysis: WorkloadAnalysis):
        doc = yaml.safe_load(filled_charmcraft_yaml('my-charm', analysis))
        assert 'workload-image' in doc['resources']


class TestPortConfigOption:
    """Bug guard: src/charm.py reads `self.config.get("port", ...)` for ingress;
    the matching `port` option must be declared in charmcraft.yaml whenever
    we're a web app with a port.
    """

    def test_port_option_declared_for_web_app(self):
        analysis = WorkloadAnalysis(name='x', command='/x', port=5000, is_web_app=True)
        doc = yaml.safe_load(filled_charmcraft_yaml('x', analysis))
        assert 'port' in doc['config']['options']
        src = filled_src_charm_py('x', analysis)
        # Read the config in a way that doesn't nest double-quotes inside
        # the f-string (works on Python 3.10+).
        assert 'port = self.config.get("port", 5000)' in src
        assert 'f"http://{self.app.name}:{port}"' in src

    def test_no_ingress_for_non_web_app(self):
        analysis = WorkloadAnalysis(name='x', command='/x', port=8080)
        doc = yaml.safe_load(filled_charmcraft_yaml('x', analysis))
        assert 'ingress' not in doc.get('provides', {})


class TestRelationKeysSkippedFromConfig:
    def test_database_url_not_a_config_option(self):
        analysis = WorkloadAnalysis(
            name='x',
            command='/x',
            env_vars={'DATABASE_URL': 'postgres://x', 'LOG_LEVEL': 'info'},
            needs_database=True,
        )
        doc = yaml.safe_load(filled_charmcraft_yaml('x', analysis))
        opts = doc['config']['options']
        assert 'database-url' not in opts
        assert 'log-level' in opts
        # ...but the database relation IS declared
        assert 'database' in doc['requires']


class TestGetFilledFiles:
    def test_filled_files_overrides_charmcraft_and_charm_py(self):
        analysis = WorkloadAnalysis(
            name='svc',
            command='node index.js',
            port=3000,
            summary='A node service',
            description='Does node things.',
            is_web_app=True,
        )
        files = get_filled_files('my-charm', analysis, workload_image='myimg:latest')
        # The two driven-by-analysis files should differ from skeleton mode
        assert 'A node service' in files['charmcraft.yaml']
        assert 'node index.js' in files['src/charm.py']
        # Scaffold files still present
        assert files['LICENSE'].startswith('                                 Apache License')
        assert files['tox.ini']
        assert files['tests/unit/test_charm.py']
