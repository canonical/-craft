"""Tests for dashcraft.cli module."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from dashcraft.cli import _build_parser, _check_pi_installed, main
from tests.unit.helpers import MINIMAL_CONFIG, make_config


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
    def test_pack_succeeds(self, capsys, monkeypatch) -> None:
        with make_config(MINIMAL_CONFIG) as config_path:
            project_dir = config_path.parent

            def fake_run(args, **kwargs):
                if args and args[0] == 'git' and 'clone' in args:
                    return subprocess.CompletedProcess(
                        args=args, returncode=0, stdout='', stderr=''
                    )
                return subprocess.CompletedProcess(args=args, returncode=0, stdout='', stderr='')

            monkeypatch.setenv('GEMINI_API_KEY', 'fake-key')
            monkeypatch.setattr('subprocess.run', fake_run)
            monkeypatch.setattr(
                'shutil.which',
                lambda cmd: (
                    '/usr/bin/git'
                    if cmd == 'git'
                    else '/usr/local/bin/pi'
                    if cmd == 'pi'
                    else None
                ),
            )
            # Mock generate_charm to avoid starting a real pi subprocess.
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
        assert 'Charm generation complete' in captured.err
        # .tmp should be cleaned up (no --keep-source)
        assert not (project_dir / '.tmp').exists()

    def test_pack_fails_on_missing_config(self, capsys) -> None:
        with patch.object(sys, 'argv', ['dashcraft', '--project-dir', '/nonexistent', 'pack']):
            ret = main()

        assert ret == 1
        captured = capsys.readouterr()
        assert 'not found' in captured.err

    def test_pack_keep_source(self, capsys, monkeypatch) -> None:
        with make_config(MINIMAL_CONFIG) as config_path:
            project_dir = config_path.parent

            def fake_run(args, **kwargs):
                if args and args[0] == 'git' and 'clone' in args:
                    return subprocess.CompletedProcess(
                        args=args, returncode=0, stdout='', stderr=''
                    )
                return subprocess.CompletedProcess(args=args, returncode=0, stdout='', stderr='')

            monkeypatch.setenv('GEMINI_API_KEY', 'fake-key')
            monkeypatch.setattr('subprocess.run', fake_run)
            monkeypatch.setattr(
                'shutil.which',
                lambda cmd: (
                    '/usr/bin/git'
                    if cmd == 'git'
                    else '/usr/local/bin/pi'
                    if cmd == 'pi'
                    else None
                ),
            )
            # Mock generate_charm to avoid starting a real pi subprocess.
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

            # Check inside the context manager since make_config cleans up
            assert ret == 0
            captured = capsys.readouterr()
            assert 'my-charm' in captured.out
            assert 'will not be cleaned up' in captured.out
            assert 'Charm generation complete' in captured.err
            # .tmp should be preserved (--keep-source)
            assert (project_dir / '.tmp').exists()
            assert (project_dir / '.tmp' / 'upstream').exists()
            assert (project_dir / '.tmp' / 'charm').exists()

    def test_pack_handles_generate_charm_error(self, capsys, monkeypatch) -> None:
        """generate_charm raises RuntimeError; pack returns 1."""
        with make_config(MINIMAL_CONFIG) as config_path:
            project_dir = config_path.parent

            def fake_run(args, **kwargs):
                return subprocess.CompletedProcess(args=args, returncode=0, stdout='', stderr='')

            monkeypatch.setenv('GEMINI_API_KEY', 'fake-key')
            monkeypatch.setattr('subprocess.run', fake_run)
            monkeypatch.setattr(
                'shutil.which',
                lambda cmd: (
                    '/usr/bin/git'
                    if cmd == 'git'
                    else '/usr/local/bin/pi'
                    if cmd == 'pi'
                    else None
                ),
            )
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
        # .tmp should be cleaned up on error
        assert not (project_dir / '.tmp').exists()

    def test_pack_without_api_key_skips_generation(self, capsys, monkeypatch) -> None:
        """When no API key is configured, pi check fails and generation is skipped."""
        with make_config(MINIMAL_CONFIG) as config_path:
            project_dir = config_path.parent

            known_keys = [
                'ANTHROPIC_API_KEY',
                'OPENAI_API_KEY',
                'GEMINI_API_KEY',
                'AZURE_OPENAI_API_KEY',
                'DEEPSEEK_API_KEY',
                'GROQ_API_KEY',
                'MISTRAL_API_KEY',
                'OPENROUTER_API_KEY',
                'FIREWORKS_API_KEY',
            ]
            for key in known_keys:
                monkeypatch.delenv(key, raising=False)

            def fake_run(args, **kwargs):
                return subprocess.CompletedProcess(args=args, returncode=0, stdout='', stderr='')

            monkeypatch.setattr('subprocess.run', fake_run)
            monkeypatch.setattr(
                'shutil.which',
                lambda cmd: (
                    '/usr/bin/git'
                    if cmd == 'git'
                    else '/usr/local/bin/pi'
                    if cmd == 'pi'
                    else None
                ),
            )

            with patch.object(
                sys, 'argv', ['dashcraft', '--project-dir', str(project_dir), 'pack']
            ):
                ret = main()

        assert ret == 1
        captured = capsys.readouterr()
        assert 'Skipping AI charm generation' in captured.err
        # .tmp should be cleaned up even when generation is skipped
        assert not (project_dir / '.tmp').exists()


class TestCheckPi:
    def test_returns_error_when_pi_not_found(self, monkeypatch) -> None:
        monkeypatch.setattr('shutil.which', lambda cmd: None)
        assert _check_pi_installed() == 1

    def test_returns_error_when_no_api_key(self, monkeypatch) -> None:
        known_keys = [
            'ANTHROPIC_API_KEY',
            'OPENAI_API_KEY',
            'GEMINI_API_KEY',
            'AZURE_OPENAI_API_KEY',
            'DEEPSEEK_API_KEY',
            'GROQ_API_KEY',
            'MISTRAL_API_KEY',
            'OPENROUTER_API_KEY',
            'FIREWORKS_API_KEY',
        ]
        for key in known_keys:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setattr(
            'shutil.which', lambda cmd: '/usr/local/bin/pi' if cmd == 'pi' else None
        )
        assert _check_pi_installed() == 1

    def test_succeeds_with_pi_and_api_key(self, monkeypatch) -> None:
        monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
        monkeypatch.setattr(
            'shutil.which', lambda cmd: '/usr/local/bin/pi' if cmd == 'pi' else None
        )
        assert _check_pi_installed() == 0


class TestEnsureCleanTmp:
    def test_creates_new_tmp_dir(self, tmp_path: Path) -> None:
        from dashcraft.cli import TMP_DIR_NAME, _ensure_clean_tmp

        tmp_dir = tmp_path / TMP_DIR_NAME
        _ensure_clean_tmp(tmp_dir)
        assert tmp_dir.exists()
        assert tmp_dir.is_dir()

    def test_removes_existing_contents(self, tmp_path: Path) -> None:
        from dashcraft.cli import TMP_DIR_NAME, _ensure_clean_tmp

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

        tmp_dir = tmp_path / '.tmp'
        tmp_dir.mkdir()
        (tmp_dir / 'stuff').write_text('data')

        _cleanup_tmp(tmp_dir, keep=False)
        assert not tmp_dir.exists()

    def test_preserves_tmp_when_keep_is_true(self, tmp_path: Path, capsys) -> None:
        from dashcraft.cli import _cleanup_tmp

        tmp_dir = tmp_path / '.tmp'
        tmp_dir.mkdir()

        _cleanup_tmp(tmp_dir, keep=True)
        assert tmp_dir.exists()
        captured = capsys.readouterr()
        assert 'will not be cleaned up' in captured.out
