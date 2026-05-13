from __future__ import annotations

from collections.abc import Generator

import pytest

from . import helpers

SubprocessMock = helpers.SubprocessMock


@pytest.fixture
def subprocess_mock(monkeypatch: pytest.MonkeyPatch) -> Generator[helpers.SubprocessMock]:
    """Patch subprocess.run with a SubprocessMock."""
    mock = helpers.SubprocessMock()
    monkeypatch.setattr('subprocess.run', mock)
    yield mock
