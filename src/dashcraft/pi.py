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
from collections.abc import Callable, Iterator
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
        system_prompt: str | None = None,
        no_skills: bool = True,
        no_prompt_templates: bool = True,
    ) -> None:
        """Initialise configuration for the RPC subprocess.

        Args:
            model: Pi model pattern (e.g. ``'gemini/gemini-2.5-flash'``).
                When empty, pi uses its default model selection.
            extension: Absolute path to a pi extension ``.ts`` file.
                Defaults to the shipped juju-charm extension.
            work_dir: Working directory for the pi subprocess.
                Defaults to the current working directory.
            system_prompt: Custom system prompt for the agent.
                When ``None`` a default charm-focused prompt is used.
                Pass ``""`` to disable the ``--system-prompt`` flag.
            no_skills: Pass ``--no-skills`` to pi. Set ``False`` to
                allow loading project/user skills.
            no_prompt_templates: Pass ``--no-prompt-templates`` to pi.
                Set ``False`` to allow loading prompt templates.
        """
        self._model = model
        self._extension = extension or str(_EXTENSION_PATH)
        self._work_dir = str(work_dir) if work_dir else str(Path.cwd())
        self._system_prompt = (
            system_prompt
            if system_prompt is not None
            else 'You are an assistant that generates Juju charm code.'
        )
        self._no_skills = no_skills
        self._no_prompt_templates = no_prompt_templates
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
            '--no-context-files',
            '--no-themes',
            '--extension',
            self._extension,
        ]
        if self._no_skills:
            cmd += ['--no-skills']
        if self._no_prompt_templates:
            cmd += ['--no-prompt-templates']
        if self._system_prompt:
            cmd += ['--system-prompt', self._system_prompt]
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

    def send(
        self,
        command: dict[str, Any],
        *,
        timeout: float = 30.0,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Send a single command and return its response.

        This writes *command* to stdin (JSONL), reads JSON lines from
        stdout until it finds a line with ``"type": "response"`` that
        matches the command's ``id`` (or just the first response if no
        ``id`` was set), and returns that response dict.

        Other lines (events, extension UI requests, etc.) are discarded
        by default.  Supply *on_event* to receive each event dict as it
        arrives.

        Args:
            command: The JSON-RPC-style command dict.
            timeout: Max seconds to wait for a matching response.
            on_event: Optional callback invoked for each event dict
                read from stdout before the matching response arrives.

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
                if on_event:
                    on_event(msg)
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

    def wait_for_agent_end(
        self,
        *,
        timeout: float = 600.0,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any] | None:
        """Read events until ``agent_end`` or timeout.

        After sending a ``prompt`` command, the agent works
        asynchronously. Call this to wait for it to finish.

        Args:
            timeout: Maximum seconds to wait (default 600 == 10 min).
            on_event: Optional callback for every event dict seen.

        Returns:
            The ``agent_end`` event dict, or ``None`` on timeout /
            process exit.
        """
        deadline = time.monotonic() + timeout
        for event in self.events():
            if on_event:
                on_event(event)
            if event.get('type') == 'agent_end':
                return event
            if time.monotonic() >= deadline:
                return None
        return None

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


