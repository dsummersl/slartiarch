from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from linkml.validator import validate
from linkml_runtime import SchemaView
from typer.testing import CliRunner

import slarti
from slarti import vocabulary
from slarti.checks import ownership
from slarti.cli import app
from tests.conftest import SCHEMA, make_models
from tests.test_cli import stub_context

DATA = Path(__file__).parent / "data" / "vocabulary" / "c4"
PROJECT = DATA / "project.yaml"
PROFILE = vocabulary.PROFILES["slarti:c4"]
C4_CLASSES = {"Person", "SoftwareSystem", "Container", "Component", "Relationship"}

# The conftest schema, adopting the profile with one class of its own.
C4_SCHEMA = SCHEMA.replace("  - linkml:types\n", "  - linkml:types\n  - slarti:c4\n").replace(
    "classes:\n", "classes:\n  Database:\n    is_a: Container\n    annotations:\n"
    "      owner: todo.api\n",
)


def _errors(fixture: Path) -> list[str]:
    view = SchemaView(str(PROJECT), importmap=vocabulary.importmap())
    view.merge_imports()
    instance: dict[str, Any] = yaml.safe_load(fixture.read_text(encoding="utf-8"))
    return [r.message for r in validate(instance, view.schema, "Corpus").results]


def test_the_profile_ships_inside_the_package() -> None:
    assert PROFILE.is_file()
    assert PROFILE.parent == vocabulary.SCHEMA.parent
    assert vocabulary.importmap()["slarti:c4"] == str(PROFILE.with_suffix(""))


def test_the_profile_extends_the_architectural_layer() -> None:
    view = SchemaView(str(PROFILE), importmap=vocabulary.importmap())
    for name in C4_CLASSES - {"Relationship"}:
        assert view.class_ancestors(name) == [name, "Element"]
    assert view.class_ancestors("Relationship") == ["Relationship", "Relation"]


def test_a_project_imports_the_profile_from_its_own_schema() -> None:
    view = SchemaView(str(PROJECT), importmap=vocabulary.importmap())
    assert view.class_ancestors("Database") == ["Database", "Container", "Element"]


def test_a_project_without_the_profile_sees_no_c4_classes(tmp_path: Path) -> None:
    models = make_models(tmp_path)
    assert models.schema is not None
    assert not C4_CLASSES & set(models.schema.all_classes(imports=True))


@pytest.mark.parametrize("fixture", sorted((DATA / "valid").glob("*.yaml")), ids=str)
def test_valid_fixtures_conform(fixture: Path) -> None:
    assert _errors(fixture) == []


@pytest.mark.parametrize("fixture", sorted((DATA / "invalid").glob("*.yaml")), ids=str)
def test_invalid_fixtures_fail(fixture: Path) -> None:
    assert _errors(fixture)


def test_profile_classes_need_no_owner(tmp_path: Path) -> None:
    models = make_models(tmp_path, C4_SCHEMA, owns=("Task", "Database"))
    assert ownership.owned_classes(models) == ["Database", "Task"]
    assert ownership.check(models) == []


def test_project_classes_on_the_profile_still_need_an_owner(tmp_path: Path) -> None:
    findings = ownership.check(make_models(tmp_path, C4_SCHEMA, owns=("Task",)))
    assert [(f.id, f.subject) for f in findings] == [("OWN-3", "Database")]


def test_no_check_assumes_the_profile() -> None:
    checks = Path(slarti.__file__).parent / "checks"
    for module in checks.glob("*.py"):
        text = module.read_text(encoding="utf-8")
        assert "slarti:c4" not in text and "PROFILES" not in text, module
        assert not any(f"'{name}'" in text or f'"{name}"' in text for name in C4_CLASSES)


def test_doctor_reports_the_profile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "slarti.toml").write_text("", encoding="utf-8")
    result = CliRunner().invoke(app, ["doctor"])
    assert "import as 'slarti:c4'" in result.stdout
    assert str(PROFILE) in result.stdout


def test_report_json_lists_the_profile(tmp_path: Path, monkeypatch) -> None:
    ctx = stub_context(tmp_path, constraints=[])
    monkeypatch.setattr("slarti.cli._context", lambda: ctx)
    payload = json.loads(CliRunner().invoke(app, ["report", "--json"]).stdout)
    assert payload["vocabulary"]["profiles"] == vocabulary.profile_versions()
    assert "slarti:c4" in payload["vocabulary"]["profiles"]
