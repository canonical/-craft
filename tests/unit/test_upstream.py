"""Tests for dashcraft.upstream module."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from dashcraft.upstream import (
    CloneError,
    _ensure_git_available,
    _git_clone,
    clone_upstream_persistent,
)

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


class TestCloneUpstreamPersistent:
    def test_writes_to_supplied_dest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        dest = tmp_path / 'clone-here'
        sp = helpers.SubprocessMock()
        sp.handle(['git', 'clone', '--depth', '1', 'https://example.com', str(dest)])
        monkeypatch.setattr('subprocess.run', sp)
        out = clone_upstream_persistent('https://example.com', dest=dest)
        assert out == dest
        assert dest.exists()  # caller owns it; not removed

    def test_creates_temp_dir_when_dest_omitted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        known = tmp_path / 'auto-temp'
        known.mkdir()
        monkeypatch.setattr('tempfile.mkdtemp', lambda prefix='': str(known))

        def fake_run(args: list[str], **_kw: object) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout='', stderr='')

        monkeypatch.setattr('subprocess.run', fake_run)
        out = clone_upstream_persistent('https://example.com')
        assert out == known
        assert known.exists()  # caller owns it
