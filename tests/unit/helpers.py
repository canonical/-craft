"""Helper mocks and fixtures for dashcraft unit tests."""

from __future__ import annotations

import subprocess
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def make_config(
    content: str,
    *,
    dir_path: Path | None = None,
) -> Generator[Path]:
    """Create a temporary directory with a dashcraft.yaml inside.

    Yields the path to the config file. Cleans up the directory on exit.
    """
    if dir_path is None:
        import tempfile

        tmp = Path(tempfile.mkdtemp(prefix='dashcraft-test-'))
    else:
        tmp = dir_path
        tmp.mkdir(parents=True, exist_ok=True)

    config_file = tmp / 'dashcraft.yaml'
    config_file.write_text(content)
    try:
        yield config_file
    finally:
        if dir_path is None:
            import shutil

            shutil.rmtree(tmp, ignore_errors=True)


MINIMAL_CONFIG = """\
name: my-charm
summary: A test charm
description: For testing purposes
type: charm

parts:
  charm:
    plugin: -craft
    upstream: https://github.com/example/repo.git
    model: gpt-4
"""


class SubprocessMock:
    """Mock for subprocess.run that records calls and returns configured output."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self._responses: dict[tuple[str, ...], tuple[int, str, str]] = {}
        self._side_effect: Exception | None = None

    def handle(
        self, args: list[str], *, returncode: int = 0, stdout: str = '', stderr: str = ''
    ) -> None:
        """Register a response for the given command args."""
        self._responses[tuple(args)] = (returncode, stdout, stderr)

    def set_side_effect(self, exc: Exception) -> None:
        """Raise an exception on the next call."""
        self._side_effect = exc

    def __call__(
        self,
        args: list[str],
        check: bool = False,
        capture_output: bool = False,
        text: bool = False,
        **kwargs,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(list(args))
        if self._side_effect is not None:
            raise self._side_effect

        key = tuple(args)
        assert key in self._responses, f'unhandled command: {args}'
        returncode, stdout, stderr = self._responses[key]
        if returncode != 0:
            raise subprocess.CalledProcessError(
                returncode=returncode, cmd=args, output=stdout, stderr=stderr
            )
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr=stderr)
