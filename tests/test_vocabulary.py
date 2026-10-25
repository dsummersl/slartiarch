from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from linkml.validator import validate
from linkml_runtime import SchemaView
from typer.testing import CliRunner

from slarti import generate, vocabulary
from slarti.cli import app
from slarti.models import Models
from tests.conftest import make_config
from tests.test_cli import stub_context

DATA = Path(__file__).parent / "data" / "vocabulary"
PROJECT = DATA / "project.yaml"


def _errors(fixture: Path, schema: Path = PROJECT) -> list[str]:
    view = SchemaView(str(schema), importmap=vocabulary.importmap())
    view.merge_imports()
    instance: dict[str, Any] = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    return [r.message for r in validate(instance, view.schema, "Corpus").results]


def test_the_schema_ships_inside_the_package() -> None:
    assert vocabulary.SCHEMA.is_file()
    assert vocabulary.SCHEMA.parent == Path(vocabulary.__file__).parent


def test_version_is_the_schema_version() -> None:
    raw = yaml.safe_load(vocabulary.SCHEMA.read_text(encoding="utf-8"))
    assert vocabulary.version() == raw["version"]


def test_a_project_schema_extends_the_architectural_layer() -> None:
    view = SchemaView(str(PROJECT), importmap=vocabulary.importmap())
    assert view.class_ancestors("Service") == ["Service", "Element"]
    assert view.class_ancestors("Reads") == ["Reads", "Relation"]
    assert {"Diagram", "Node", "Edge", "SourceLocation"} <= set(view.all_classes())


def test_models_resolve_the_vocabulary_import(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    (config.path("linkml") / "todo.yaml").write_text(PROJECT.read_text(), encoding="utf-8")
    models = Models(config=config)
    assert models.schema is not None
    assert "Element" in models.schema.class_ancestors("Database")


@pytest.mark.skipif(shutil.which("gen-erdiagram") is None, reason="LinkML is not installed")
def test_the_er_diagram_shows_the_project_not_the_vocabulary(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    (config.path("linkml") / "todo.yaml").write_text(PROJECT.read_text(), encoding="utf-8")
    block = generate.linkml_erd_block(Models(config=config))
    assert "Service {" in block and "Database {" in block
    assert "Corpus {" not in block


def test_the_structural_layer_stands_alone() -> None:
    assert _errors(DATA / "valid" / "structure_only.yaml", vocabulary.SCHEMA) == []


@pytest.mark.parametrize("fixture", sorted((DATA / "valid").glob("*.yaml")), ids=str)
def test_valid_fixtures_conform(fixture: Path) -> None:
    assert _errors(fixture) == []


@pytest.mark.parametrize("fixture", sorted((DATA / "invalid").glob("*.yaml")), ids=str)
def test_invalid_fixtures_fail(fixture: Path) -> None:
    assert _errors(fixture)


def test_doctor_reports_the_vocabulary_version(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "slarti.toml").write_text("", encoding="utf-8")
    result = CliRunner().invoke(app, ["doctor"])
    assert f"vocabulary {vocabulary.version()}" in result.stdout
    assert vocabulary.IMPORT in result.stdout


def test_report_json_carries_the_vocabulary_version(tmp_path: Path, monkeypatch) -> None:
    ctx = stub_context(tmp_path, constraints=[])
    monkeypatch.setattr("slarti.cli._context", lambda: ctx)
    payload = json.loads(CliRunner().invoke(app, ["report", "--json"]).stdout)
    assert payload["vocabulary"]["import"] == "slarti:vocabulary"
    assert payload["vocabulary"]["version"] == vocabulary.version()
