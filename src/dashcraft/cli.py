"""CLI interface for dashcraft."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from quickpack.pack import quick_pack

from dashcraft.config import ConfigError, load_config
from dashcraft.templates import get_files
from dashcraft.upstream import CloneError, clone_upstream

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

    # pack command
    subparsers.add_parser('pack', help='Generate and pack a charm for the upstream workload')

    # charm-init command
    init_parser = subparsers.add_parser(
        'charm-init', help='Scaffold a new Juju charm from a template'
    )
    init_parser.add_argument('name', help='Charm name in kebab-case')
    init_parser.add_argument(
        '--workload',
        default='',
        help='OCI image reference for the workload (optional)',
    )
    init_parser.add_argument(
        '--directory',
        default='',
        help='Target directory (default: ./<name>)',
    )
    init_parser.add_argument(
        '--force',
        action='store_true',
        help='Skip existing files instead of failing',
    )

    # lint command
    subparsers.add_parser('lint', help='Lint the charm code (tox run -e lint)')

    # test command
    test_parser = subparsers.add_parser('test', help='Run charm tests')
    test_parser.add_argument('--unit', action='store_true', help='Run unit tests only')
    test_parser.add_argument(
        '--integration', action='store_true', help='Run integration tests only'
    )

    return parser


def main() -> int:
    """Entry point for the dashcraft CLI."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == 'pack':
        return _cmd_pack(args)

    if args.command == 'charm-init':
        return _cmd_charm_init(args)

    if args.command == 'lint':
        return _cmd_lint(args)

    if args.command == 'test':
        return _cmd_test(args)

    parser.print_help()
    return 1


def _cmd_pack(args: argparse.Namespace) -> int:
    """Execute the 'pack' command."""
    config_path = args.project_dir / CONFIG_FILENAME
    print(f'Project directory: {args.project_dir}')

    try:
        config = load_config(config_path)
    except ConfigError as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1

    charm_part = config.charm_part
    assert charm_part is not None  # validated by load_config

    print(f"Packing charm '{config.name}' from upstream: {charm_part.upstream}")

    try:
        with clone_upstream(charm_part.upstream) as source_dir:
            print(f'Cloned upstream to: {source_dir}')
            print('Upstream source ready. (Charm generation not yet implemented.)')

            if (args.project_dir / 'charmcraft.yaml').exists():
                print('Found charmcraft.yaml — running quickpack...')
                return _run_quickpack(args.project_dir)

    except CloneError as e:
        print(f'Error: {e}', file=sys.stderr)
        return 1

    return 0


def _run_quickpack(cwd: Path) -> int:
    """Run quickpack in the given directory."""
    try:
        charm_path = quick_pack(cwd)
        print(f'Created {charm_path.name}')
        return 0
    except (FileNotFoundError, ValueError, RuntimeError, OSError) as e:
        print(f'quickpack failed: {e}', file=sys.stderr)
        print('Falling back to charmcraft pack...')
        return _run_charmcraft_pack(cwd)


def _run_charmcraft_pack(cwd: Path) -> int:
    """Run charmcraft pack in the given directory as a fallback."""
    charmcraft = shutil.which('charmcraft')
    if not charmcraft:
        print(
            'Error: charmcraft is not installed. '
            'Install it with: sudo snap install charmcraft --classic',
            file=sys.stderr,
        )
        return 1

    try:
        subprocess.run(
            [charmcraft, 'pack'],
            cwd=cwd,
            check=True,
        )
        return 0
    except subprocess.CalledProcessError as e:
        print(f'charmcraft pack failed: {e}', file=sys.stderr)
        return 1


def _cmd_charm_init(args: argparse.Namespace) -> int:
    """Execute the 'charm-init' command."""
    name = args.name.strip()
    if not name or not _is_valid_kebab_case(name):
        print(
            f'Error: Invalid charm name "{name}". Use kebab-case (e.g. "my-app").',
            file=sys.stderr,
        )
        return 1

    subdir = args.directory.strip() or f'./{name}'
    target_dir = Path.cwd() / subdir
    workload_image = args.workload.strip() if args.workload else ''

    if target_dir.exists() and any(target_dir.iterdir()) and not args.force:
        print(
            f'Error: Directory "{subdir}" already contains files. '
            'Use --force to skip existing files, or choose a different directory.',
            file=sys.stderr,
        )
        return 1

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

    print(f'Charm "{name}" scaffolded in {subdir}.')
    if created:
        print(f'\nCreated {len(created)} files:')
        for f in created:
            print(f'  ✓ {f}')
    if skipped:
        print(f'\nSkipped {len(skipped)} existing files:')
        for f in skipped:
            print(f'  - {f}')
    print('\nNext: review charmcraft.yaml and src/charm.py, then run `dashcraft pack` to build.')

    return 0


def _is_valid_kebab_case(name: str) -> bool:
    """Check if the name is valid kebab-case."""
    if not name:
        return False
    if not name[0].isalpha():
        return False
    allowed = set('abcdefghijklmnopqrstuvwxyz0123456789-')
    return all(c in allowed for c in name)


def _cmd_lint(args: argparse.Namespace) -> int:
    """Execute the 'lint' command."""
    cwd = args.project_dir

    tox = shutil.which('tox')
    if not tox:
        print(
            'Error: tox is not installed. Install it with: uv tool install tox',
            file=sys.stderr,
        )
        return 1

    try:
        subprocess.run(
            [tox, 'run', '-e', 'lint'],
            cwd=cwd,
            check=True,
        )
        return 0
    except subprocess.CalledProcessError as e:
        print(f'Lint failed: {e}', file=sys.stderr)
        return 1


def _cmd_test(args: argparse.Namespace) -> int:
    """Execute the 'test' command."""
    cwd = args.project_dir

    tox = shutil.which('tox')
    if not tox:
        print(
            'Error: tox is not installed. Install it with: uv tool install tox',
            file=sys.stderr,
        )
        return 1

    env = 'unit' if args.unit else 'integration' if args.integration else 'unit'

    try:
        subprocess.run(
            [tox, 'run', '-e', env],
            cwd=cwd,
            check=True,
        )
        return 0
    except subprocess.CalledProcessError as e:
        print(f'Tests failed: {e}', file=sys.stderr)
        return 1
