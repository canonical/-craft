"""Parse and validate dashcraft.yaml configuration files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

CONFIG_FILENAMES = ('dashcraft.yaml', '-craft.yaml')


@dataclass
class CharmPart:
    """Represents a charm part in the dashcraft.yaml."""

    plugin: str = '-craft'
    upstream: str = ''
    workload: str = ''
    model: str = ''
    language: str = ''


@dataclass
class Config:
    """Parsed dashcraft.yaml configuration."""

    name: str = ''
    summary: str = ''
    description: str = ''
    type: str = 'charm'
    parts: dict[str, CharmPart] = field(default_factory=dict)

    @property
    def charm_part(self) -> CharmPart | None:
        """Return the charm part if it exists."""
        return self.parts.get('charm')


class ConfigError(Exception):
    """Raised when the configuration is invalid."""

    pass


def _parse_parts(raw_parts: dict[str, Any]) -> dict[str, CharmPart]:
    """Parse the parts section of the config."""
    parts: dict[str, CharmPart] = {}
    for name, attrs in raw_parts.items():
        if not isinstance(attrs, dict):
            raise ConfigError(f"Part '{name}' must be a mapping, got {type(attrs).__name__}")
        parts[name] = CharmPart(
            plugin=attrs.get('plugin', '-craft'),
            upstream=attrs.get('upstream', ''),
            workload=attrs.get('workload', ''),
            model=attrs.get('model', ''),
            language=attrs.get('language', ''),
        )
    return parts


def _resolve_config_path(directory: Path) -> Path:
    """Find the config file in ``directory``, accepting either filename."""
    for name in CONFIG_FILENAMES:
        candidate = directory / name
        if candidate.exists():
            return candidate
    names = ' or '.join(CONFIG_FILENAMES)
    raise ConfigError(f'Config file not found in {directory}: expected {names}')


def load_config(path: Path | str | None = None) -> Config:
    """Load and validate a dashcraft config file.

    Args:
        path: Path to the config file, or a directory to search in. Defaults
            to the CWD. When a directory is given (or ``path`` is ``None``),
            looks for ``dashcraft.yaml`` first, then ``-craft.yaml``.

    Returns:
        Parsed Config object.

    Raises:
        ConfigError: If the config file is missing or invalid.
    """
    if path is None:
        path = _resolve_config_path(Path.cwd())
    else:
        path = Path(path)
        if path.is_dir():
            path = _resolve_config_path(path)
        elif not path.exists():
            raise ConfigError(f'Config file not found: {path}')

    try:
        with open(path) as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f'Failed to parse YAML: {e}') from e

    if not isinstance(raw, dict):
        raise ConfigError('Config file must contain a YAML mapping at the top level')

    raw_parts = raw.pop('parts', {})
    if not isinstance(raw_parts, dict):
        raise ConfigError("'parts' must be a mapping")

    parts = _parse_parts(raw_parts)

    config = Config(
        name=raw.get('name', ''),
        summary=raw.get('summary', ''),
        description=raw.get('description', ''),
        type=raw.get('type', 'charm'),
        parts=parts,
    )

    # Validate required fields
    if not config.name:
        raise ConfigError("'name' is required in dashcraft.yaml")
    if config.type != 'charm':
        raise ConfigError(f"Only type 'charm' is supported, got '{config.type}'")

    charm = config.charm_part
    if charm is None:
        raise ConfigError("A 'charm' part is required in dashcraft.yaml")
    if charm.plugin != '-craft':
        raise ConfigError(f"Charm part plugin must be '-craft', got '{charm.plugin}'")
    if not charm.upstream:
        raise ConfigError("'upstream' is required in the charm part")

    return config
