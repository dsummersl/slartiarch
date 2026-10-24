from __future__ import annotations

import hashlib
from pathlib import Path

from slarti import config as config_module
from slarti import scaffold


def digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_init_scaffolds_the_convention(tmp_path: Path) -> None:
    result = scaffold.init(tmp_path)
    assert "slarti.toml" in result.written
    assert (tmp_path / "docs/slarti/likec4/example.c4").is_file()
    assert result.skipped == []


def test_init_never_overwrites(tmp_path: Path) -> None:
    (tmp_path / "slarti.toml").write_text("mine", encoding="utf-8")
    before = digest(tmp_path)
    result = scaffold.init(tmp_path)
    assert "slarti.toml" in result.skipped
    assert (tmp_path / "slarti.toml").read_text(encoding="utf-8") == "mine"
    assert before["slarti.toml"] == digest(tmp_path)["slarti.toml"]


def test_init_is_idempotent(tmp_path: Path) -> None:
    scaffold.init(tmp_path)
    first = digest(tmp_path)
    scaffold.init(tmp_path)
    assert digest(tmp_path) == first


def test_scaffolded_config_loads(tmp_path: Path) -> None:
    scaffold.init(tmp_path)
    cfg = config_module.load(tmp_path)
    assert cfg.root == tmp_path
    assert cfg.documents == ["docs/architecture.md"]
