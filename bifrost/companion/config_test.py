"""Tests for bifrost/companion/config.py"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from bifrost.companion.config import DEFAULTS, load_config


# ── fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_config_dir():
    """Yield a temporary directory that gets cleaned up after the test."""
    with tempfile.TemporaryDirectory() as tmp:
        yield Path(tmp)


# ── default behaviour ─────────────────────────────────────────────────────


def test_load_config_returns_simplenamespace():
    cfg = load_config()
    assert isinstance(cfg, SimpleNamespace)


def test_load_config_defaults():
    cfg = load_config()
    for key, value in DEFAULTS.items():
        assert getattr(cfg, key) == value, f"Mismatch for {key}"


def test_default_context_tokens():
    cfg = load_config()
    assert cfg.max_context_tokens == 8000


def test_default_cost_ceiling():
    cfg = load_config()
    assert cfg.cost_ceiling_default == 1.00


# ── XDG path resolution ──────────────────────────────────────────────────


def test_xdg_config_home_is_used_when_set(monkeypatch):
    with tempfile.TemporaryDirectory() as tmp:
        xdg_dir = Path(tmp) / "bifrost"
        xdg_dir.mkdir(parents=True)
        config_file = xdg_dir / "config.yaml"
        config_file.write_text("max_context_tokens: 4000\n")

        monkeypatch.setenv("XDG_CONFIG_HOME", tmp)
        cfg = load_config()
        assert cfg.max_context_tokens == 4000


def test_fallback_to_dot_bifrost(monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    cfg = load_config()
    assert isinstance(cfg, SimpleNamespace)
    assert cfg.max_context_tokens == 8000


# ── explicit path ─────────────────────────────────────────────────────────


def test_explicit_path(tmp_config_dir):
    config_file = tmp_config_dir / "config.yaml"
    config_file.write_text("model_for_classifier: gpt-4\n")
    cfg = load_config(config_file)
    assert cfg.model_for_classifier == "gpt-4"


def test_explicit_path_missing_raises():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/bifrost/config.yaml")


# ── partial overrides ─────────────────────────────────────────────────────


def test_partial_override(tmp_config_dir):
    config_file = tmp_config_dir / "config.yaml"
    config_file.write_text("max_context_tokens: 999\n")
    cfg = load_config(config_file)
    assert cfg.max_context_tokens == 999
    assert cfg.model_for_classifier == DEFAULTS["model_for_classifier"]


# ── validation ────────────────────────────────────────────────────────────


def test_allowlisted_commands_must_be_list_of_strings(tmp_config_dir):
    config_file = tmp_config_dir / "config.yaml"
    config_file.write_text("allowlisted_bash_commands: [42, 'ls']\n")
    with pytest.raises(ValueError, match="list of strings"):
        load_config(config_file)


def test_allowlisted_commands_not_a_list(tmp_config_dir):
    config_file = tmp_config_dir / "config.yaml"
    config_file.write_text("allowlisted_bash_commands: 'ls'\n")
    with pytest.raises(ValueError, match="list of strings"):
        load_config(config_file)


# ── malformed YAML ────────────────────────────────────────────────────────


def test_malformed_yaml_raises_clear_error(tmp_config_dir):
    config_file = tmp_config_dir / "config.yaml"
    config_file.write_text("key: [unclosed list\n")
    with pytest.raises(yaml.YAMLError):
        load_config(config_file)
