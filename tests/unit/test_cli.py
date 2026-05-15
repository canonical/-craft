"""Tests for dashcraft.cli module."""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from dashcraft.cli import KNOWN_API_KEYS, TMP_DIR_NAME, _build_parser, _check_pi_installed, main
from tests.unit.helpers import MINIMAL_CONFIG, make_config

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


_DEFAULT_TOOL_PATHS = {
    'git': '/usr/bin/git',
    'quickpack': '/usr/local/bin/quickpack',
    'pi': '/usr/local/bin/pi',
    'uv': '/usr/local/bin/uv',
}


@pytest.fixture
def fake_tools(monkeypatch: pytest.MonkeyPatch) -> Callable[..., None]:
    """Patch shutil.which to find the named tools (default: git/quickpack/pi/uv).

    Call ``fake_tools()`` to install defaults, or pass an explicit dict
    (e.g. ``fake_tools({'git': '/usr/bin/git', 'pi': '/usr/local/bin/pi'})``)
    to restrict the set of "installed" tools.
    """

    def _install(paths: dict[str, str] | None = None) -> None:
        resolved = _DEFAULT_TOOL_PATHS if paths is None else paths

        def _which(cmd: str) -> str | None:
            return resolved.get(cmd)

        monkeypatch.setattr('shutil.which', _which)

    return _install


