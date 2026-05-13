"""Tests for dashcraft.pi module."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from textwrap import dedent
from unittest.mock import MagicMock, patch

import pytest

from dashcraft.config import load_config
from dashcraft.pi import PiRpcServer, _default_model_for_config, generate_charm
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
        assert 'openai/gpt-4o' in call_args

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
    """Tests for generate_charm(). Currently a dry-run wrapper."""

    def test_calls_get_state_and_returns_response(self, tmp_path: Path) -> None:
        """generate_charm starts server and returns its response."""
        source_dir = tmp_path / 'source'
        project_dir = tmp_path / 'charm'
        project_dir.mkdir()

        fake_response = {
            'type': 'response',
            'id': 'dashcraft-verify',
            'success': True,
            'data': {'isStreaming': False},
        }

        # Build a fake Popen that serves our canned response.
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = io.StringIO(json.dumps(fake_response) + '\n')
        mock_proc.stderr = io.StringIO('')

        with patch('dashcraft.pi.subprocess.Popen', return_value=mock_proc):
            with make_config(MINIMAL_CONFIG) as cfg_path:
                config = load_config(cfg_path)
                result = generate_charm(
                    config_obj=config,
                    source_dir=source_dir,
                    project_dir=project_dir,
                )

        assert result == fake_response

    def test_generates_with_config_model(self, tmp_path: Path) -> None:
        """The model from config is passed to PiRpcServer."""
        source_dir = tmp_path / 'source'
        project_dir = tmp_path / 'charm'
        project_dir.mkdir()

        fake_response = {
            'type': 'response',
            'id': 'dashcraft-verify',
            'success': True,
            'data': {},
        }

        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stdout = io.StringIO(json.dumps(fake_response) + '\n')
        mock_proc.stderr = io.StringIO('')

        with make_config(MINIMAL_CONFIG) as cfg_path:
            config = load_config(cfg_path)

        captured_model: list[str] = []

        def fake_popen(cmd: list[str], **kw: object) -> MagicMock:
            # Capture the --model value.
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

        assert captured_model == ['gpt-4']  # from MINIMAL_CONFIG

    def test_raises_runtime_error_on_server_failure(self, tmp_path: Path) -> None:
        """If the server is not running, generate_charm raises RuntimeError."""
        source_dir = tmp_path / 'source'
        project_dir = tmp_path / 'charm'
        project_dir.mkdir()

        # Make Popen create a process that is immediately dead.
        mock_proc = MagicMock(spec=subprocess.Popen)
        mock_proc.poll.return_value = 1  # exited.
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
