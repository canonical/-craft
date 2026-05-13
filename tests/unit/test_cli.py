"""Tests for dashcraft.cli module."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from dashcraft.cli import CONFIG_FILENAME, _build_parser, main
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

    def test_config_filename(self) -> None:
        assert CONFIG_FILENAME == 'dashcraft.yaml'

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

            monkeypatch.setattr('subprocess.run', fake_run)
            monkeypatch.setattr(
                'shutil.which',
                lambda cmd: '/usr/bin/git' if cmd == 'git' else None,
            )
            monkeypatch.setattr('quickpack.pack.quick_pack', lambda cwd: Path('result.charm'))

            with patch.object(
                sys, 'argv', ['dashcraft', '--project-dir', str(project_dir), 'pack']
            ):
                ret = main()

        assert ret == 0
        captured = capsys.readouterr()
        assert 'my-charm' in captured.out
        assert 'Cloned upstream to:' in captured.out
        assert 'Upstream source ready' in captured.out
        assert 'Running lint checks' in captured.out
        assert 'Running unit tests' in captured.out

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

            monkeypatch.setattr('subprocess.run', fake_run)
            monkeypatch.setattr(
                'shutil.which',
                lambda cmd: '/usr/bin/git' if cmd == 'git' else None,
            )
            monkeypatch.setattr('quickpack.pack.quick_pack', lambda cwd: Path('result.charm'))

            with patch.object(
                sys,
                'argv',
                ['dashcraft', '--project-dir', str(project_dir), 'pack', '--keep-source'],
            ):
                ret = main()

        assert ret == 0
        captured = capsys.readouterr()
        assert 'my-charm' in captured.out
        assert 'directory will not be cleaned up' in captured.out
        assert 'Upstream source ready' in captured.out