@pytest.fixture
def fake_subprocess_run(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch subprocess.run to always succeed."""

    def _run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=args, returncode=0, stdout='', stderr='')

    monkeypatch.setattr('subprocess.run', _run)


@pytest.fixture
def clear_api_keys(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Remove every known API-key env var for the duration of the test."""
    for key in KNOWN_API_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildParser:
    def test_parser_has_project_dir(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(['--project-dir', '/foo/bar'])
        assert args.project_dir == Path('/foo/bar')

    def test_project_dir_defaults_to_cwd(self) -> None:
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.project_dir == Path.cwd()

    def test_keep_source_flag(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(['pack', '--keep-source'])
        assert args.keep_source is True

    def test_keep_source_defaults_to_false(self) -> None:
        parser = _build_parser()
        args = parser.parse_args(['pack'])
        assert args.keep_source is False


class TestMain:
    def test_no_subcommand_prints_help_exit_zero(self, capsys) -> None:
        with patch.object(sys, 'argv', ['dashcraft']):
            ret = main()
        assert ret == 0
        captured = capsys.readouterr()
        assert 'pack' in captured.out

    def test_pack_succeeds(
        self,
        capsys,
        monkeypatch: pytest.MonkeyPatch,
        fake_tools: Callable[..., None],
        fake_subprocess_run: None,
    ) -> None:
        del fake_subprocess_run  # used for its side effect (monkeypatch)
        with make_config(MINIMAL_CONFIG) as config_path:
            project_dir = config_path.parent
            monkeypatch.setenv('GEMINI_API_KEY', 'fake-key')
            fake_tools()
            monkeypatch.setattr(
                'dashcraft.cli.generate_charm',
                lambda **_kw: {'type': 'response', 'success': True},
            )
            with patch.object(
                sys, 'argv', ['dashcraft', '--project-dir', str(project_dir), 'pack']
            ):
                ret = main()

        assert ret == 0
        captured = capsys.readouterr()
        assert 'my-charm' in captured.out
        assert 'Cloned upstream to:' in captured.out
        assert 'Upstream source ready at:' in captured.out
        assert 'Charm generation complete' in captured.err
        # working dir should be cleaned up (no --keep-source)
        assert not (project_dir / TMP_DIR_NAME).exists()

    def test_pack_fails_on_missing_config(self, capsys) -> None:
        with patch.object(sys, 'argv', ['dashcraft', '--project-dir', '/nonexistent', 'pack']):
            ret = main()

        assert ret == 1
        captured = capsys.readouterr()
        assert 'not found' in captured.err

    def test_pack_keep_source(
        self,
        capsys,
        monkeypatch: pytest.MonkeyPatch,
        fake_tools: Callable[..., None],
        fake_subprocess_run: None,
    ) -> None:
        del fake_subprocess_run
        with make_config(MINIMAL_CONFIG) as config_path:
            project_dir = config_path.parent
            monkeypatch.setenv('GEMINI_API_KEY', 'fake-key')
            fake_tools()
            monkeypatch.setattr(
                'dashcraft.cli.generate_charm',
                lambda **_kw: {'type': 'response', 'success': True},
            )
            with patch.object(
                sys,
                'argv',
                ['dashcraft', '--project-dir', str(project_dir), 'pack', '--keep-source'],
            ):
                ret = main()

            assert ret == 0
            captured = capsys.readouterr()
            assert 'my-charm' in captured.out
            assert 'will not be cleaned up' in captured.out
            assert 'Charm generation complete' in captured.err
            # working dir should be preserved (--keep-source)
            tmp = project_dir / TMP_DIR_NAME
            assert tmp.exists()
            assert (tmp / 'upstream').exists()
            assert (tmp / 'charm').exists()

    def test_pack_handles_generate_charm_error(
        self,
        capsys,
        monkeypatch: pytest.MonkeyPatch,
        fake_tools: Callable[..., None],
        fake_subprocess_run: None,
    ) -> None:
        """generate_charm raises RuntimeError; pack returns 1."""
        del fake_subprocess_run
        with make_config(MINIMAL_CONFIG) as config_path:
            project_dir = config_path.parent
            monkeypatch.setenv('GEMINI_API_KEY', 'fake-key')
            fake_tools()
            monkeypatch.setattr(
                'dashcraft.cli.generate_charm',
                lambda **_kw: (_ for _ in ()).throw(RuntimeError('test boom')),
            )

            with patch.object(
                sys, 'argv', ['dashcraft', '--project-dir', str(project_dir), 'pack']
            ):
                ret = main()

        assert ret == 1
        captured = capsys.readouterr()
        assert 'AI charm generation failed' in captured.err
        # working dir should be cleaned up on error
        assert not (project_dir / TMP_DIR_NAME).exists()

    def test_pack_without_api_key_skips_generation(
        self,
        capsys,
        fake_tools: Callable[..., None],
        fake_subprocess_run: None,
        clear_api_keys: None,
    ) -> None:
        """When no API key is configured, pi check fails and generation is skipped."""
        del fake_subprocess_run, clear_api_keys
        with make_config(MINIMAL_CONFIG) as config_path:
            project_dir = config_path.parent
            # Pretend pi & uv & git are installed, but no quickpack — we should
            # bail out at the API-key check before that matters.
            fake_tools()

            with patch.object(
                sys, 'argv', ['dashcraft', '--project-dir', str(project_dir), 'pack']
            ):
                ret = main()

        assert ret == 1
        captured = capsys.readouterr()
        assert 'Skipping AI charm generation' in captured.err
        # working dir should be cleaned up even when generation is skipped
        assert not (project_dir / TMP_DIR_NAME).exists()


class TestCheckPi:
    def test_returns_error_when_pi_not_found(
        self, fake_tools: Callable[..., None], clear_api_keys: None
    ) -> None:
        del clear_api_keys
        fake_tools({})  # nothing installed
        assert _check_pi_installed() == 1

    def test_returns_error_when_no_api_key(
        self,
        fake_tools: Callable[..., None],
        clear_api_keys: None,
    ) -> None:
        del clear_api_keys
        fake_tools({'pi': '/usr/local/bin/pi'})
        assert _check_pi_installed() == 1

    def test_succeeds_with_pi_and_api_key(
        self, monkeypatch: pytest.MonkeyPatch, fake_tools: Callable[..., None]
    ) -> None:
        monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
        fake_tools({'pi': '/usr/local/bin/pi'})
        assert _check_pi_installed() == 0


class TestEnsureCleanTmp:
    def test_creates_new_tmp_dir(self, tmp_path: Path) -> None:
        from dashcraft.cli import _ensure_clean_tmp

        tmp_dir = tmp_path / TMP_DIR_NAME
        _ensure_clean_tmp(tmp_dir)
        assert tmp_dir.exists()
        assert tmp_dir.is_dir()

    def test_removes_existing_contents(self, tmp_path: Path) -> None:
        from dashcraft.cli import _ensure_clean_tmp

        tmp_dir = tmp_path / TMP_DIR_NAME
        tmp_dir.mkdir()
        (tmp_dir / 'old-file').write_text('stale')
        (tmp_dir / 'old-subdir').mkdir()

        _ensure_clean_tmp(tmp_dir)

        assert tmp_dir.exists()
        assert not (tmp_dir / 'old-file').exists()
        assert not (tmp_dir / 'old-subdir').exists()


class TestCleanupTmp:
    def test_removes_tmp_when_keep_is_false(self, tmp_path: Path) -> None:
        from dashcraft.cli import _cleanup_tmp

        tmp_dir = tmp_path / TMP_DIR_NAME
        tmp_dir.mkdir()
        (tmp_dir / 'stuff').write_text('data')

        _cleanup_tmp(tmp_dir, keep=False)
        assert not tmp_dir.exists()

    def test_preserves_tmp_when_keep_is_true(self, tmp_path: Path, capsys) -> None:
        from dashcraft.cli import _cleanup_tmp

        tmp_dir = tmp_path / TMP_DIR_NAME
        tmp_dir.mkdir()

        _cleanup_tmp(tmp_dir, keep=True)
        assert tmp_dir.exists()
        captured = capsys.readouterr()
        assert 'will not be cleaned up' in captured.out


class TestFindCharmFile:
    def test_returns_none_when_no_charm_file(self, tmp_path: Path) -> None:
        from dashcraft.cli import _find_charm_file

        result = _find_charm_file(tmp_path)
        assert result is None

    def test_finds_single_charm_file(self, tmp_path: Path) -> None:
        from dashcraft.cli import _find_charm_file

        charm_file = tmp_path / 'my-charm.charm'
        charm_file.write_text('fake-charm')

        result = _find_charm_file(tmp_path)
        assert result == charm_file

    def test_returns_most_recent_charm_file(self, tmp_path: Path) -> None:
        import time

        from dashcraft.cli import _find_charm_file

        older = tmp_path / 'older.charm'
        older.write_text('old')
        time.sleep(0.01)
        newer = tmp_path / 'newer.charm'
        newer.write_text('new')

        result = _find_charm_file(tmp_path)
        assert result == newer


class TestBuildDeployCommand:
    def test_builds_with_no_resources(self, tmp_path: Path) -> None:
        from dashcraft.cli import _build_deploy_command

        charm_dir = tmp_path / 'charm'
        charm_dir.mkdir()
        charm_file = tmp_path / 'my-charm.charm'
        charm_file.write_text('fake')

        cmd = _build_deploy_command(charm_dir, charm_file, tmp_path)
        assert cmd == f'juju deploy ./{charm_file.name}'

    def test_builds_with_resources(self, tmp_path: Path) -> None:
        from dashcraft.cli import _build_deploy_command

        charm_dir = tmp_path / 'charm'
        charm_dir.mkdir()
        charmcraft_yaml = charm_dir / 'charmcraft.yaml'
        charmcraft_yaml.write_text(
            'resources:\n'
            '  workload-image:\n'
            '    type: oci-image\n'
            '    description: OCI image\n'
            '    upstream-source: myimage:latest\n'
        )
        charm_file = tmp_path / 'my-charm.charm'
        charm_file.write_text('fake')

        cmd = _build_deploy_command(charm_dir, charm_file, tmp_path)
        assert 'juju deploy' in cmd
        assert '--resource workload-image=myimage:latest' in cmd

    def test_handles_missing_charmcraft_yaml(self, tmp_path: Path) -> None:
        from dashcraft.cli import _build_deploy_command

        charm_dir = tmp_path / 'charm'
        charm_dir.mkdir()
        charm_file = tmp_path / 'my-charm.charm'
        charm_file.write_text('fake')

        cmd = _build_deploy_command(charm_dir, charm_file, tmp_path)
        assert cmd == f'juju deploy ./{charm_file.name}'

    def test_uses_relative_path_when_outside_project_dir(self, tmp_path: Path) -> None:
        from dashcraft.cli import _build_deploy_command

        charm_dir = tmp_path / TMP_DIR_NAME / 'charm'
        charm_dir.mkdir(parents=True)
        charm_file = charm_dir / 'my-charm.charm'
        charm_file.write_text('fake')
        project_dir = tmp_path

        cmd = _build_deploy_command(charm_dir, charm_file, project_dir)
        assert f'juju deploy ./{TMP_DIR_NAME}/charm/my-charm.charm' in cmd
