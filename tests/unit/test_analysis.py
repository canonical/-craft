"""Tests for dashcraft.analysis."""

from __future__ import annotations

from pathlib import Path

import pytest

from dashcraft.analysis import (
    WorkloadAnalysis,
    _parse_compose,
    _parse_docker_cmd,
    _parse_dockerfile,
    _split_dockerfile_stages,
    analyse_workload,
)

# ── Dockerfile parsing ────────────────────────────────────────────────────


class TestParseDockerfile:
    def test_expose_single_port(self):
        _, _, _ = _parse_dockerfile('FROM alpine\nEXPOSE 8080\n')
        ports, _, _ = _parse_dockerfile('FROM alpine\nEXPOSE 8080\n')
        assert ports == [8080]

    def test_expose_multiple_ports_one_line(self):
        ports, _, _ = _parse_dockerfile('FROM alpine\nEXPOSE 8080 9090 3000\n')
        assert ports == [8080, 9090, 3000]

    def test_expose_with_protocol(self):
        ports, _, _ = _parse_dockerfile('FROM alpine\nEXPOSE 53/udp 80/tcp\n')
        assert ports == [53, 80]

    def test_env_kv_form(self):
        _, env, _ = _parse_dockerfile('FROM alpine\nENV PORT=8080\nENV NAME="foo bar"\n')
        assert env == {'PORT': '8080', 'NAME': 'foo bar'}

    def test_env_legacy_space_form(self):
        _, env, _ = _parse_dockerfile('FROM alpine\nENV PORT 8080\n')
        assert env == {'PORT': '8080'}

    def test_cmd_shell_form(self):
        _, _, cmd = _parse_dockerfile('FROM alpine\nCMD python app.py\n')
        assert cmd == 'python app.py'

    def test_cmd_json_array_form(self):
        _, _, cmd = _parse_dockerfile('FROM alpine\nCMD ["python", "app.py"]\n')
        assert cmd == 'python app.py'

    def test_entrypoint_falls_back_to_cmd(self):
        _, _, cmd = _parse_dockerfile('FROM alpine\nENTRYPOINT ["/bin/myapp"]\n')
        assert cmd == '/bin/myapp'

    def test_multi_stage_takes_final_stage(self):
        text = (
            'FROM golang AS build\n'
            'ENV BUILD_ONLY=1\n'
            'EXPOSE 9999\n'
            'CMD ["build", "this"]\n'
            'FROM alpine AS runtime\n'
            'ENV PORT=8080\n'
            'EXPOSE 8080\n'
            'CMD ["./run"]\n'
        )
        ports, env, cmd = _parse_dockerfile(text)
        assert ports == [8080]
        assert env == {'PORT': '8080'}
        assert cmd == './run'

    def test_env_line_continuation(self):
        text = 'FROM alpine\nENV \\\n  PORT=8080\n'
        _, env, _ = _parse_dockerfile(text)
        assert env == {'PORT': '8080'}


class TestParseDockerCmd:
    def test_json_array_returns_space_joined(self):
        assert _parse_docker_cmd('["python", "-m", "flask", "run"]') == 'python -m flask run'

    def test_shell_form_returned_verbatim(self):
        assert _parse_docker_cmd('python app.py') == 'python app.py'

    def test_invalid_json_array_returned_as_string(self):
        assert _parse_docker_cmd('[python, app.py]') == '[python, app.py]'

    def test_trailing_comment_stripped_for_shell_form(self):
        assert _parse_docker_cmd('python app.py # default cmd') == 'python app.py'


class TestSplitDockerfileStages:
    def test_single_stage(self):
        stages = _split_dockerfile_stages('FROM alpine\nRUN echo hi\n')
        assert len(stages) == 1

    def test_multi_stage(self):
        stages = _split_dockerfile_stages('FROM a\nRUN 1\nFROM b\nRUN 2\n')
        assert len(stages) == 2
        assert 'RUN 2' in stages[-1]


# ── compose parsing ───────────────────────────────────────────────────────


class TestParseCompose:
    def test_environment_as_mapping(self):
        text = (
            'services:\n'
            '  web:\n'
            '    image: foo\n'
            '    environment:\n'
            '      PORT: 8080\n'
            '      DEBUG: true\n'
        )
        env, _ = _parse_compose(text)
        assert env == {'PORT': '8080', 'DEBUG': 'True'}

    def test_environment_as_list(self):
        text = (
            'services:\n'
            '  web:\n'
            '    image: foo\n'
            '    environment:\n'
            '      - PORT=8080\n'
            '      - DEBUG=1\n'
        )
        env, _ = _parse_compose(text)
        assert env == {'PORT': '8080', 'DEBUG': '1'}

    def test_ports_string_and_int_forms(self):
        text = (
            'services:\n'
            '  web:\n'
            '    image: foo\n'
            '    ports:\n'
            '      - "8080:80"\n'
            '      - "127.0.0.1:9090:90"\n'
            '      - 3000\n'
            '      - "53:53/udp"\n'
        )
        _, ports = _parse_compose(text)
        assert ports == [80, 90, 3000, 53]

    def test_malformed_yaml_returns_empty(self):
        assert _parse_compose(': :::') == ({}, [])

    def test_no_services_returns_empty(self):
        assert _parse_compose('foo: bar') == ({}, [])


# ── analyse_workload integration ──────────────────────────────────────────


