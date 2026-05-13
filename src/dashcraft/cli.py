"""CLI interface for dashcraft."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from dashcraft.config import ConfigError, load_config
from dashcraft.templates import get_files
from dashcraft.upstream import CloneError, clone_upstream_persistent
from quickpack.pack import quick_pack

CONFIG_FILENAME = 'dashcraft.yaml'


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='dashcraft',
        description='AI-powered charm generator — charming, but fast.',
    )
    parser.add_argument(
        '--project-dir',
        type=Path,
        default=Path.cwd(),
        help='Project directory containing dashcraft.yaml (default: CWD)',
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
    """Entry point for the dashcraft CLI."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command != 'pack':
        parser.print_help()
        return 1

    return _cmd_pack(args)


def _cmd_pack(args: argparse.Namespace) -> int:
    """Execute the 'pack' command — scaffold and pack."""
    project_dir = args.project_dir
    config_path = project_dir / CONFIG_FILENAME

    # Step 1: Load config
    try:
        config = load_config(config_path)
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

    # TODO: Analyze source, generate charm
    print('Upstream source ready. (Charm generation not yet implemented.)')

    # Step 3: Scaffold charm files if charmcraft.yaml doesn't exist
    if not (project_dir / 'charmcraft.yaml').exists():
        scaffold_ret = _do_scaffold(project_dir, config.name, charm_part.workload)
        if scaffold_ret != 0:
            _cleanup_source(source_dir, args.keep_source)
            return scaffold_ret

    # Step 4: Pack
    print('Packing charm...')
    pack_ret = _run_quickpack(project_dir)

    _cleanup_source(source_dir, args.keep_source)

    return pack_ret


def _cleanup_source(source_dir: Path, keep: bool) -> None:
    """Clean up the cloned upstream source unless --keep-source was given."""
    if not keep:
        shutil.rmtree(source_dir, ignore_errors=True)


def _run_quickpack(cwd: Path) -> int:
    """Run quickpack in the given directory."""
    try:
        charm_path = quick_pack(cwd)
        print(f'Created {charm_path.name}')
        return 0
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as e:
        print(f'quickpack failed: {e}', file=sys.stderr)
        return 1


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


def _is_valid_kebab_case(name: str) -> bool:
    """Check if the name is valid kebab-case."""
    if not name:
        return False
    if not name[0].isalpha():
        return False
    allowed = set('abcdefghijklmnopqrstuvwxyz0123456789-')
    return all(c in allowed for c in name)
