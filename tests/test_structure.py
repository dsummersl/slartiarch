from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from slarti import config as config_module
from slarti.checks import structure
from slarti.cli import app
from slarti.models import Models
from slarti.report import catalogue
from tests.test_cli import stub_context

FIXTURES = Path(__file__).parent / "data" / "structure"
RULES = [
    *(f"ATTACH-{n}" for n in range(1, 4)),
    "IDENT-1",
    "IDENT-2",
    *(f"DANGLE-{n}" for n in range(1, 5)),
    "DRAWN-1",
]

# An ambiguous attachment is only possible through an ambiguous declaration.
CO_FIRES = {"IDENT-2": {"IDENT-1"}}


def ids(findings: list) -> list[str]:
    return sorted(f.id for f in findings)


def fixture_models(tmp_path: Path, kind: str, rule: str) -> Models:
    text = (FIXTURES / kind / f"{rule}.yaml").read_text()
    schema, _, corpus = text.rpartition("\n---\n")
    files = {
        "schema/todo.yaml": schema or (FIXTURES / "schema.yaml").read_text(),
        "architecture/corpus.yaml": corpus,
    }
    for name, body in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(body, encoding="utf-8")
    (tmp_path / "slarti.toml").write_text(
        '[paths]\nlinkml = "schema"\ndocuments = []\ninstances = ["architecture"]\n',
        encoding="utf-8",
    )
    models = Models(config=config_module.load(tmp_path))
    assert models.instances.findings == []
    return models


@pytest.mark.parametrize("rule", RULES)
def test_invalid_fixture_fires_its_rule(tmp_path: Path, rule: str) -> None:
    findings = structure.check(fixture_models(tmp_path, "invalid", rule))
    assert rule in ids(findings)
    assert set(ids(findings)) <= {rule, *CO_FIRES.get(rule, set())}
    for finding in findings:
        assert finding.file and finding.subject and finding.remedy


@pytest.mark.parametrize("rule", RULES)
def test_valid_fixture_is_silent(tmp_path: Path, rule: str) -> None:
    assert structure.check(fixture_models(tmp_path, "valid", rule)) == []


def test_drawn_findings_point_at_the_diagram_source(tmp_path: Path) -> None:
    (finding,) = structure.check(fixture_models(tmp_path, "invalid", "DANGLE-1"))
    assert (finding.file, finding.line, finding.subject) == ("notes.md", 2, "d/queue")


def test_declared_ambiguity_points_at_the_element_file(tmp_path: Path) -> None:
    (finding,) = structure.check(fixture_models(tmp_path, "invalid", "IDENT-1"))
    assert finding.file == "architecture/corpus.yaml"
    assert finding.subject == "store"


def test_an_element_whose_own_id_is_its_alias_is_not_ambiguous(tmp_path: Path) -> None:
    models = fixture_models(tmp_path, "valid", "ATTACH-2")
    models.vocabulary.aliases["todo.api"] = ["todo.api", "api"]
    assert structure.check(models) == []


def test_drawn_is_inherited_by_subkinds(tmp_path: Path) -> None:
    models = fixture_models(tmp_path, "valid", "DRAWN-1")
    schema = models.config.root / "schema" / "todo.yaml"
    schema.write_text(
        schema.read_text().replace(
            "  Database:\n    is_a: Element\n", "  Database:\n    is_a: Service\n"
        ),
        encoding="utf-8",
    )
    findings = structure.check(Models(config=models.config))
    assert ids(findings) == ["DRAWN-1"]
    assert findings[0].subject == "todo.db"


def test_every_rule_is_in_the_catalogue() -> None:
    assert set(RULES) <= {c.id for c in catalogue()}


def test_report_lists_the_structure_checks(tmp_path: Path, monkeypatch) -> None:
    ctx = stub_context(tmp_path, constraints=[])
    monkeypatch.setattr("slarti.cli._context", lambda: ctx)
    payload = json.loads(CliRunner().invoke(app, ["report", "--json"]).stdout)
    checks = {c["id"]: c for c in payload["checks"]}
    assert all(checks[rule]["remedy"] for rule in RULES)
