"""Manage a pi RPC server subprocess for AI-driven charm generation.

Starts ``pi --mode rpc`` as a subprocess, communicates via the JSONL
protocol on stdin/stdout, and shuts it down when finished.  Provides
high-level functions used by the ``pack`` command to invoke the
juju-charm extension against a cloned workload and scaffolded charm
directory.

See ``docs/rpc.md`` in the pi source tree for the full protocol.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Low-level subprocess manager
# ---------------------------------------------------------------------------

_EXTENSION_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / '..'
    / '.pi'
    / 'extensions'
    / 'juju-charm'
    / 'index.ts'
)


class PiRpcServer:
    """Manage a pi RPC subprocess.

    Use :meth:`start` to launch, :meth:`send` to issue commands, and
    :meth:`shutdown` (or use as a context manager) to clean up.
    """

    def __init__(
        self,
        *,
        model: str = '',
        extension: str | None = None,
        work_dir: str | Path | None = None,
    ) -> None:
        """Initialise configuration for the RPC subprocess.

        Args:
            model: Pi model pattern (e.g. ``'gemini/gemini-2.5-flash'``).
                When empty, pi uses its default model selection.
            extension: Absolute path to a pi extension ``.ts`` file.
                Defaults to the shipped juju-charm extension.
            work_dir: Working directory for the pi subprocess.
                Defaults to the current working directory.
        """
        self._model = model
        self._extension = extension or str(_EXTENSION_PATH)
        self._work_dir = str(work_dir) if work_dir else str(Path.cwd())
        self._proc: subprocess.Popen[str] | None = None

    # -- context manager -----------------------------------------------------

    def __enter__(self) -> PiRpcServer:
        """Start the RPC server on entry."""
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        """Shut down the RPC server on exit."""
        self.shutdown()

    # -- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        """Launch the pi RPC subprocess (non-blocking)."""
        cmd = [
            'pi',
            '--mode',
            'rpc',
            '--no-session',
            '--no-skills',
            '--no-prompt-templates',
            '--no-context-files',
            '--no-themes',
            '--extension',
            self._extension,
            '--system-prompt',
            'You are an assistant that generates Juju charm code.',
        ]
        if self._model:
            cmd += ['--model', self._model]

        self._proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # line-buffered
            cwd=self._work_dir,
        )

    @property
    def is_running(self) -> bool:
        """Return ``True`` if the subprocess is alive."""
        return self._proc is not None and self._proc.poll() is None

    def shutdown(self) -> None:
        """Terminate the subprocess if still running."""
        if self._proc is None:
            return
        if self._proc.poll() is None:
            if self._proc.stdin:
                # Try graceful shutdown via the ``abort`` command and
                # then close stdin so the process can exit.
                try:
                    self._proc.stdin.write(json.dumps({'type': 'abort', 'id': 'shutdown'}) + '\n')
                    self._proc.stdin.flush()
                except BrokenPipeError, OSError:
                    pass
                self._proc.stdin.close()

            # Give the process a moment to exit gracefully.
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()

        if self._proc.stdout:
            self._proc.stdout.close()
        if self._proc.stderr:
            self._proc.stderr.close()
        self._proc = None

    # -- communication -------------------------------------------------------

    def send(self, command: dict[str, Any], *, timeout: float = 30.0) -> dict[str, Any]:
        """Send a single command and return its response.

        This writes *command* to stdin (JSONL), reads JSON lines from
        stdout until it finds a line with ``"type": "response"`` that
        matches the command's ``id`` (or just the first response if no
        ``id`` was set), and returns that response dict.

        Other lines (events, extension UI requests, etc.) are discarded
        for now; callers can use :meth:`events` for fine-grained
        processing.

        Args:
            command: The JSON-RPC-style command dict.
            timeout: Max seconds to wait for a matching response.

        Returns:
            The decoded response dict.

        Raises:
            RuntimeError: If the subprocess is not running or
                ``timeout`` expires without a matching response.
        """
        if not self.is_running or self._proc is None or self._proc.stdin is None:
            raise RuntimeError('Pi RPC server is not running')

        cmd_id = command.get('id')
        self._proc.stdin.write(json.dumps(command) + '\n')
        self._proc.stdin.flush()

        # Read stdout lines until we find a response with a matching id.
        events_seen: list[dict[str, Any]] = []
        if self._proc.stdout is None:
            raise RuntimeError('Pi RPC server stdout unavailable')

        deadline = time.monotonic() + timeout
        buffer = ''
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                # Process exited -- drain remaining buffer.
                remaining = self._proc.stdout.read()
                if remaining:
                    buffer += remaining
                break

            chunk = self._proc.stdout.readline()
            if not chunk:
                break
            buffer += chunk

            # Process complete lines.
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.rstrip('\r')
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                events_seen.append(msg)
                if msg.get('type') == 'response':
                    resp_id = msg.get('id')
                    # Match on id if the original command had one.
                    if cmd_id is None or resp_id == cmd_id:
                        return msg
                    # Got a response for a different id -- keep waiting.

        # Timeout or no matching response.
        raise RuntimeError(
            f'Timed out waiting for pi RPC response (id={cmd_id!r}). '
            f'Events seen: {len(events_seen)}'
        )

    def events(self) -> Iterator[dict[str, Any]]:
        """Yield JSON events from the pi subprocess stdout.

        Each line is parsed and yielded as a dict.  Stops when the
        subprocess exits and stdout is exhausted.
        """
        if self._proc is None or self._proc.stdout is None:
            return

        for raw_line in self._proc.stdout:
            line = raw_line.rstrip('\r\n')
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


# ---------------------------------------------------------------------------
# High-level helpers for dashcraft
# ---------------------------------------------------------------------------

_DEFAULT_MODEL = 'gemini/gemini-2.5-flash'


def _default_model_for_config(config_obj: Any) -> str:
    """Return the model to use, falling back to a sensible default.

    Args:
        config_obj: A :class:`~.Config` loaded from ``dashcraft.yaml``.
            When ``config_obj.charm_part.model`` is non-empty that
            value is used; otherwise falls back to :data:`_DEFAULT_MODEL`.
    """
    charm_part = config_obj.charm_part
    if charm_part and charm_part.model:
        return charm_part.model
    return _DEFAULT_MODEL


def generate_charm(
    *,
    config_obj: Any,
    source_dir: Path,
    project_dir: Path,
) -> dict[str, Any]:
    """Generate charm code for the cloned workload.

    This starts a pi RPC server, asks it to use the juju-charm
    extension to analyse *source_dir* and scaffolds / updates charm
    code into *project_dir*.

    **Current behaviour**: The juju-charm extension's API for
    workload-aware charm generation is still under development.  This
    function currently starts the RPC server, verifies it is alive by
    invoking the ``get_state`` command (which does *not* require an
    API key), and returns that state data.  Real charm generation
    will follow once the extension API is stable.

    Args:
        config_obj: A parsed :class:`~.Config` from ``dashcraft.yaml``.
        source_dir: Path to the cloned upstream workload source tree.
        project_dir: Path to the scaffolded charm project root.

    Returns:
        Response dict from the pi RPC server (currently ``get_state``
        output for the dry-run verification).
    """
    model = _default_model_for_config(config_obj)

    server = PiRpcServer(
        model=model,
        work_dir=project_dir,
    )
    server.start()

    try:
        # For now we call ``get_state`` -- a cheap command that
        # confirms the RPC server is alive and does *not* need a
        # working LLM API key.  Once the juju-charm extension
        # exposes a workload-aware generation tool, replace this
        # with a real invocation.
        response = server.send({'type': 'get_state', 'id': 'dashcraft-verify'})
        return response
    finally:
        server.shutdown()


# ---------------------------------------------------------------------------
# CLI convenience (allows ``python -m dashcraft.pi`` for quick testing)
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print('Testing pi RPC server startup...', file=sys.stderr)
    try:
        with PiRpcServer() as srv:
            print(f'pi pid={srv._proc.pid if srv._proc else "?"}', file=sys.stderr)
            resp = srv.send({'type': 'get_state', 'id': 'test'})
            print('response:', json.dumps(resp, indent=2))
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
