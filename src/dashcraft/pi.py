"""Manage a pi RPC server subprocess for AI-driven charm generation.

Starts ``pi --mode rpc`` as a subprocess, communicates via the JSONL
protocol on stdin/stdout, and shuts it down when finished.  Provides
high-level functions used by the ``pack`` command to invoke the
juju-charm extension against a cloned workload and scaffolded charm
directory.

See ``docs/rpc.md`` in the pi source tree for the full protocol.
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from dashcraft.analysis import WorkloadAnalysis
from dashcraft.config import Config

# ---------------------------------------------------------------------------
# Low-level subprocess manager
# ---------------------------------------------------------------------------


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
        self._extension = extension
        self._work_dir = str(work_dir) if work_dir else str(Path.cwd())
        self._system_prompt = (
            system_prompt
            if system_prompt is not None
            else 'You are an assistant that generates Juju charm code.'
        )
        self._no_skills = no_skills
        self._no_prompt_templates = no_prompt_templates
        self._proc: subprocess.Popen[str] | None = None
        # Shared read buffer so that data prefetched during send()
        # is not lost when events() / wait_for_agent_end() reads next.
        self._buffer: str = ''
        # If agent_end arrives during send() (unlikely but possible),
        # stash it here so wait_for_agent_end() can return immediately.
        self._pending_agent_end: dict[str, Any] | None = None

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
            cmd += ['--model', 'openrouter/' + self._model.removeprefix('openrouter/')]

        self._proc = subprocess.Popen(  # ty: ignore[no-matching-overload,invalid-assignment]
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
                with contextlib.suppress(BrokenPipeError, OSError):
                    self._proc.stdin.write(json.dumps({'type': 'abort', 'id': 'shutdown'}) + '\n')
                    self._proc.stdin.flush()
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

        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                # Process exited -- drain remaining buffer.
                remaining = self._proc.stdout.read()
                if remaining:
                    self._buffer += remaining
                break

            chunk = self._proc.stdout.readline()
            if not chunk:
                break
            self._buffer += chunk

            # Process complete lines.
            while '\n' in self._buffer:
                line, self._buffer = self._buffer.split('\n', 1)
                line = line.rstrip('\r')
                if not line.strip():
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                events_seen.append(msg)
                # Stash agent_end in case it arrives before the response.
                if msg.get('type') == 'agent_end':
                    self._pending_agent_end = msg
                if on_event:
                    on_event(msg)
                if msg.get('type') == 'response':
                    resp_id = msg.get('id')
                    # Match on id if the original command had one.
                    if cmd_id is None or resp_id == cmd_id:
                        return msg
                    # Got a response for a different id -- keep waiting.

        # Timeout or no matching response.
        stderr_info = ''
        if self._proc is not None:
            with contextlib.suppress(Exception):
                stderr_stream = getattr(self._proc, 'stderr', None)
                if stderr_stream is not None:
                    err = stderr_stream.read()
                    if err and err.strip():
                        stderr_info = f'\n  pi stderr: {err[-1000:]}'
        raise RuntimeError(
            f'Timed out waiting for pi RPC response (id={cmd_id!r}). '
            f'Events seen: {len(events_seen)}.{stderr_info}'
        )

    def wait_for_agent_end(
        self,
        *,
        timeout: float = 1800.0,
        on_event: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any] | None:
        """Read events until ``agent_end`` or timeout.

        After sending a ``prompt`` command, the agent works
        asynchronously. Call this to wait for it to finish.

        Args:
            timeout: Maximum seconds to wait (default 1800 == 30 min).
            on_event: Optional callback for every event dict seen.

        Returns:
            The ``agent_end`` event dict, or ``None`` on timeout /
            process exit.
        """
        # If agent_end was already seen during send(), return immediately.
        if self._pending_agent_end is not None:
            result = self._pending_agent_end
            self._pending_agent_end = None
            return result

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

        Each line is parsed and yielded as a dict.  Reads from the
        shared ``self._buffer`` first so that data prefetched during
        ``send()`` is not lost.

        Stops when the subprocess exits and stdout is exhausted.
        """
        if self._proc is None or self._proc.stdout is None:
            return

        # First, drain the shared buffer (data already read by send()).
        while '\n' in self._buffer:
            line, self._buffer = self._buffer.split('\n', 1)
            line = line.rstrip('\r')
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

        # Then read from stdout line-by-line.
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


