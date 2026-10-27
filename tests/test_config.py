from __future__ import annotations

from pathlib import Path

import pytest

from slarti import config as config_module


def test_defaults_apply_when_unstated(tmp_path: Path) -> None:
    (tmp_path / "slarti.toml").write_text('[paths]\nlikec4 = "src/arch"\n', encoding="utf-8")
    cfg = config_module.load(tmp_path)
    assert cfg.paths["likec4"] == "src/arch"
    assert cfg.paths["linkml"] == "docs/slarti/linkml"


def test_config_is_found_from_a_subdirectory(tmp_path: Path) -> None:
    (tmp_path / "slarti.toml").write_text("[paths]\n", encoding="utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert config_module.load(nested).root == tmp_path


def test_missing_config_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(config_module.ConfigError):
        config_module.load(tmp_path)


def test_unknown_keys_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "slarti.toml").write_text('[paths]\ntheme = "dark"\n', encoding="utf-8")
    with pytest.raises(config_module.ConfigError, match="theme"):
        config_module.load(tmp_path)


def test_checks_name_the_kinds_that_must_be_drawn(tmp_path: Path) -> None:
    (tmp_path / "slarti.toml").write_text('[checks]\ndrawn = ["Container"]\n',
                                          encoding="utf-8")
    assert config_module.load(tmp_path).drawn == ["Container"]


def test_unknown_check_keys_are_rejected(tmp_path: Path) -> None:
    (tmp_path / "slarti.toml").write_text('[checks]\nstrict = true\n', encoding="utf-8")
    with pytest.raises(config_module.ConfigError, match="strict"):
        config_module.load(tmp_path)


def test_rel_is_relative_to_the_root(tmp_path: Path) -> None:
    cfg = config_module.Config(root=tmp_path)
    assert cfg.rel(tmp_path / "docs" / "slarti" / "x.yaml") == "docs/slarti/x.yaml"


def test_pyproject_toml_fallback(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[tool.slartiarch.paths]\nlikec4 = "src/arch"\n', encoding="utf-8"
    )
    cfg = config_module.load(tmp_path)
    assert cfg.root == tmp_path
    assert cfg.paths["likec4"] == "src/arch"
    assert cfg.paths["linkml"] == "docs/slarti/linkml"


def test_slarti_toml_precedes_pyproject(tmp_path: Path) -> None:
    (tmp_path / "slarti.toml").write_text('[paths]\nlikec4 = "from-toml"\n', encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(
        '[tool.slartiarch.paths]\nlikec4 = "from-pyproject"\n', encoding="utf-8"
    )
    cfg = config_module.load(tmp_path)
    assert cfg.paths["likec4"] == "from-toml"


def test_missing_pyproject_section_is_an_error(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project]\nname = 'foo'\n", encoding="utf-8")
    with pytest.raises(config_module.ConfigError):
        config_module.load(tmp_path)


def test_mermaid_inputs_enable_the_mermaid_adapter(tmp_path: Path) -> None:
    (tmp_path / "slarti.toml").write_text("[paths]\n", encoding="utf-8")
    assert not config_module.load(tmp_path).mermaid_enabled()
    (tmp_path / "slarti.toml").write_text('[paths]\nmermaid = "docs/a.md"\n', encoding="utf-8")
    cfg = config_module.load(tmp_path)
    assert cfg.mermaid == ["docs/a.md"] and cfg.mermaid_enabled()
