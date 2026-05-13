"""Tests for dashcraft.config module."""

from __future__ import annotations

import pytest

from dashcraft.config import CharmPart, Config, ConfigError, _parse_parts, load_config
from tests.unit.helpers import MINIMAL_CONFIG, make_config


class TestParseParts:
    def test_parses_single_part(self) -> None:
        raw = {'charm': {'plugin': '-craft', 'upstream': 'https://example.com'}}
        parts = _parse_parts(raw)
        assert 'charm' in parts
        assert parts['charm'].plugin == '-craft'
        assert parts['charm'].upstream == 'https://example.com'

    def test_defaults(self) -> None:
        raw = {'charm': {}}
        parts = _parse_parts(raw)
        assert parts['charm'].plugin == '-craft'
        assert parts['charm'].upstream == ''
        assert parts['charm'].model == ''
        assert parts['charm'].language == ''

    def test_rejects_non_mapping_part(self) -> None:
        with pytest.raises(ConfigError) as exc_info:
            _parse_parts({'charm': 'not_a_dict'})
        assert 'must be a mapping' in str(exc_info.value)

    def test_parses_multiple_parts(self) -> None:
        raw = {
            'charm': {'upstream': 'https://a.com'},
            'libs': {'plugin': 'other'},
        }
        parts = _parse_parts(raw)
        assert set(parts.keys()) == {'charm', 'libs'}


class TestLoadConfig:
    def test_loads_minimal_config(self) -> None:
        with make_config(MINIMAL_CONFIG) as config_path:
            config = load_config(config_path)
        assert config.name == 'my-charm'
        assert config.summary == 'A test charm'
        assert config.type == 'charm'
        assert config.charm_part is not None
        assert config.charm_part.upstream == 'https://github.com/example/repo.git'
        assert config.charm_part.model == 'gpt-4'

    def test_raises_on_missing_file(self) -> None:
        with pytest.raises(ConfigError) as exc_info:
            load_config('/nonexistent/dashcraft.yaml')
        assert 'not found' in str(exc_info.value)

    def test_raises_on_invalid_yaml(self) -> None:
        with make_config(': :\n  bad yaml') as config_path:
            with pytest.raises(ConfigError) as exc_info:
                load_config(config_path)
        assert 'Failed to parse YAML' in str(exc_info.value)

    def test_raises_on_non_mapping_top_level(self) -> None:
        with make_config('- not\n- a\n- mapping') as config_path:
            with pytest.raises(ConfigError) as exc_info:
                load_config(config_path)
        assert 'must contain a YAML mapping' in str(exc_info.value)

    def test_raises_on_missing_name(self) -> None:
        content = """\
type: charm
parts:
  charm:
    plugin: -craft
    upstream: https://example.com
"""
        with make_config(content) as config_path, pytest.raises(ConfigError) as exc_info:
            load_config(config_path)
        assert "'name' is required" in str(exc_info.value)

    def test_raises_on_unsupported_type(self) -> None:
        content = """\
name: x
type: snap
parts:
  charm:
    plugin: -craft
    upstream: https://example.com
"""
        with make_config(content) as config_path, pytest.raises(ConfigError) as exc_info:
            load_config(config_path)
        assert "Only type 'charm' is supported" in str(exc_info.value)

    def test_raises_on_missing_charm_part(self) -> None:
        content = """\
name: x
parts:
  libs:
    plugin: dump
"""
        with make_config(content) as config_path, pytest.raises(ConfigError) as exc_info:
            load_config(config_path)
        assert "'charm' part is required" in str(exc_info.value)

    def test_raises_on_wrong_plugin(self) -> None:
        content = """\
name: x
type: charm
parts:
  charm:
    plugin: dump
    upstream: https://example.com
"""
        with make_config(content) as config_path, pytest.raises(ConfigError) as exc_info:
            load_config(config_path)
        assert "plugin must be '-craft'" in str(exc_info.value)

    def test_raises_on_missing_upstream(self) -> None:
        content = """\
name: x
type: charm
parts:
  charm:
    plugin: -craft
"""
        with make_config(content) as config_path, pytest.raises(ConfigError) as exc_info:
            load_config(config_path)
        assert "'upstream' is required" in str(exc_info.value)

    def test_parts_must_be_mapping(self) -> None:
        content = """\
name: x
parts: not_a_dict
"""
        with make_config(content) as config_path, pytest.raises(ConfigError) as exc_info:
            load_config(config_path)
        assert "'parts' must be a mapping" in str(exc_info.value)

    def test_empty_parts(self) -> None:
        content = """\
name: x
parts: {}
"""
        with make_config(content) as config_path, pytest.raises(ConfigError) as exc_info:
            load_config(config_path)
        assert "'charm' part is required" in str(exc_info.value)

    def test_charm_part_returns_none_when_missing(self) -> None:
        config = Config(name='x', parts={'libs': CharmPart()})
        assert config.charm_part is None
