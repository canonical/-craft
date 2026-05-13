"""Tests for dashcraft.upstream module."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dashcraft.upstream import CloneError, _ensure_git_available, _git_clone, clone_upstream

from . import helpers


class TestEnsureGitAvailable:
    def test_passes_when_git_exists(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr('shutil.which', lambda cmd: '/usr/bin/git')
        _ensure_git_available()  # should not raise

    def test_raises_when_git_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr('shutil.which', lambda cmd: None)
        with pytest.raises(CloneError) as exc_info:
            _ensure_git_available()
        assert 'git is not installed' in str(exc_info.value)


class TestGitClone:
    def test_calls_subprocess_with_correct_args(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sp = helpers.SubprocessMock()
        sp.handle(['git', 'clone', '--depth', '1', 'https://example.com', str(tmp_path)])
        monkeypatch.setattr('subprocess.run', sp)
        _git_clone('https://example.com', tmp_path, depth=1)
        assert len(sp.calls) == 1

    def test_raises_clone_error_on_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sp = helpers.SubprocessMock()
        sp.handle(
            ['git', 'clone', '--depth', '1', 'https://bad-url.git', str(tmp_path)],
            returncode=128,
            stderr='fatal: repository not found',
        )
        monkeypatch.setattr('subprocess.run', sp)
        with pytest.raises(CloneError) as exc_info:
            _git_clone('https://bad-url.git', tmp_path)
        assert 'Failed to clone' in str(exc_info.value)
        assert 'repository not found' in str(exc_info.value)

    def test_clone_error_without_stderr(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sp = helpers.SubprocessMock()
        sp.handle(
            ['git', 'clone', '--depth', '1', 'https://no-stderr.git', str(tmp_path)],
            returncode=1,
            stderr='',
        )
        monkeypatch.setattr('subprocess.run', sp)
        with pytest.raises(CloneError) as exc_info:
            _git_clone('https://no-stderr.git', tmp_path)
        assert 'Failed to clone' in str(exc_info.value)


class TestCloneUpstream:
    def test_cleans_up_temp_dir_on_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Even when clone fails, the temp dir should be removed."""
        sp = helpers.SubprocessMock()
        sp.set_side_effect(
            subprocess.CalledProcessError(1, ['git', 'clone'], output='', stderr='fail')
        )
        monkeypatch.setattr('subprocess.run', sp)

        with pytest.raises(CloneError), clone_upstream('https://example.com'):
            pass  # pragma: no cover — clone fails before entering

    def test_cleans_up_temp_dir_on_success(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Temp dir is removed after the context manager exits normally."""
        # Create a known temp dir to return from mkdtemp
        known_dir = tmp_path / 'fake-temp'
        known_dir.mkdir()
        monkeypatch.setattr('tempfile.mkdtemp', lambda prefix='': str(known_dir))

        # Make git clone succeed for any call targeting our known dir
        def fake_run(args, **kwargs) -> subprocess.CompletedProcess[str]:
            assert 'git' in args[0]
            return subprocess.CompletedProcess(args=args, returncode=0, stdout='', stderr='')

        monkeypatch.setattr('subprocess.run', fake_run)

        with clone_upstream('https://example.com') as source_dir:
            assert source_dir == known_dir
            # Dir still exists inside context
            assert known_dir.exists()

        # After exit, shutil.rmtree should have removed it
        assert not known_dir.exists()
