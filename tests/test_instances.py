from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from slarti import config as config_module
from slarti import env, instances, runner, vocabulary
from slarti.checks import delegated, ownership
from slarti.cli import app
from slarti.models import Models

PROJECT = Path(__file__).parent / "data" / "instances" / "project"

needs_linkml = pytest.mark.skipif(shutil.which("linkml") is None, reason="LinkML is not installed")


def project(tmp_path: Path) -> config_module.Config:
    target = tmp_path / "project"
    shutil.copytree(PROJECT, target)
    return config_module.load(target)


def write(cfg: config_module.Config, name: str, text: str) -> Path:
    path = cfg.root / "architecture" / name
    path.write_text(text, encoding="utf-8")
    return path


def ids(findings: list) -> list[str]:
    return sorted(f.id for f in findings)


def test_config_names_instance_inputs(tmp_path: Path) -> None:
    cfg = project(tmp_path)
    assert cfg.instances == ["architecture"]
    assert cfg.instance_paths() == [cfg.root / "architecture"]
    assert not cfg.likec4_enabled()


def test_a_directory_input_reads_yaml_and_json(tmp_path: Path) -> None:
    cfg = project(tmp_path)
    names = [p.name for p in instances.files_for(cfg.root / "architecture")]
    assert names == ["containers.yaml", "relations.json"]


def test_instances_join_the_architecture(tmp_path: Path) -> None:
    models = Models(config=project(tmp_path))
    architecture = models.architecture
    assert sorted(architecture.elements) == ["todo.api", "todo.db"]
    assert architecture.elements["todo.api"].owns == ["Reads", "Service", "Task"]
    assert architecture.has_relation("todo.api", "todo.db")
    assert models.element_file("todo.db") == "architecture/containers.yaml"
    assert models.instances.findings == []


def test_ownership_findings_name_the_instance_file(tmp_path: Path) -> None:
    cfg = project(tmp_path)
    path = cfg.root / "architecture" / "containers.yaml"
    path.write_text(path.read_text().replace("owns: [Database]", "owns: [Database, Ghost]"))
    findings = ownership.check(Models(config=cfg))
    assert ids(findings) == ["OWN-4"]
    assert findings[0].file == "architecture/containers.yaml"


def test_inp1_a_configured_input_is_missing(tmp_path: Path) -> None:
    cfg = project(tmp_path)
    shutil.rmtree(cfg.root / "architecture")
    findings = instances.load(cfg).findings
    assert ids(findings) == ["INP-1"]
    assert findings[0].file == "architecture"


@pytest.mark.parametrize("text", ["- not\n- a mapping\n", "elements: [unclosed\n"])
def test_inp2_an_instance_file_is_not_a_mapping(tmp_path: Path, text: str) -> None:
    cfg = project(tmp_path)
    write(cfg, "broken.yaml", text)
    findings = instances.load(cfg).findings
    assert ids(findings) == ["INP-2"]
    assert findings[0].file == "architecture/broken.yaml"
    assert findings[0].remedy


def test_inp3_an_instance_does_not_conform(tmp_path: Path) -> None:
    cfg = project(tmp_path)
    write(cfg, "queue.yaml", "elements:\n  - id: todo.queue\n    kind: Queue\n    name: Queue\n")
    findings = instances.load(cfg).findings
    assert ids(findings) and set(ids(findings)) == {"INP-3"}
    assert all(f.file == "architecture/queue.yaml" for f in findings)


def test_without_a_project_schema_instances_meet_the_vocabulary(tmp_path: Path) -> None:
    cfg = project(tmp_path)
    shutil.rmtree(cfg.root / "schema")
    (cfg.root / "architecture" / "relations.json").unlink()
    write(cfg, "containers.yaml", "diagrams:\n  - id: d\n    location: {file: notes.md}\n")
    assert instances.load(cfg).findings == []
    write(cfg, "containers.yaml", "diagrams:\n  - id: d\n    location: {line: 3}\n")
    assert ids(instances.load(cfg).findings) == ["INP-3"]


def test_malformed_input_stops_the_run_before_any_seam(tmp_path: Path, monkeypatch) -> None:
    cfg = project(tmp_path)
    write(cfg, "broken.yaml", "- not a corpus\n")
    monkeypatch.setattr(delegated, "run_all", lambda config: [])
    report, _ = runner.check(runner.context(cfg))
    assert ids(report.findings) == ["INP-2"]


def test_likec4_is_neither_probed_nor_run_without_c4_sources(tmp_path: Path, monkeypatch) -> None:
    cfg = project(tmp_path)
    monkeypatch.setattr(env, "probe", lambda req, cwd=None: pytest.fail(req.tool))
    monkeypatch.setattr(env, "REQUIREMENTS", [r for r in env.REQUIREMENTS if r.tool != "linkml"])
    assert [p.tool for p in env.probe_all(likec4=False)] == ["python"]
    assert all(d.tool != "likec4" for d in delegated.run_all(cfg))


def test_lint_resolves_the_vocabulary_without_the_network() -> None:
    text = (PROJECT / "schema" / "todo.yaml").read_text()
    local = vocabulary.localised(text)
    assert f"slarti: {vocabulary.SCHEMA.parent.as_uri()}/" in local
    assert vocabulary.localised("id: x\n") == "id: x\n"


@needs_linkml
def test_check_runs_on_hand_written_instances_alone(tmp_path: Path, monkeypatch) -> None:
    cfg = project(tmp_path)
    monkeypatch.chdir(cfg.root)
    result = CliRunner().invoke(app, ["check", "--json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout[result.stdout.index("{"):])
    assert payload["findings"] == []