def _build_generation_prompt(
    *,
    charm_dir: Path,
    workload_dir: Path,
    charm_name: str,
    summary: str = '',
    description: str = '',
) -> str:
    """Build the multi-phase prompt for the pi agent.

    Args:
        charm_dir: Path to the scaffolded charm project.
        workload_dir: Path to the cloned upstream workload source.
        charm_name: Name of the charm (from config).
        summary: Short summary from the config (may be empty).
        description: Longer description from the config (may be empty).

    Returns:
        The prompt string to send via the pi RPC ``prompt`` command.
    """
    # Build context header from config metadata.
    context_parts = [f'Charm name: {charm_name}']
    if summary:
        context_parts.append(f'Summary: {summary}')
    if description:
        context_parts.append(f'Description: {description}')
    context_header = '\n'.join(context_parts)

    return (
        f'You are going to build a Juju charm for a workload. Do everything in one shot '
        f'— do NOT stop and ask questions, just keep going until the charm is ready.\n'
        f'\n'
        f'## Project context\n'
        f'{context_header}\n'
        f'Charm directory: {charm_dir}\n'
        f'Workload source: {workload_dir}\n'
        f'\n'
        f'## Phase 1: Initial research\n'
        f'Call the dashcraft tool with:\n'
        f'  directory={charm_dir}\n'
        f'  workload={workload_dir}\n'
        f'\n'
        f'## Phase 2: Fix structural issues\n'
        f'Read the generated charmcraft.yaml and src/charm.py. Fix any structural problems:\n'
        f'- Malformed YAML or dict nesting\n'
        f'- Placeholder commands (/bin/foo)\n'
        f'- Missing module files\n'
        f'- Incorrect container/resource names\n'
        f"- Anything that won't work\n"
        f'\n'
        f'## Phase 3: Lint and fix\n'
        f'Run charm_lint on {charm_dir}. If it fails, fix the issues and re-run '
        f'until lint passes cleanly.\n'
        f'\n'
        f'## Phase 4: Unit tests and fix\n'
        f'Run charm_test_unit on {charm_dir}. If it fails, fix the issues and re-run '
        f'until unit tests pass cleanly.\n'
        f'\n'
        f'## Phase 5: Load skills for quality\n'
        f'Load /skill:relations if the workload has database/integration needs, '
        f'/skill:observability for COS integration, and '
        f'/skill:operational-patterns for actions/config/status patterns. '
        f'Apply the relevant patterns.\n'
        f'\n'
        f'## Phase 6: Final validation\n'
        f'Run charm_lint AND charm_test_unit one last time to confirm everything passes.\n'
        f'\n'
        f'IMPORTANT: Do NOT stop between phases. Do NOT ask the user for permission. '
        f'Just go through all phases in one continuous run.'
    )


def generate_charm(
    *,
    config_obj: Any,
    source_dir: Path,
    project_dir: Path,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    timeout: float = 600.0,
    prompt_timeout: float = 30.0,
) -> dict[str, Any]:
    """Generate charm code for the cloned workload via pi RPC.

    This starts a pi RPC server, sends a detailed multi-phase prompt
    instructing the agent to analyse *source_dir*, call the dashcraft
    tool, fix issues, lint, and run unit tests, then waits for the
    agent to finish.

    Args:
        config_obj: A parsed :class:`~.Config` from ``dashcraft.yaml``.
        source_dir: Path to the cloned upstream workload source tree.
        project_dir: Path to the scaffolded charm project root.
        on_event: Optional callback invoked for every event received
            from the pi subprocess (both during prompt acceptance and
            while waiting for ``agent_end``).
        timeout: Maximum seconds to wait for the agent to finish
            (default 600 s == 10 min).
        prompt_timeout: Maximum seconds to wait for the prompt
            command response (default 30 s).

    Returns:
        A dict with at least these keys:

        - ``success`` (*bool*): Whether the agent completed without
          a top-level error.
        - ``agent_end`` (*dict | None*): The ``agent_end`` event if
          the agent finished, ``None`` on timeout.
        - ``prompt_response`` (*dict*): The response to the initial
          ``prompt`` command.
        - ``error`` (*str*, optional): Error message on failure.
    """
    model = _default_model_for_config(config_obj)
    charm_name = config_obj.name
    summary = config_obj.summary
    description = config_obj.description

    prompt = _build_generation_prompt(
        charm_dir=project_dir,
        workload_dir=source_dir,
        charm_name=charm_name,
        summary=summary,
        description=description,
    )

    server = PiRpcServer(
        model=model,
        work_dir=project_dir,
    )
    server.start()

    try:
        # Phase 1 — send the prompt and confirm acceptance.
        prompt_response = server.send(
            {
                'type': 'prompt',
                'message': prompt,
                'id': 'dashcraft-prompt',
            },
            timeout=prompt_timeout,
            on_event=on_event,
        )

        if not prompt_response.get('success'):
            return {
                'success': False,
                'prompt_response': prompt_response,
                'agent_end': None,
                'error': prompt_response.get('error', 'Prompt rejected'),
            }

        # Phase 2 — wait for the agent to finish its work.
        agent_end = server.wait_for_agent_end(timeout=timeout, on_event=on_event)

        if agent_end is None:
            return {
                'success': False,
                'prompt_response': prompt_response,
                'agent_end': None,
                'error': f'Agent timed out after {timeout}s',
            }

        return {
            'success': True,
            'prompt_response': prompt_response,
            'agent_end': agent_end,
        }

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
