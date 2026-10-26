from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from slarti import runner
from slarti.checks import delegated
from slarti.cli import app
from slarti.findings import Finding, Report
from slarti.proc import Result
from slarti.registry import Constraint, Enforcer
from tests.conftest import make_models

RUNNER = CliRunner()


def test_init_scaffolds_and_reports(tmp_path: Path) -> None:
    result = RUNNER.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0
    assert "created slarti.toml" in result.stdout


def test_report_lists_rules_shapes_and_checks(tmp_path: Path, monkeypatch) -> None:
    ctx = stub_context(tmp_path, constraints=[_constraint()])
    monkeypatch.setattr("slarti.cli._context", lambda: ctx)
    result = RUNNER.invoke(app, ["report"])
    assert result.exit_code == 0
    assert "C1" in result.stdout
    assert "OWN-3" in result.stdout


def test_report_json_is_fully_detailed(tmp_path: Path, monkeypatch) -> None:
    ctx = stub_context(tmp_path, constraints=[_constraint()])
    monkeypatch.setattr("slarti.cli._context", lambda: ctx)
    result = RUNNER.invoke(app, ["report", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    rule = payload["constraints"][0]
    assert rule["id"] == "C1"
    assert rule["enforcer"]["kind"] == "linkml_class"
    assert rule["enforcer"]["resolves"] is True
    assert payload["linkml_ownership"] == [
        {"class": "Task", "owner": "todo.api", "claimed_by": ["todo.api"]}
    ]
    assert any(c["id"] == "OWN-3" and c["remedy"] for c in payload["checks"])
    assert payload["summary"]["enforced"] == 1


def _constraint() -> Constraint:
    enforcer = Enforcer(kind="linkml_class", ref="Task", fixture=None, fixture_class=None)
    return Constraint(id="C1", statement="Tasks exist.", enforced_by=enforcer, line=3)


def test_check_without_a_project_is_an_environment_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = RUNNER.invoke(app, ["check"])
    assert result.exit_code == 2
    assert "slarti init" in result.stdout + str(result.stderr)


def stub_context(tmp_path: Path, constraints=()) -> runner.Context:
    models = make_models(tmp_path)
    models.config.path("constraints").write_text("constraints: []\n", encoding="utf-8")
    return runner.Context(config=models.config, models=models, constraints=list(constraints))


def test_check_reports_findings_and_exits_one(tmp_path: Path, monkeypatch) -> None:
    ctx = stub_context(tmp_path)
    monkeypatch.setattr("slarti.cli._context", lambda: ctx)
    finding = Finding(id="OWN-1", severity="error", file="f", subject="Task",
                      message="class 'Task' has no owner.", remedy="Add an owner.")
    monkeypatch.setattr(runner, "check", lambda ctx, include_docs=True: (_report(finding), True))
    result = RUNNER.invoke(app, ["check"])
    assert result.exit_code == 1
    assert "OWN-1" in result.stdout


def test_check_fix_regenerates_stale_regions(tmp_path: Path, monkeypatch) -> None:
    ctx = stub_context(tmp_path)
    document = ctx.config.document_paths()[0]
    document.write_text("<!-- slarti:begin unverified -->\n<!-- slarti:end unverified -->\n",
                        encoding="utf-8")
    monkeypatch.setattr("slarti.cli._context", lambda: ctx)
    monkeypatch.setattr(runner, "check", lambda ctx, include_docs=True: (Report(), True))
    result = RUNNER.invoke(app, ["check", "--fix"])
    assert result.exit_code == 0
    assert "No rules are declared." in document.read_text(encoding="utf-8")


def _report(finding: Finding) -> Report:
    return Report([finding], checked=1)


def test_delegated_failures_fail_the_run(tmp_path: Path, monkeypatch) -> None:
    ctx = stub_context(tmp_path)
    monkeypatch.setattr("slarti.cli._context", lambda: ctx)
    monkeypatch.setattr(runner, "check", lambda ctx, include_docs=True: (Report(), False))
    assert RUNNER.invoke(app, ["check"]).exit_code == 1


def test_check_json_keeps_delegated_output_off_stdout(tmp_path: Path, monkeypatch) -> None:
    ctx = stub_context(tmp_path)
    monkeypatch.setattr("slarti.cli._context", lambda: ctx)
    failure = delegated.Delegation("linkml", ["linkml"], Result(1, "lint says no\n", ""))

    def check(ctx, include_docs=True):  # noqa: ANN001, ANN202 - test double
        return Report(), delegated.report([failure]) == 0

    monkeypatch.setattr(runner, "check", check)
    result = RUNNER.invoke(app, ["check", "--json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["findings"] == []
    assert "lint says no" in result.stderr
    assert "delegated validation failed" in result.stderr


def test_delegated_diagnostics_pass_through(capsys) -> None:
    failure = delegated.Delegation("likec4", ["likec4"], Result(1, "out\n", "err\n"))
    assert delegated.report([failure]) == 1
    captured = capsys.readouterr()
    assert captured.out == "out\n"
    assert captured.err == "err\n"


def test_passing_delegations_say_nothing(capsys) -> None:
    ok = delegated.Delegation("likec4", ["likec4"], Result(0, "quiet\n", ""))
    assert delegated.report([ok]) == 0
    assert capsys.readouterr().out == ""


def test_doctor_probes_node_only_for_likec4_projects(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("slarti.proc.run", lambda argv, cwd=None: Result(0, "v1.60.0", ""))
    RUNNER.invoke(app, ["init"])
    assert "skip node" in RUNNER.invoke(app, ["doctor"]).stdout
    (tmp_path / "docs/slarti/likec4").mkdir()
    (tmp_path / "docs/slarti/likec4/model.c4").write_text("model {}\n", encoding="utf-8")
    doctor = RUNNER.invoke(app, ["doctor"]).stdout
    assert "skip node" not in doctor
    assert "ok   likec4" in doctor


def test_report_says_when_no_shape_is_orphaned(tmp_path: Path, monkeypatch) -> None:
    ctx = stub_context(tmp_path)
    monkeypatch.setattr("slarti.cli._context", lambda: ctx)
    stdout = RUNNER.invoke(app, ["report"]).stdout
    assert "Orphaned shapes (declared, unreferenced):\n  none\n" in stdout


def test_help_shows_no_double_backticks() -> None:
    assert "``" not in RUNNER.invoke(app, ["--help"]).stdout
    assert "``" not in RUNNER.invoke(app, ["check", "--help"]).stdout
