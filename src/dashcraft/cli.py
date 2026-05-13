"""CLI interface for dashcraft."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dashcraft.config import ConfigError, load_config
from dashcraft.upstream import CloneError, clone_upstream


CONFIG_FILENAME = "dashcraft.yaml"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dashcraft",
        description="AI-powered charm generator — charming, but fast.",
    )
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path.cwd(),
        help="Project directory containing dashcraft.yaml (default: CWD)",
    )
    subparsers = parser.add_subparsers(dest="command")

    # pack command
    subparsers.add_parser(
        "pack", help="Generate and pack a charm for the upstream workload"
    )

    return parser


def main() -> int:
    """Entry point for the dashcraft CLI."""
    parser = _build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 1

    if args.command == "pack":
        return _cmd_pack(args)

    parser.print_help()
    return 1


def _cmd_pack(args: argparse.Namespace) -> int:
    """Execute the 'pack' command."""
    config_path = args.project_dir / CONFIG_FILENAME
    print(f"Project directory: {args.project_dir}")

    try:
        config = load_config(config_path)
    except ConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    charm_part = config.charm_part
    assert charm_part is not None  # validated by load_config

    print(f"Packing charm '{config.name}' from upstream: {charm_part.upstream}")

    try:
        with clone_upstream(charm_part.upstream) as source_dir:
            print(f"Cloned upstream to: {source_dir}")
            # TODO: Analyze source, generate charm, pack it
            print("Upstream source ready. (Charm generation not yet implemented.)")
    except CloneError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    return 0
