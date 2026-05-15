"""Clone upstream workload source code into a target directory."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def clone_upstream_persistent(
    upstream_url: str, *, dest: Path | str | None = None, depth: int = 1
) -> Path:
    """Clone an upstream git repository into a directory.

    The cloned directory is NOT cleaned up automatically — the caller
    owns it.

    Args:
        upstream_url: Git URL of the upstream repository to clone.
        dest: Destination directory. If None, a temp directory is created.
        depth: Git clone depth (default 1 for shallow clone).

    Returns:
        Path to the cloned repository root.

    Raises:
        CloneError: If the git clone operation fails.
    """
    if dest is None:
        dest = Path(tempfile.mkdtemp(prefix='dashcraft-upstream-'))
    else:
        dest = Path(dest)
        dest.mkdir(parents=True, exist_ok=True)

    _git_clone(upstream_url, dest, depth=depth)
    return dest


def _ensure_git_available() -> None:
    """Check that git is installed and accessible."""
    if not shutil.which('git'):
        raise CloneError('git is not installed or not found in PATH')


def _git_clone(url: str, dest: Path, *, depth: int = 1) -> None:
    """Execute git clone with the given parameters."""
    _ensure_git_available()

    cmd = ['git', 'clone', '--depth', str(depth)]
    cmd.append(url)
    cmd.append(str(dest))

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise CloneError(
            f"Failed to clone '{url}': {e.stderr.strip()}"
            if e.stderr
            else f"Failed to clone '{url}'"
        ) from e


class CloneError(Exception):
    """Raised when cloning an upstream repository fails."""

    pass
