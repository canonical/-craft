"""CLI interface for dashcraft."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from dashcraft.config import ConfigError, load_config
from dashcraft.pi import generate_charm
from dashcraft.templates import get_files
from dashcraft.upstream import CloneError, clone_upstream_persistent


def _pi_event_handler(event: dict[str, Any]) -> None:
    """Default on_event callback for streaming pi RPC progress to the user."""
    etype = event.get('type', '')

    if etype == 'response':
        cmd = event.get('command', '?')
        ok = event.get('success', False)
        if cmd == 'prompt':
            if ok:
                print('  [pi] Prompt accepted — agent is working...', file=sys.stderr)
            else:
                err = event.get('error', 'unknown')
                print(f'  [pi] Prompt rejected: {err}', file=sys.stderr)

    elif etype == 'agent_start':
        print('  [pi] Agent started.', file=sys.stderr)

    elif etype == 'tool_execution_start':
        tname = event.get('toolName', '?')
        print(f'  [pi] 🔧 {tname}…', file=sys.stderr)

    elif etype == 'tool_execution_end':
        tname = event.get('toolName', '?')
        is_err = event.get('isError', False)
        status = '❌ FAILED' if is_err else '✓'
        print(f'  [pi] {status} {tname}', file=sys.stderr)

    elif etype == 'tool_execution_update':
        for block in event.get('partialResult', {}).get('content', []):
            if block.get('type') == 'text' and block.get('text', '').strip():
                # Only show non-empty tool progress
                text = block['text'].strip()
                lines = text.split('\n')
                # Show just the last line for brevity
                last_line = lines[-1][:120]
                if last_line:
                    print(f'    {last_line}', file=sys.stderr)

    elif etype == 'message_update':
        delta = event.get('assistantMessageEvent', {})
        if delta.get('type') == 'text_delta':
            sys.stdout.write(delta['delta'])
            sys.stdout.flush()

    elif etype == 'agent_end':
        print('\n  [pi] Agent finished.', file=sys.stderr)

    elif etype == 'extension_error':
        err = event.get('error', 'unknown')
        print(f'  [pi] Extension error: {err}', file=sys.stderr)


def _build_parser(prog: str = 'dashcraft') -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description='AI-powered charm generator — charming, but fast.',
    )
    parser.add_argument(
        '--project-dir',
        type=Path,
        default=Path.cwd(),
        help='Project directory containing dashcraft.yaml or -craft.yaml (default: CWD)',
    )
    subparsers = parser.add_subparsers(dest='command')

    # pack — the only command
    pack_parser = subparsers.add_parser(
        'pack', help='Generate and pack a charm for the upstream workload'
    )
    pack_parser.add_argument(
        '--keep-source',
        action='store_true',
        help='Keep the cloned upstream source directory (do not clean up on exit)',
    )

    return parser


def main() -> int:
    """Entry point for the dashcraft CLI (also works as `-craft`)."""
    prog = os.path.basename(sys.argv[0])
    parser = _build_parser(prog)
    args = parser.parse_args()

    if args.command != 'pack':
        parser.print_help()
        return 1

    return _cmd_pack(args)


def _cmd_pack(args: argparse.Namespace) -> int:
    """Execute the 'pack' command — scaffold and pack."""
    project_dir = args.project_dir

    # Step 1: Load config
    try:
        config = load_config(project_dir)
    except ConfigError as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1

    charm_part = config.charm_part
    assert charm_part is not None  # validated by load_config

    print(f"Packing charm '{config.name}' from upstream: {charm_part.upstream}")

    # Step 2: Clone upstream
    try:
        if args.keep_source:
            source_dir = clone_upstream_persistent(charm_part.upstream)
            print(f'Cloned upstream to: {source_dir}')
            print('(--keep-source: directory will not be cleaned up)')
        else:
            source_dir = clone_upstream_persistent(charm_part.upstream)
            print(f'Cloned upstream to: {source_dir}')
    except CloneError as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1

    # Step 3: Scaffold charm files if charmcraft.yaml doesn't exist
    if not (project_dir / 'charmcraft.yaml').exists():
        scaffold_ret = _do_scaffold(project_dir, config.name, charm_part.workload)
        if scaffold_ret != 0:
            _cleanup_source(source_dir, args.keep_source)
            return scaffold_ret

    # Step 4: Check if pi is available and generate charm code.
    pi_check_ret = _check_pi_installed()
    if pi_check_ret != 0:
        print('Skipping AI charm generation.', file=sys.stderr)
        _cleanup_source(source_dir, args.keep_source)
        return 1

    print('Generating charm code via pi RPC...')
    print(f'  Charm dir:    {project_dir}', file=sys.stderr)
    print(f'  Workload dir: {source_dir}', file=sys.stderr)

    try:
        gen_result = generate_charm(
            config_obj=config,
            source_dir=source_dir,
            project_dir=project_dir,
            on_event=_pi_event_handler,
        )
    except RuntimeError as e:
        print(f'Error: AI charm generation failed: {e}', file=sys.stderr)
        _cleanup_source(source_dir, args.keep_source)
        return 1

    if not gen_result.get('success'):
        err = gen_result.get('error', 'unknown error')
        print(f'Error: Charm generation failed: {err}', file=sys.stderr)
        _cleanup_source(source_dir, args.keep_source)
        return 1

    print('\nCharm generation complete.', file=sys.stderr)

    _cleanup_source(source_dir, args.keep_source)
    return 0

    # Step 5: Pack (unreachable for now — future work)
    print('Packing charm...')
    pack_ret = _run_quickpack(project_dir)

    _cleanup_source(source_dir, args.keep_source)

    return pack_ret


def _cleanup_source(source_dir: Path, keep: bool) -> None:
    """Clean up the cloned upstream source unless --keep-source was given."""
    if not keep:
        shutil.rmtree(source_dir, ignore_errors=True)


def _run_quickpack(cwd: Path) -> int:
    """Run the `quickpack` CLI (from the juju-cantrip PyPI package) in the given directory."""
    quickpack_path = shutil.which('quickpack')
    if not quickpack_path:
        print("Error: 'quickpack' is not installed.", file=sys.stderr)
        print(
            'Install it with:\n  uv tool install juju-cantrip',
            file=sys.stderr,
        )
        return 1
    try:
        subprocess.run([quickpack_path], cwd=cwd, check=True)
    except subprocess.CalledProcessError as e:
        print(f'quickpack failed (exit {e.returncode})', file=sys.stderr)
        return e.returncode or 1
    return 0


def _find_source_pi_dir() -> Path | None:
    """Find the source .pi directory bundled with dashcraft.

    Resolves relative to the package location (src/dashcraft/ -> project root).
    """
    return Path(__file__).resolve().parent.parent / '.pi'


def _do_scaffold(project_dir: Path, name: str, workload_image: str = '') -> int:
    """Scaffold charm files from templates into the project directory."""
    if not _is_valid_kebab_case(name):
        print(
            f'Error: Invalid charm name "{name}". Use kebab-case (e.g. "my-app").',
            file=sys.stderr,
        )
        return 1

    target_dir = project_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    files = get_files(name, workload_image)
    created: list[str] = []
    skipped: list[str] = []

    for rel_path, content in files.items():
        full_path = target_dir / rel_path
        if full_path.exists():
            skipped.append(rel_path)
        else:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding='utf-8')
            created.append(rel_path)

    # Copy the .pi directory (pi extension & skills) into the scaffolded charm.
    _source_pi = _find_source_pi_dir()
    if _source_pi and _source_pi.is_dir():
        _dest_pi = target_dir / '.pi'
        if not _dest_pi.exists():
            shutil.copytree(_source_pi, _dest_pi)
            created.append('.pi/')
        else:
            skipped.append('.pi/')

    print(f'Scaffolded charm "{name}" into {project_dir}.')
    if created:
        print(f'Created {len(created)} files:')
        for f in created:
            print(f'  ✓ {f}')
    if skipped:
        print(f'Skipped {len(skipped)} existing files:')
        for f in skipped:
            print(f'  - {f}')

    # Run uv lock to create uv.lock for the generated pyproject.toml
    uv = shutil.which('uv')
    if uv:
        try:
            subprocess.run(
                [uv, 'lock'], cwd=project_dir, check=True, capture_output=True, text=True
            )
            print('Created uv.lock')
        except subprocess.CalledProcessError as e:
            print(f'Warning: uv lock failed: {e.stderr.strip()}', file=sys.stderr)
    else:
        print('Warning: uv not found — skipping uv.lock generation', file=sys.stderr)

    return 0


def _check_pi_installed() -> int:
    """Check that pi is installed and an API key is set."""
    pi_path = shutil.which('pi')
    if not pi_path:
        print("Error: 'pi' is not installed.", file=sys.stderr)
        print(
            'Install it with:\n  sudo npm install -g @earendil-works/pi-coding-agent',
            file=sys.stderr,
        )
        return 1

    # Check for at least one known API key env var
    known_keys = {
        'ANTHROPIC_API_KEY',
        'OPENAI_API_KEY',
        'GEMINI_API_KEY',
        'AZURE_OPENAI_API_KEY',
        'DEEPSEEK_API_KEY',
        'GROQ_API_KEY',
        'MISTRAL_API_KEY',
        'OPENROUTER_API_KEY',
        'FIREWORKS_API_KEY',
    }
    if not any(os.environ.get(k) for k in known_keys):
        print('Error: No API key found for pi.', file=sys.stderr)
        print(
            'Set one of the supported API key environment variables, e.g.:\n'
            '  export GEMINI_API_KEY=<your-key>\n'
            '  export ANTHROPIC_API_KEY=<your-key>',
            file=sys.stderr,
        )
        return 1

    print(f'Found pi at {pi_path}')
    print('API key configured.')
    return 0


def _is_valid_kebab_case(name: str) -> bool:
    """Check if the name is valid kebab-case."""
    if not name:
        return False
    if not name[0].isalpha():
        return False
    allowed = set('abcdefghijklmnopqrstuvwxyz0123456789-')
    return all(c in allowed for c in name)
