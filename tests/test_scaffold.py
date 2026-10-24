from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from slarti import config as config_module
from slarti import scaffold
from slarti.cli import app

needs_linkml = pytest.mark.skipif(shutil.which("linkml") is None, reason="LinkML is not installed")


def digest(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_init_scaffolds_the_convention(tmp_path: Path) -> None:
    result = scaffold.init(tmp_path)
    assert "slarti.toml" in result.written
    assert (tmp_path / "docs/slarti/instances/architecture.yaml").is_file()
    assert (tmp_path / "docs/diagrams").is_dir()
    assert result.skipped == []


def test_init_scaffolds_no_likec4_by_default(tmp_path: Path) -> None:
    scaffold.init(tmp_path)
    cfg = config_module.load(tmp_path)
    assert not (tmp_path / "docs/slarti/likec4").exists()
    assert not cfg.likec4_enabled()
    assert cfg.instances == ["docs/slarti/instances"]
    assert "diagram:" not in (tmp_path / "docs/architecture.md").read_text(encoding="utf-8")


def test_init_scaffolds_likec4_on_request(tmp_path: Path) -> None:
    scaffold.init(tmp_path, likec4=True)
    cfg = config_module.load(tmp_path)
    assert (tmp_path / "docs/slarti/likec4/example.c4").is_file()
    assert cfg.likec4_enabled()
    assert cfg.instances == []
    assert "diagram:index" in (tmp_path / "docs/architecture.md").read_text(encoding="utf-8")


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


def _without_node() -> str:
    """A PATH holding only this interpreter's tools, so nothing provides Node."""
    return str(Path(sys.executable).parent)


@needs_linkml
def test_scaffold_checks_and_docs_without_node(tmp_path: Path, monkeypatch) -> None:
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv("PATH", _without_node())
    assert shutil.which("node") is None and shutil.which("npx") is None
    monkeypatch.chdir(project)
    runner = CliRunner()
    assert runner.invoke(app, ["init"]).exit_code == 0
    doctor = runner.invoke(app, ["doctor"])
    assert doctor.exit_code == 0, doctor.stdout
    assert "skip node" in doctor.stdout and "skip likec4" in doctor.stdout
    assert runner.invoke(app, ["docs"]).exit_code == 0
    check = runner.invoke(app, ["check"])
    assert check.exit_code == 0, check.stdout
    assert runner.invoke(app, ["docs", "--check"]).exit_code == 0
