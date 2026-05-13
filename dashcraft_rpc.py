#!/usr/bin/env python3
"""Exercise the dashcraft pi extension over RPC.

Usage:
    python dashcraft_rpc.py <charm_dir> <workload_dir>

    charm_dir    - path to a (pre-scaffolded or empty) charm project directory
    workload_dir - path to a cloned workload source tree
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path
from typing import NoReturn


def _build_parser() -> ArgumentParser:
    p = ArgumentParser(
        description='Exercise the dashcraft pi extension over RPC',
    )
    p.add_argument(
        'charm_dir',
        help='Path to pre-scaffolded (or empty) charm project directory',
    )
    p.add_argument(
        'workload_dir',
        help='Path to cloned workload source tree',
    )
    p.add_argument(
        '--provider',
        default=None,
        help='LLM provider (e.g. anthropic, openai)',
    )
    p.add_argument(
        '--model',
        default=None,
        help='Model pattern (e.g. anthropic/claude-sonnet-4)',
    )
    p.add_argument(
        '--no-session',
        action='store_true',
        help='Do not persist the session to disk',
    )
    p.add_argument(
        '--pi-args',
        default='',
        help='Additional arguments to pass to pi (space-separated)',
    )
    return p


def main(argv: list[str] | None = None) -> NoReturn:
    """Entry-point: start pi in RPC mode and prompt it to run dashcraft."""
    args = _build_parser().parse_args(argv)

    charm_dir = Path(args.charm_dir).resolve()
    workload_dir = Path(args.workload_dir).resolve()

    if not workload_dir.exists():
        print(f"Error: workload '{workload_dir}' does not exist", file=sys.stderr)
        sys.exit(1)

    # Ensure charm dir exists
    charm_dir.mkdir(parents=True, exist_ok=True)

    # Build pi command
    pi_cmd = ['pi', '--mode', 'rpc', '--no-session']
    if not args.no_session:
        # Use temp session
        pi_cmd = ['pi', '--mode', 'rpc']
    if args.provider:
        pi_cmd += ['--provider', args.provider]
    if args.model:
        pi_cmd += ['--model', args.model]
    if args.pi_args:
        pi_cmd += args.pi_args.split()

    # The prompt — one-shot: dashcraft → fix → lint → unit → iterate until clean
    prompt = (
        f'You are going to build a Juju charm for a workload. Do everything in one shot '
        f'— do NOT stop and ask questions, just keep going until the charm is ready.\n'
        f'\n'
        f'## Phase 1: Initial research\n'
        f'Call the dashcraft tool with:\n'
        f'  directory={charm_dir}\n'
        f'  workload={workload_dir}\n'
        f'\n'
        f'## Phase 2: Fix structural issues\n'
        f'Read the generated charmcraft.yaml and src/charm.py. Fix any structural problems:\n'
        f'- Malformed YAML or dict nesting\n'
        f'- Placeholder commands ({"/bin/foo"})\n'
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

    print(f'[dashcraft-rpc] Starting: {" ".join(pi_cmd)}', file=sys.stderr)
    print(f'[dashcraft-rpc] Charm dir:  {charm_dir}', file=sys.stderr)
    print(f'[dashcraft-rpc] Workload:    {workload_dir}', file=sys.stderr)
    print('[dashcraft-rpc] Prompting...', file=sys.stderr)

    proc = subprocess.Popen(
        pi_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    def send(cmd: dict) -> None:
        """Send a JSON-RPC command to pi."""
        line = json.dumps(cmd, ensure_ascii=False)
        print(f'  >>> {line}', file=sys.stderr)
        proc.stdin.write(line + '\n')  # type: ignore[union-attr]
        proc.stdin.flush()  # type: ignore[union-attr]

    # Send the prompt
    send({'type': 'prompt', 'message': prompt})

    # Read events until agent_end or error
    exit_code = 0
    try:
        for raw in proc.stdout:  # type: ignore[union-attr]
            line = raw.rstrip('\n').rstrip('\r')
            if not line:
                continue

            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                print(f'  [non-json] {line}', file=sys.stderr)
                continue

            etype = event.get('type', '')

            # ── Responses to our commands ──────────────────────────────
            if etype == 'response':
                cmd = event.get('command', '?')
                ok = event.get('success', False)
                if cmd == 'prompt':
                    if ok:
                        print(
                            '[dashcraft-rpc] Prompt accepted, waiting for agent...',
                            file=sys.stderr,
                        )
                    else:
                        print(f'[dashcraft-rpc] Prompt rejected: {event}', file=sys.stderr)

            # ── Streaming assistant text ───────────────────────────────
            elif etype == 'message_update':
                delta = event.get('assistantMessageEvent', {})
                if delta.get('type') == 'text_delta':
                    sys.stdout.write(delta['delta'])
                    sys.stdout.flush()

            # ── Tool execution progress ─────────────────────────────────
            elif etype == 'tool_execution_start':
                tname = event.get('toolName', '?')
                print(f'\n[dashcraft-rpc] 🔧 Calling {tname}…', file=sys.stderr)

            elif etype == 'tool_execution_update':
                # Show partial progress from the tool
                for block in event.get('partialResult', {}).get('content', []):
                    if block.get('type') == 'text':
                        print(f'  {block["text"]}', file=sys.stderr)

            elif etype == 'tool_execution_end':
                tname = event.get('toolName', '?')
                is_err = event.get('isError', False)
                status = '❌ FAILED' if is_err else '✓ done'
                print(f'[dashcraft-rpc] {status}: {tname}', file=sys.stderr)

                # Print tool result summary
                if not is_err:
                    result = event.get('result', {})
                    for block in result.get('content', []):
                        if block.get('type') == 'text':
                            print('  ──', file=sys.stderr)
                            print(block['text'], file=sys.stderr)

            # ── Lifecycle ───────────────────────────────────────────────
            elif etype == 'agent_start':
                print('[dashcraft-rpc] Agent started.', file=sys.stderr)

            elif etype == 'agent_end':
                print('\n[dashcraft-rpc] Agent finished.', file=sys.stderr)
                break

            elif etype == 'extension_error':
                print(f'[dashcraft-rpc] Extension error: {event}', file=sys.stderr)

            # Silently skip internal events
            elif etype in ('turn_start', 'turn_end', 'message_start', 'message_end'):
                pass

            else:
                print(f'  [event] {etype}', file=sys.stderr)

    except KeyboardInterrupt:
        print('\n[dashcraft-rpc] Interrupted, aborting…', file=sys.stderr)
        send({'type': 'abort'})
        exit_code = 1

    except BrokenPipeError:
        print('[dashcraft-rpc] pi process closed its stdout unexpectedly.', file=sys.stderr)
        exit_code = 1

    finally:
        with contextlib.suppress(Exception):
            proc.stdin.close()  # type: ignore[union-attr]
        proc.wait(timeout=10)

        # Print any stderr from pi
        stderr_text = proc.stderr.read()  # type: ignore[union-attr]
        if stderr_text.strip():
            print(f'\n[dashcraft-rpc] pi stderr:\n{stderr_text}', file=sys.stderr)

    # ── Independent final check ────────────────────────────────────────
    print('\n[dashcraft-rpc] ── Final validation ──', file=sys.stderr)

    def _run_check(cmd: list[str]) -> tuple[int, str]:
        try:
            r = subprocess.run(cmd, cwd=charm_dir, capture_output=True, text=True, timeout=120)
            return r.returncode, (r.stdout + r.stderr).strip()
        except FileNotFoundError:
            return -1, f'{cmd[0]} not found'
        except subprocess.TimeoutExpired:
            return -1, 'timed out'

    lint_code, lint_out = _run_check(['tox', 'run', '-e', 'lint'])
    unit_code, unit_out = _run_check(['tox', 'run', '-e', 'unit'])

    def _status(code: int) -> str:
        return '✓' if code == 0 else '✗'

    print(f'  charm_lint  {_status(lint_code)} (exit {lint_code})', file=sys.stderr)
    print(f'  charm_unit  {_status(unit_code)} (exit {unit_code})', file=sys.stderr)

    if lint_code != 0:
        print(f'\n[dashcraft-rpc] Lint output:\n{lint_out[-2000:]}', file=sys.stderr)
    if unit_code != 0:
        print(f'\n[dashcraft-rpc] Unit output:\n{unit_out[-2000:]}', file=sys.stderr)

    if lint_code == 0 and unit_code == 0:
        print('[dashcraft-rpc] ✓ Charm is ready!', file=sys.stderr)
        exit_code = 0
    else:
        print(
            '[dashcraft-rpc] ✗ Charm still has issues — run again for another cleanup pass.',
            file=sys.stderr,
        )
        exit_code = 1

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