class TestAnalyseWorkloadPython:
    def test_flask_detection_by_package_name(self, tmp_path: Path):
        (tmp_path / 'requirements.txt').write_text('flask==2.3.0\nrequests\n')
        out = analyse_workload(tmp_path, 'my-charm')
        assert out.language == 'python'
        assert out.framework == 'flask'
        assert out.port == 5000
        assert 'flask' in out.command
        assert out.is_web_app

    def test_flask_login_does_not_match_flask(self, tmp_path: Path):
        """Substring 'flask' inside Flask-Login must not flag the framework."""
        (tmp_path / 'requirements.txt').write_text('Flask-Login==0.6\nsqlalchemy\n')
        out = analyse_workload(tmp_path, 'my-charm')
        assert out.framework == 'none'

    def test_django_by_pyproject(self, tmp_path: Path):
        (tmp_path / 'pyproject.toml').write_text(
            '[project]\nname = "djangoapp"\ndependencies = ["Django>=4.2", "psycopg"]\n'
        )
        out = analyse_workload(tmp_path, 'my-charm')
        assert out.framework == 'django'
        assert out.name == 'djangoapp'
        assert out.port == 8000

    def test_fastapi_detection(self, tmp_path: Path):
        (tmp_path / 'requirements.txt').write_text('fastapi==0.110\nuvicorn\n')
        out = analyse_workload(tmp_path, 'my-charm')
        assert out.framework == 'fastapi'
        assert 'uvicorn' in out.command


class TestAnalyseWorkloadNode:
    def test_express(self, tmp_path: Path):
        (tmp_path / 'package.json').write_text(
            '{"name": "myapp", "description": "a thing", '
            '"dependencies": {"express": "^4"}, '
            '"scripts": {"start": "node index.js"}}'
        )
        out = analyse_workload(tmp_path, 'my-charm')
        assert out.language == 'nodejs'
        assert out.framework == 'express'
        assert out.name == 'myapp'
        assert out.summary == 'a thing'
        assert out.command == 'npm start'

    def test_dotenv_picked_up(self, tmp_path: Path):
        (tmp_path / 'package.json').write_text(
            '{"name": "myapp", "dependencies": {"fastify": "^4"}}'
        )
        (tmp_path / '.env.example').write_text('PORT=3001\nDATABASE_URL=postgres://x\n')
        out = analyse_workload(tmp_path, 'my-charm')
        assert out.env_vars['PORT'] == '3001'
        assert out.port == 3001
        assert out.needs_database


class TestAnalyseWorkloadGo:
    def test_go_module_name_and_command(self, tmp_path: Path):
        (tmp_path / 'go.mod').write_text('module github.com/example/awesome-thing\n\ngo 1.22\n')
        out = analyse_workload(tmp_path, 'my-charm')
        assert out.language == 'go'
        assert out.name == 'awesome-thing'
        assert out.command == '/awesome-thing'

    def test_gin_marks_web_app(self, tmp_path: Path):
        (tmp_path / 'go.mod').write_text(
            'module example.com/foo\nrequire github.com/gin-gonic/gin v1\n'
        )
        out = analyse_workload(tmp_path, 'my-charm')
        assert out.is_web_app


class TestAnalyseWorkloadDocker:
    def test_dockerfile_cmd_json_array(self, tmp_path: Path):
        (tmp_path / 'Dockerfile').write_text(
            'FROM python:3.12\nEXPOSE 8000\nCMD ["python", "manage.py", "runserver"]\n'
        )
        out = analyse_workload(tmp_path, 'my-charm')
        assert out.has_dockerfile
        assert out.docker_expose_ports == [8000]
        assert out.command == 'python manage.py runserver'
        assert out.port == 8000

    def test_multistage_dockerfile_uses_final(self, tmp_path: Path):
        (tmp_path / 'Dockerfile').write_text(
            'FROM golang AS build\nEXPOSE 9999\nCMD ["build"]\n'
            'FROM alpine\nEXPOSE 8080\nCMD ["./run"]\n'
        )
        out = analyse_workload(tmp_path, 'my-charm')
        assert out.docker_expose_ports == [8080]
        assert out.command == './run'

    def test_compose_env_and_ports(self, tmp_path: Path):
        (tmp_path / 'docker-compose.yml').write_text(
            'services:\n'
            '  web:\n'
            '    image: foo\n'
            '    environment:\n'
            '      REDIS_URL: redis://r\n'
            '    ports:\n'
            '      - "8080:80"\n'
        )
        out = analyse_workload(tmp_path, 'my-charm')
        assert out.has_docker_compose
        assert out.env_vars.get('REDIS_URL') == 'redis://r'
        assert 80 in out.docker_expose_ports
        assert out.needs_cache


class TestAnalyseWorkloadFallbacks:
    def test_empty_directory(self, tmp_path: Path):
        out = analyse_workload(tmp_path, 'my-charm')
        assert out.name == 'my-charm'
        assert out.language == 'unknown'
        assert out.summary == 'Charm for my-charm'
        assert out.command == '/bin/sh'

    def test_readme_summary_used_when_no_other_source(self, tmp_path: Path):
        (tmp_path / 'README.md').write_text('# Awesome Thing\n\nA description.\n')
        out = analyse_workload(tmp_path, 'my-charm')
        assert out.summary == 'Awesome Thing'

    def test_postgres_signal(self, tmp_path: Path):
        (tmp_path / 'Dockerfile').write_text('FROM x\nENV POSTGRES_HOST=db\n')
        out = analyse_workload(tmp_path, 'my-charm')
        assert out.has_postgres


@pytest.mark.parametrize(
    'analysis,expected_truthy',
    [
        (WorkloadAnalysis(name='x'), False),
        (WorkloadAnalysis(name='x', is_web_app=True), True),
    ],
)
def test_workload_analysis_dataclass(analysis: WorkloadAnalysis, expected_truthy: bool):
    assert analysis.is_web_app is expected_truthy