def _default_model_for_config(config_obj: Config) -> str:
    """Return the model to use, falling back to a sensible default.

    Args:
        config_obj: A :class:`~.Config` loaded from ``dashcraft.yaml``.
            When ``config_obj.charm_part.model`` is non-empty that
            value is used; otherwise falls back to :data:`_DEFAULT_MODEL`.

    Note:
        Whatever provider prefix the user supplies (``gemini/``,
        ``anthropic/``, etc.) is preserved here. The OpenRouter prefix
        in :meth:`PiRpcServer.start` is layered on top so that pi routes
        every model through OpenRouter as the gateway.
    """
    charm_part = config_obj.charm_part
    if charm_part and charm_part.model:
        return charm_part.model
    return _DEFAULT_MODEL


_MAX_FIX_ITERATIONS = 5


def _format_analysis_block(analysis: WorkloadAnalysis) -> str:
    """Render a compact, agent-readable summary of the workload analysis."""
    lines = [
        f'- name: {analysis.name}',
        f'- language: {analysis.language}',
    ]
    if analysis.framework != 'none':
        lines.append(f'- framework: {analysis.framework}')
    if analysis.command:
        lines.append(f'- command: {analysis.command}')
    if analysis.port:
        lines.append(f'- port: {analysis.port}')
    if analysis.env_vars:
        lines.append(f'- env vars: {", ".join(sorted(analysis.env_vars))}')
    if analysis.is_web_app:
        lines.append('- web app: yes')
    if analysis.needs_database:
        lines.append('- needs database: yes')
    if analysis.has_dockerfile:
        lines.append('- Dockerfile: yes')
    return '\n'.join(lines)


