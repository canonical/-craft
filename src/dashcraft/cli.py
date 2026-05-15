"""CLI interface for dashcraft."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from dashcraft.analysis import WorkloadAnalysis, analyse_workload
from dashcraft.config import Config, ConfigError, load_config
from dashcraft.pi import generate_charm
from dashcraft.templates import get_files, get_filled_files
from dashcraft.upstream import CloneError, clone_upstream_persistent

TMP_DIR_NAME = '.dashcraft-tmp'

# Environment variables that pi recognises as model-provider API keys. The
# CLI accepts any one of these as "configured."
KNOWN_API_KEYS = (
    'ANTHROPIC_API_KEY',
    'OPENAI_API_KEY',
    'GEMINI_API_KEY',
    'AZURE_OPENAI_API_KEY',
    'DEEPSEEK_API_KEY',
    'GROQ_API_KEY',
    'MISTRAL_API_KEY',
    'OPENROUTER_API_KEY',
    'FIREWORKS_API_KEY',
)


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
                for line in block['text'].rstrip().splitlines():
                    if line.strip():
                        print(f'    {line}', file=sys.stderr)

    elif etype == 'message_update':
        delta = event.get('assistantMessageEvent', {})
        if delta.get('type') == 'text_delta':
            # Assistant text is part of user-facing output; keep on stderr
            # to leave stdout for the packed-charm path and deploy hint.
            sys.stderr.write(delta['delta'])
            sys.stderr.flush()

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

    if args.command is None:
        # No subcommand given — show help. argparse convention: exit 0.
        parser.print_help()
        return 0

    if args.command != 'pack':  # pragma: no cover — argparse should reject
        parser.print_help()
        return 2

    return _cmd_pack(args)


def _cmd_pack(args: argparse.Namespace) -> int:
    """Execute the 'pack' command — scaffold and pack."""
    project_dir: Path = args.project_dir

    # Step 1: Load config
    try:
        config = load_config(project_dir)
    except ConfigError as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1

    charm_part = config.charm_part
    assert charm_part is not None  # validated by load_config

    print(f"Packing charm '{config.name}' from upstream: {charm_part.upstream}")

    # Step 2: Prepare working directory (sibling to dashcraft.yaml)
    tmp_dir = project_dir / TMP_DIR_NAME
    _ensure_clean_tmp(tmp_dir)
    print(f'Working directory: {tmp_dir}')

    try:
        return _run_pack(project_dir, tmp_dir, config)
    finally:
        _cleanup_tmp(tmp_dir, args.keep_source)


def _run_pack(project_dir: Path, tmp_dir: Path, config: Config) -> int:
    """Run the pack pipeline. Cleanup is handled by the caller."""
    charm_part = config.charm_part
    assert charm_part is not None

    source_dir = tmp_dir / 'upstream'
    charm_dir = tmp_dir / 'charm'

    # Clone upstream
    try:
        clone_upstream_persistent(charm_part.upstream, dest=source_dir)
        print(f'Cloned upstream to: {source_dir}')
    except CloneError as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1
    print(f'Upstream source ready at: {source_dir}')

    # Research the cloned workload deterministically so we can pre-fill
    # charmcraft.yaml and src/charm.py. Running this Python-side (rather
    # than as the agent's first tool call) saves a full LLM round-trip.
    analysis = analyse_workload(source_dir, config.name)
    _print_analysis_summary(analysis)

    # Scaffold charm files (filled from analysis).
    scaffold_ret = _do_scaffold(
        charm_dir,
        config.name,
        charm_part.workload,
        config.summary,
        config.description,
        analysis=analysis,
    )
    if scaffold_ret != 0:
        return scaffold_ret

    # Check if pi is available and generate charm code.
    pi_check_ret = _check_pi_installed()
    if pi_check_ret != 0:
        print('Skipping AI charm generation.', file=sys.stderr)
        return 1

    print('Generating charm code via pi RPC...')
    print(f'  Charm dir:    {charm_dir}', file=sys.stderr)
    print(f'  Workload dir: {source_dir}', file=sys.stderr)

    try:
        gen_result = generate_charm(
            config_obj=config,
            source_dir=source_dir,
            project_dir=charm_dir,
            analysis=analysis,
            on_event=_pi_event_handler,
        )
    except RuntimeError as e:
        print(f'Error: AI charm generation failed: {e}', file=sys.stderr)
        return 1

    if not gen_result.get('success'):
        err = gen_result.get('error', 'unknown error')
        print(f'Error: Charm generation failed: {err}', file=sys.stderr)
        return 1

    print('\nCharm generation complete.', file=sys.stderr)

    # Pack
    print('Packing charm...')
    pack_ret = _run_quickpack(charm_dir)
    if pack_ret != 0:
        return pack_ret

    # Move packed charm beside dashcraft.yaml, then print deploy hint
    charm_file = _find_charm_file(charm_dir)
    if charm_file:
        dest_charm = project_dir / charm_file.name
        shutil.move(str(charm_file), str(dest_charm))
        print(f'\nPacked charm saved to: {dest_charm}')
        deploy_cmd = _build_deploy_command(charm_dir, dest_charm, project_dir)
        print(f'Deploy with:\n  {deploy_cmd}')
    else:
        print('\nWarning: No .charm file found after packing.', file=sys.stderr)

    return 0


def _print_analysis_summary(analysis: WorkloadAnalysis) -> None:
    """Print a one-line workload-analysis summary to stderr."""
    bits = [f'name={analysis.name}', f'language={analysis.language}']
    if analysis.framework != 'none':
        bits.append(f'framework={analysis.framework}')
    if analysis.command:
        bits.append(f'command={analysis.command!r}')
    if analysis.port:
        bits.append(f'port={analysis.port}')
    if analysis.is_web_app:
        bits.append('web-app=yes')
    if analysis.needs_database:
        bits.append('database=yes')
    print('Workload analysis: ' + ' '.join(bits), file=sys.stderr)


def _ensure_clean_tmp(tmp_dir: Path) -> None:
    """Remove existing dashcraft tmp directory if present, then create fresh."""
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    tmp_dir.mkdir(parents=True, exist_ok=True)


def _cleanup_tmp(tmp_dir: Path, keep: bool) -> None:
    """Clean up the working directory unless --keep-source was given."""
    if not keep:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    else:
        print(f'(--keep-source: {tmp_dir} will not be cleaned up)')


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
    return Path(__file__).resolve().parent / '.pi'


def _do_scaffold(
    target_dir: Path,
    name: str,
    workload_image: str = '',
    summary: str = '',
    description: str = '',
    analysis: WorkloadAnalysis | None = None,
) -> int:
    """Scaffold charm files from templates into the project directory.

    When *analysis* is provided, ``charmcraft.yaml`` and ``src/charm.py`` are
    filled from it; otherwise the skeleton (TODO-laden) versions are used.
    """
    if not _is_valid_kebab_case(name):
        print(
            f'Error: Invalid charm name "{name}". Use kebab-case (e.g. "my-app").',
            file=sys.stderr,
        )
        return 1

    target_dir.mkdir(parents=True, exist_ok=True)

    if analysis is not None:
        files = get_filled_files(name, analysis, workload_image=workload_image)
    else:
        files = get_files(name, workload_image, summary, description)
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

    print(f'Scaffolded charm "{name}" into {target_dir}.')
    if created:
        print(f'Created {len(created)} files:')
        for f in created:
            print(f'  ✓ {f}')
    if skipped:
        print(f'Skipped {len(skipped)} existing files:')
        for f in skipped:
            print(f'  - {f}')

    # Run uv lock to create uv.lock for the generated pyproject.toml. The
    # downstream charmcraft uv-plugin needs this file at build time, so
    # treat its absence as fatal rather than a soft warning.
    uv = shutil.which('uv')
    if not uv:
        print(
            "Error: 'uv' is required to generate the charm's uv.lock. "
            'Install it from https://astral.sh/uv/install.sh',
            file=sys.stderr,
        )
        return 1
    try:
        subprocess.run([uv, 'lock'], cwd=target_dir, check=True, capture_output=True, text=True)
        print('Created uv.lock')
    except subprocess.CalledProcessError as e:
        print(f'Error: uv lock failed: {e.stderr.strip()}', file=sys.stderr)
        return e.returncode or 1

    return 0


def _find_charm_file(charm_dir: Path) -> Path | None:
    """Find the generated .charm file in the charm directory."""
    charm_files = sorted(charm_dir.glob('*.charm'))
    if not charm_files:
        return None
    # Return the most recently created .charm file
    return max(charm_files, key=lambda p: p.stat().st_mtime)


def _build_deploy_command(charm_dir: Path, charm_file: Path, project_dir: Path) -> str:
    """Build a juju deploy command string from the charm file and its metadata."""
    # Determine the charm path relative to the project dir for the user
    try:
        rel_charm = charm_file.relative_to(project_dir)
    except ValueError:
        rel_charm = charm_file
    charm_path = f'./{rel_charm}'

    # Parse charmcraft.yaml for resources
    resource_args: list[str] = []
    charmcraft_yaml = charm_dir / 'charmcraft.yaml'
    if charmcraft_yaml.exists():
        with open(charmcraft_yaml) as f:
            metadata = yaml.safe_load(f) or {}
        resources = metadata.get('resources', {})
        for res_name, res_def in resources.items():
            if isinstance(res_def, dict):
                upstream_source = res_def.get('upstream-source', '')
            else:
                upstream_source = ''
            resource_args.append(f'--resource {res_name}={upstream_source}')

    cmd_parts = ['juju deploy', charm_path, *resource_args]
    return ' '.join(cmd_parts)


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

    if not any(os.environ.get(k) for k in KNOWN_API_KEYS):
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
