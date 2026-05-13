"""Tests for dashcraft.pi module."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from textwrap import dedent
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dashcraft.config import load_config
from dashcraft.pi import (
    PiRpcServer,
    _build_generation_prompt,
    _default_model_for_config,
    generate_charm,
)
from tests.unit.helpers import MINIMAL_CONFIG, make_config

# ---------------------------------------------------------------------------
# PiRpcServer unit tests
# ---------------------------------------------------------------------------


class TestPiRpcServerInit:
    """Tests for PiRpcServer.__init__ and configuration."""

    def test_default_values(self) -> None:
        srv = PiRpcServer()
        # Internal attrs set but no process started.
        assert srv._model == ''
        assert srv._proc is None
        assert srv.is_running is False

    def test_custom_model(self) -> None:
        srv = PiRpcServer(model='gemini/gemini-2.5-flash')
        assert srv._model == 'gemini/gemini-2.5-flash'

    def test_custom_work_dir(self, tmp_path: Path) -> None:
        srv = PiRpcServer(work_dir=tmp_path)
        assert srv._work_dir == str(tmp_path)

    def test_custom_extension(self, tmp_path: Path) -> None:
        ext_file = tmp_path / 'ext.ts'
        srv = PiRpcServer(extension=str(ext_file))
        assert srv._extension == str(ext_file)


class TestPiRpcServerLifecycle:
    """Tests for start / shutdown / is_running."""

    def test_start_creates_subprocess(self) -> None:
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None  # alive

        with (
            patch('dashcraft.pi.subprocess.Popen', return_value=mock_proc) as mock_popen,
        ):
            srv = PiRpcServer()
            srv.start()

        assert srv.is_running is True
        # Verify pi was launched with RPC flags.
        call_args = mock_popen.call_args[0][0]
        assert 'pi' in call_args
        assert '--mode' in call_args
        assert 'rpc' in call_args
        assert '--no-session' in call_args

    def test_start_passes_model_when_set(self) -> None:
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None

        with (
            patch('dashcraft.pi.subprocess.Popen', return_value=mock_proc) as mock_popen,
        ):
            srv = PiRpcServer(model='openai/gpt-4o')
            srv.start()

        call_args = mock_popen.call_args[0][0]
        assert '--model' in call_args
        assert 'openrouter/openai/gpt-4o' in call_args

    def test_start_sets_no_model_flag_when_empty(self) -> None:
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None

        with (
            patch('dashcraft.pi.subprocess.Popen', return_value=mock_proc) as mock_popen,
        ):
            srv = PiRpcServer(model='')
            srv.start()

        call_args = mock_popen.call_args[0][0]
        assert '--model' not in call_args

    def test_start_passes_extension_flag(self, tmp_path: Path) -> None:
        ext_file = tmp_path / 'fake.ts'
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None

        with (
            patch('dashcraft.pi.subprocess.Popen', return_value=mock_proc) as mock_popen,
        ):
            srv = PiRpcServer(extension=str(ext_file))
            srv.start()

        call_args = mock_popen.call_args[0][0]
        ext_idx = call_args.index('--extension')
        assert call_args[ext_idx + 1] == str(ext_file)

    def test_shutdown_when_not_started(self) -> None:
        srv = PiRpcServer()
        # Should not raise.
        srv.shutdown()

    def test_shutdown_when_running(self) -> None:
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()

        srv = PiRpcServer()
        srv._proc = mock_proc
        srv.shutdown()

        mock_proc.stdin.write.assert_called_once()
        mock_proc.stdin.flush.assert_called()
        mock_proc.stdin.close.assert_called()
        mock_proc.wait.assert_called_once()

    def test_shutdown_when_process_already_exited(self) -> None:
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = 0  # already exited.
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()

        srv = PiRpcServer()
        srv._proc = mock_proc
        srv.shutdown()

        # Should not try to write to stdin.
        mock_proc.stdin = None  # type: ignore[assignment]
        mock_proc.wait.assert_not_called()


class TestPiRpcServerSend:
    """Tests for the send() method (mocking the subprocess)."""

    def _make_mock_proc(self, responses: list[str], exit_code: int | None = None) -> MagicMock:
        """Create a mock subprocess.Popen that yields *responses* lines on stdout.

        If *exit_code* is set, ``poll()`` returns it after a single call.
        """
        mock = MagicMock(spec=subprocess.Popen)
        mock.stdin = MagicMock()
        mock.stdout = io.StringIO('\n'.join(responses) + '\n')
        mock.poll.return_value = None  # running

        if exit_code is not None:
            mock.poll.side_effect = [None, exit_code]  # first: alive, second: exited

        return mock

    def test_send_returns_matching_response(self) -> None:
        resp = {'type': 'response', 'id': 'x1', 'success': True}
        mock_proc = self._make_mock_proc([json.dumps(resp)])

        srv = PiRpcServer()
        srv._proc = mock_proc

        result = srv.send({'type': 'get_state', 'id': 'x1'})
        assert result == resp

    def test_send_raises_when_server_not_running(self) -> None:
        srv = PiRpcServer()
        with pytest.raises(RuntimeError, match='not running'):
            srv.send({'type': 'get_state'})

    def test_send_raises_on_timeout(self) -> None:
        # stdout has no response lines - will time out.
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = io.StringIO('')

        srv = PiRpcServer()
        srv._proc = mock_proc

        with pytest.raises(RuntimeError, match='Timed out'):
            srv.send({'type': 'get_state', 'id': 'to'}, timeout=0.01)

    def test_send_writes_formatted_json_to_stdin(self) -> None:
        resp = {'type': 'response', 'id': 'y', 'success': True}
        mock_proc = self._make_mock_proc([json.dumps(resp)])

        srv = PiRpcServer()
        srv._proc = mock_proc
        srv.send({'type': 'bash', 'id': 'y'})

        written = mock_proc.stdin.write.call_args[0][0]
        # Should be a single JSONL line with newline.
        assert written.endswith('\n')
        parsed = json.loads(written.strip())
        assert parsed['type'] == 'bash'
        assert parsed['id'] == 'y'

    def test_send_skips_events_and_returns_first_response(self) -> None:
        event = {'type': 'agent_start'}
        resp = {'type': 'response', 'id': 'e1', 'success': True}
        lines = [json.dumps(event), json.dumps(resp)]
        mock_proc = self._make_mock_proc(lines)

        srv = PiRpcServer()
        srv._proc = mock_proc
        result = srv.send({'type': 'prompt', 'message': 'hi', 'id': 'e1'})

        assert result == resp


class TestPiRpcServerContextManager:
    """Ensure __enter__ starts and __exit__ shuts down."""

    def test_context_manager_calls(self) -> None:
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()

        with patch('dashcraft.pi.subprocess.Popen', return_value=mock_proc):
            with PiRpcServer(model='dummy') as srv:
                assert srv.is_running

        mock_proc.stdin.close.assert_called()


# ---------------------------------------------------------------------------
# _default_model_for_config / generate_charm
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _build_generation_prompt
# ---------------------------------------------------------------------------


class TestBuildGenerationPrompt:
    """Tests for the _build_generation_prompt helper."""

    def test_includes_charm_name(self, tmp_path: Path) -> None:
        prompt = _build_generation_prompt(
            charm_dir=tmp_path / 'charm',
            workload_dir=tmp_path / 'source',
            charm_name='my-awesome-charm',
        )
        assert 'my-awesome-charm' in prompt

    def test_includes_summary_and_description(self, tmp_path: Path) -> None:
        prompt = _build_generation_prompt(
            charm_dir=tmp_path / 'charm',
            workload_dir=tmp_path / 'source',
            charm_name='test',
            summary='A cool charm',
            description='Does great things',
        )
        assert 'A cool charm' in prompt
        assert 'Does great things' in prompt

    def test_omits_empty_summary_and_description(self, tmp_path: Path) -> None:
        prompt = _build_generation_prompt(
            charm_dir=tmp_path / 'charm',
            workload_dir=tmp_path / 'source',
            charm_name='test',
        )
        assert 'Summary:' not in prompt
        assert 'Description:' not in prompt

    def test_includes_phase_structure(self, tmp_path: Path) -> None:
        prompt = _build_generation_prompt(
            charm_dir=tmp_path / 'charm',
            workload_dir=tmp_path / 'source',
            charm_name='test',
        )
        assert 'Phase 1: Initial research' in prompt
        assert 'Phase 2: Fix structural issues' in prompt
        assert 'Phase 3: Lint and fix' in prompt
        assert 'Phase 4: Unit tests and fix' in prompt
        assert 'Phase 5: Load skills for quality' in prompt
        assert 'Phase 6: Final validation' in prompt

    def test_includes_dashcraft_tool_call(self, tmp_path: Path) -> None:
        prompt = _build_generation_prompt(
            charm_dir=tmp_path / 'charm',
            workload_dir=tmp_path / 'source',
            charm_name='test',
        )
        assert 'dashcraft tool' in prompt
        assert str(tmp_path / 'charm') in prompt
        assert str(tmp_path / 'source') in prompt


def test_default_model_for_config_uses_set_model() -> None:
    """When config has a model set, that value is returned."""
    with make_config(MINIMAL_CONFIG) as cfg_path:
        config = load_config(cfg_path)
    # MINIMAL_CONFIG has model: gpt-4
    assert _default_model_for_config(config) == 'gpt-4'


def test_default_model_for_config_falls_back() -> None:
    """When no model is set, falls back to the default."""
    content = dedent("""\
        name: my-charm
        parts:
          charm:
            plugin: -craft
            upstream: https://example.com
    """)
    with make_config(content) as cfg_path:
        config = load_config(cfg_path)
    assert _default_model_for_config(config) == 'gemini/gemini-2.5-flash'


class TestGenerateCharm:
    """Tests for generate_charm() — sends a prompt and waits for agent."""

    def _make_fake_proc(
        self, prompt_response: dict, agent_end_event: dict | None = None
    ) -> MagicMock:
        """Create a mock Popen that streams prompt_response then agent_end."""
        lines = [json.dumps(prompt_response)]
        if agent_end_event is not None:
            lines.append(json.dumps(agent_end_event))
        mock = MagicMock(spec=subprocess.Popen)
        mock.poll.return_value = None
        mock.stdin = MagicMock()
        mock.stdout = io.StringIO('\n'.join(lines) + '\n')
        mock.stderr = io.StringIO('')
        return mock

    def test_sends_prompt_and_returns_success(self, tmp_path: Path) -> None:
        """generate_charm sends prompt, waits for agent_end, returns success."""
        source_dir = tmp_path / 'source'
        source_dir.mkdir()
        project_dir = tmp_path / 'charm'
        project_dir.mkdir()

        prompt_resp = {
            'type': 'response',
            'id': 'dashcraft-prompt',
            'command': 'prompt',
            'success': True,
        }
        agent_end = {'type': 'agent_end', 'messages': []}

        mock_proc = self._make_fake_proc(prompt_resp, agent_end)

        with patch('dashcraft.pi.subprocess.Popen', return_value=mock_proc):
            with make_config(MINIMAL_CONFIG) as cfg_path:
                config = load_config(cfg_path)
                result = generate_charm(
                    config_obj=config,
                    source_dir=source_dir,
                    project_dir=project_dir,
                )

        assert result['success'] is True
        assert result['prompt_response'] == prompt_resp
        assert result['agent_end'] == agent_end

    def test_prompt_response_contains_correct_prompt(self, tmp_path: Path) -> None:
        """The sent prompt includes charm name, source dir, and project dir."""
        source_dir = tmp_path / 'source'
        source_dir.mkdir()
        project_dir = tmp_path / 'charm'
        project_dir.mkdir()

        prompt_resp = {
            'type': 'response',
            'id': 'dashcraft-prompt',
            'command': 'prompt',
            'success': True,
        }
        agent_end = {'type': 'agent_end', 'messages': []}
        mock_proc = self._make_fake_proc(prompt_resp, agent_end)

        with make_config(MINIMAL_CONFIG) as cfg_path:
            config = load_config(cfg_path)

        captured_cmd: list[dict] = []

        def fake_popen(cmd: list[str], **kw: object) -> MagicMock:
            return mock_proc

        with patch('dashcraft.pi.subprocess.Popen', side_effect=fake_popen):
            # Override stdin.write to capture the prompt
            original_write = mock_proc.stdin.write

            def capture_write(line: str) -> None:
                captured_cmd.append(json.loads(line))
                return original_write(line)

            mock_proc.stdin.write = MagicMock(side_effect=capture_write)

            generate_charm(
                config_obj=config,
                source_dir=source_dir,
                project_dir=project_dir,
            )

        assert len(captured_cmd) >= 1
        sent_prompt = captured_cmd[0]
        assert sent_prompt['type'] == 'prompt'
        assert 'my-charm' in sent_prompt['message']  # charm name from config
        assert str(source_dir) in sent_prompt['message']
        assert str(project_dir) in sent_prompt['message']

    def test_returns_failure_when_prompt_rejected(self, tmp_path: Path) -> None:
        """If prompt response has success=False, generate_charm reports failure."""
        source_dir = tmp_path / 'source'
        source_dir.mkdir()
        project_dir = tmp_path / 'charm'
        project_dir.mkdir()

        prompt_resp = {
            'type': 'response',
            'id': 'dashcraft-prompt',
            'command': 'prompt',
            'success': False,
            'error': 'no API key',
        }

        mock_proc = self._make_fake_proc(prompt_resp)

        with patch('dashcraft.pi.subprocess.Popen', return_value=mock_proc):
            with make_config(MINIMAL_CONFIG) as cfg_path:
                config = load_config(cfg_path)
                result = generate_charm(
                    config_obj=config,
                    source_dir=source_dir,
                    project_dir=project_dir,
                )

        assert result['success'] is False
        assert result['error'] == 'no API key'
        assert result['prompt_response'] == prompt_resp

    def test_generates_with_config_model(self, tmp_path: Path) -> None:
        """The model from config is passed to PiRpcServer."""
        source_dir = tmp_path / 'source'
        source_dir.mkdir()
        project_dir = tmp_path / 'charm'
        project_dir.mkdir()

        prompt_resp = {
            'type': 'response',
            'id': 'dashcraft-prompt',
            'command': 'prompt',
            'success': True,
        }
        agent_end = {'type': 'agent_end', 'messages': []}
        mock_proc = self._make_fake_proc(prompt_resp, agent_end)

        with make_config(MINIMAL_CONFIG) as cfg_path:
            config = load_config(cfg_path)

        captured_model: list[str] = []

        def fake_popen(cmd: list[str], **kw: object) -> MagicMock:
            if '--model' in cmd:
                idx = cmd.index('--model')
                captured_model.append(cmd[idx + 1])
            return mock_proc

        with patch('dashcraft.pi.subprocess.Popen', side_effect=fake_popen):
            generate_charm(
                config_obj=config,
                source_dir=source_dir,
                project_dir=project_dir,
            )

        assert captured_model == ['openrouter/gpt-4']  # code adds openrouter/ prefix

    def test_raises_runtime_error_on_server_failure(self, tmp_path: Path) -> None:
        """If the server is not running, generate_charm raises RuntimeError."""
        source_dir = tmp_path / 'source'
        source_dir.mkdir()
        project_dir = tmp_path / 'charm'
        project_dir.mkdir()

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = 1  # immediately dead.
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = io.StringIO('')
        mock_proc.stderr = io.StringIO('error')

        with make_config(MINIMAL_CONFIG) as cfg_path:
            config = load_config(cfg_path)

        with patch('dashcraft.pi.subprocess.Popen', return_value=mock_proc):
            with pytest.raises(RuntimeError, match='not running'):
                generate_charm(
                    config_obj=config,
                    source_dir=source_dir,
                    project_dir=project_dir,
                )

    def test_returns_timeout_on_agent_timeout(self, tmp_path: Path) -> None:
        """If agent_end is never received, returns a timeout error."""
        source_dir = tmp_path / 'source'
        source_dir.mkdir()
        project_dir = tmp_path / 'charm'
        project_dir.mkdir()

        # Only a prompt response — no agent_end, then process exits.
        prompt_resp = {
            'type': 'response',
            'id': 'dashcraft-prompt',
            'command': 'prompt',
            'success': True,
        }
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.stdin = MagicMock()
        # Only the prompt response — no agent_end follows.
        # After the prompt_resp line is consumed, stdout is exhausted.
        mock_proc.stdout = io.StringIO(json.dumps(prompt_resp) + '\n')
        mock_proc.stderr = io.StringIO('')

        # poll() returns None while send() reads the prompt response,
        # then returns 0 so events() stops yielding (no more data).
        # Needs many calls because send(), events(), and shutdown()
        # all call poll().
        poll_calls = iter([None, None, None, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        mock_proc.poll.side_effect = lambda: next(poll_calls, 0)

        with make_config(MINIMAL_CONFIG) as cfg_path:
            config = load_config(cfg_path)

        with patch('dashcraft.pi.subprocess.Popen', return_value=mock_proc):
            result = generate_charm(
                config_obj=config,
                source_dir=source_dir,
                project_dir=project_dir,
                timeout=0.5,
            )

        assert result['success'] is False
        assert result.get('agent_end') is None

    def test_on_event_callback_receives_events(self, tmp_path: Path) -> None:
        """The on_event callback gets called for events during both phases."""
        source_dir = tmp_path / 'source'
        source_dir.mkdir()
        project_dir = tmp_path / 'charm'
        project_dir.mkdir()

        prompt_resp = {
            'type': 'response',
            'id': 'dashcraft-prompt',
            'command': 'prompt',
            'success': True,
        }
        agent_start = {'type': 'agent_start'}
        agent_end = {'type': 'agent_end', 'messages': []}

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        # All events in one stream — prompt_resp, then agent_start, then agent_end
        mock_proc.stdout = io.StringIO(
            json.dumps(prompt_resp)
            + '\n'
            + json.dumps(agent_start)
            + '\n'
            + json.dumps(agent_end)
            + '\n'
        )
        mock_proc.stderr = io.StringIO('')

        events_seen: list[dict[str, Any]] = []

        with patch('dashcraft.pi.subprocess.Popen', return_value=mock_proc):
            with make_config(MINIMAL_CONFIG) as cfg_path:
                config = load_config(cfg_path)
                generate_charm(
                    config_obj=config,
                    source_dir=source_dir,
                    project_dir=project_dir,
                    on_event=events_seen.append,
                )

        # Should have seen the response, agent_start, and agent_end
        event_types = [e.get('type') for e in events_seen]
        assert 'response' in event_types
        assert 'agent_start' in event_types
        assert 'agent_end' in event_types