def _build_generation_prompt(
    *,
    charm_dir: Path,
    workload_dir: Path,
    charm_name: str,
    summary: str = '',
    description: str = '',
    analysis: WorkloadAnalysis | None = None,
) -> str:
    """Build the one-shot prompt for the pi agent.

    The CLI has already analysed the workload and written filled
    ``charmcraft.yaml`` and ``src/charm.py`` into *charm_dir*. The agent's
    job is to polish and validate those files, not to re-do the research.

    Args:
        charm_dir: Path to the scaffolded charm project.
        workload_dir: Path to the cloned upstream workload source.
        charm_name: Name of the charm (from config).
        summary: Short summary from the config (may be empty).
        description: Longer description from the config (may be empty).
        analysis: Pre-computed workload analysis. When provided, its
            details are inlined into the prompt so the agent does not
            need to re-research the workload.
    """
    header_lines = [f'Charm name: {charm_name}']
    if summary:
        header_lines.append(f'Summary: {summary}')
    if description:
        header_lines.append(f'Description: {description}')
    header_lines.append(f'Charm directory: {charm_dir}')
    header_lines.append(f'Workload source: {workload_dir}')
    header = '\n'.join(header_lines)

    analysis_block = _format_analysis_block(analysis) if analysis else '(no analysis available)'

    return (
        'You are polishing a Juju charm. The upstream workload is already cloned and '
        '`charmcraft.yaml` + `src/charm.py` are pre-filled from a deterministic '
        'workload analysis. Do everything in one shot — do NOT stop or ask questions.\n'
        '\n'
        '## Project context\n'
        f'{header}\n'
        '\n'
        '## Workload analysis (already applied to the scaffold)\n'
        f'{analysis_block}\n'
        '\n'
        '## What is already done — do NOT redo\n'
        f'- Upstream is cloned at {workload_dir}.\n'
        f'- charmcraft.yaml and src/charm.py at {charm_dir} are pre-filled from the\n'
        '  analysis above. Do NOT call the dashcraft tool; the files are ready.\n'
        '\n'
        '## Tasks (do in order, no questions)\n'
        f'1. Quickly read {charm_dir}/charmcraft.yaml and src/charm.py. Edit only if\n'
        '   something is obviously wrong for this workload (e.g. the command is a\n'
        '   placeholder, an env var maps to the wrong config key). Otherwise leave\n'
        '   them alone.\n'
        f'2. Run charm_lint. If it fails, fix and re-run, '
        f'up to {_MAX_FIX_ITERATIONS} attempts.\n'
        f'3. Run charm_test_unit. If it fails, fix and re-run, '
        f'up to {_MAX_FIX_ITERATIONS} attempts.\n'
        '4. If the workload uses a database / cache / ingress, load /skill:relations\n'
        '   and /skill:operational-patterns and apply the relevant patterns. Re-run\n'
        '   charm_lint and charm_test_unit after the changes.\n'
        '5. Final pass: charm_lint AND charm_test_unit must both pass.\n'
        '\n'
        '## Hard rules\n'
        '- Do NOT ask the user for permission or input.\n'
        f'- If lint or unit tests fail more than {_MAX_FIX_ITERATIONS} times, stop trying\n'
        '  to fix; write a one-paragraph KNOWN_ISSUES.md describing what remains, then\n'
        '  finish with whatever passes.\n'
        '- Do NOT call the `dashcraft` tool — files are already filled.\n'
    )


def _resolve_extension_path(project_dir: Path) -> Path | None:
    """Find the dashcraft extension for a project.

    Looks in *project_dir* first, then falls back to the bundled
    extension next to this module.

    Returns the absolute path to ``index.ts``, or ``None`` if not
    found in either location.
    """
    rel = Path('.pi') / 'extensions' / 'dashcraft' / 'index.ts'
    project_ext = project_dir / rel
    if project_ext.exists():
        return project_ext
    bundled_ext = Path(__file__).resolve().parent / rel
    if bundled_ext.exists():
        return bundled_ext
    return None


def generate_charm(
    *,
    config_obj: Config,
    source_dir: Path,
    project_dir: Path,
    analysis: WorkloadAnalysis | None = None,
    on_event: Callable[[dict[str, Any]], None] | None = None,
    timeout: float = 1800.0,
    prompt_timeout: float = 300.0,
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
        analysis: Optional pre-computed workload analysis. When provided,
            its details are embedded in the prompt so the agent does
            not need to re-research the workload.
        on_event: Optional callback invoked for every event received
            from the pi subprocess (both during prompt acceptance and
            while waiting for ``agent_end``).
        timeout: Maximum seconds to wait for the agent to finish
            (default 1800 s == 30 min).
        prompt_timeout: Maximum seconds to wait for the prompt
            command response (default 300 s).  This needs to be long
            enough to cover pi startup, model initialisation, and
            extension loading.

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
        analysis=analysis,
    )

    extension = _resolve_extension_path(project_dir)
    if extension is None:
        return {
            'success': False,
            'prompt_response': {},
            'agent_end': None,
            'error': (
                'Could not find dashcraft pi extension in either '
                f'{project_dir}/.pi or alongside the dashcraft package.'
            ),
        }
    server = PiRpcServer(
        model=model,
        work_dir=project_dir,
        extension=str(extension),
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
                'error': (
                    f'Agent timed out after {timeout}s. Increase the timeout parameter if needed.'
                ),
            }

        return {
            'success': True,
            'prompt_response': prompt_response,
            'agent_end': agent_end,
        }

    finally:
        server.shutdown()
