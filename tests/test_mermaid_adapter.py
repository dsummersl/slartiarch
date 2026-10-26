from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from linkml.validator import validate
from linkml_runtime import SchemaView
from typer.testing import CliRunner

from slarti import env, runner, vocabulary
from slarti.adapters import mermaid
from slarti.adapters.mermaid import blocks, c4, er, sequence
from slarti.adapters.mermaid.diagram import Unsupported
from slarti.checks import structure
from slarti.cli import app
from slarti.config import DEFAULTS, Config
from slarti.domain import Finding
from slarti.models import Models
from tests.conftest import make_config

DATA = Path(__file__).parent / "data" / "mermaid"
ARCHITECTURE = yaml.safe_load((DATA / "architecture.yaml").read_text(encoding="utf-8"))
KINDS = ("sequence", "er", "c4", "blocks")


def _fixtures(state: str) -> list[Path]:
    found = [p for kind in KINDS for p in sorted((DATA / kind / state).iterdir())]
    return [p for p in found if p.suffix in (".mmd", ".md")]


def models_for(*fixtures: str, root: Path = DATA) -> Models:
    config = Config(root=root, paths=dict(DEFAULTS), mermaid=list(fixtures))
    return Models(config=config, _likec4={"architecture.yaml": ARCHITECTURE})


def findings_for(models: Models) -> list[Finding]:
    return [*models.mermaid.findings, *structure.check(models)]


def diagram(fixture: str, index: int = 0) -> dict[str, Any]:
    produced = models_for(fixture).mermaid
    return [d for doc in produced.documents.values() for d in doc["diagrams"]][index]


def _rel(path: Path) -> str:
    return str(path.relative_to(DATA))


@pytest.mark.parametrize("fixture", _fixtures("valid"), ids=_rel)
def test_valid_fixtures_raise_no_finding(fixture: Path) -> None:
    assert findings_for(models_for(_rel(fixture))) == []


@pytest.mark.parametrize("fixture", _fixtures("invalid"), ids=_rel)
def test_invalid_fixtures_raise_the_finding_they_are_named_for(fixture: Path) -> None:
    expected = fixture.name.split("--")[0]
    found = findings_for(models_for(_rel(fixture)))
    assert expected in {f.id for f in found}, found
    assert all(f.file == _rel(fixture) and f.remedy for f in found if f.id == expected)


@pytest.mark.parametrize("fixture", _fixtures("valid"), ids=_rel)
def test_adapted_diagrams_conform_to_the_vocabulary(fixture: Path) -> None:
    view = SchemaView(str(vocabulary.SCHEMA), importmap=vocabulary.importmap())
    view.merge_imports()
    for document in models_for(_rel(fixture)).mermaid.documents.values():
        assert [r.message for r in validate(document, view.schema, "Corpus").results] == []


def test_fenced_blocks_are_located_in_the_markdown_file() -> None:
    file = "blocks/valid/architecture.md"
    produced = models_for(file).mermaid
    first, second = produced.documents[file]["diagrams"]
    assert (first["id"], second["id"]) == (f"{file}#1", f"{file}#2")
    assert first["location"]["line"] == 6
    user = first["nodes"][0]
    assert user["id"] == f"{file}#1/user"
    assert user["location"] == {"file": file, "line": 9, "source_id": "user", "label": "user"}
    assert first["edges"][0]["location"]["line"] == 11
    assert second["nodes"][0]["location"]["line"] == 28


def test_generated_regions_are_not_read_back() -> None:
    produced = models_for("blocks/valid/architecture.md").mermaid
    assert produced.diagrams == 2
    assert produced.findings == []


def test_participants_carry_labels_kinds_and_dispositions() -> None:
    nodes = {n["location"]["source_id"]: n for n in diagram("sequence/valid/reading-tasks.mmd")
             ["nodes"]}
    assert nodes["user"]["kind"] == "Participant" and nodes["user"]["actor"] is True
    assert nodes["api"]["actor"] is False and nodes["api"]["element"] == "todo.api"
    assert nodes["store"]["location"]["label"] == "Task store"
    assert nodes["store"]["element"] == "db"


def test_messages_keep_their_order_arrow_and_line() -> None:
    found = diagram("sequence/valid/reading-tasks.mmd")
    assert found["location"]["label"] == "Reading tasks"
    messages = found["edges"]
    assert [m["order"] for m in messages] == [1, 2, 3, 4]
    assert [m["arrow"] for m in messages] == ["->>", "->>", "-->>", "-->>"]
    assert [m["location"]["label"] for m in messages] == [
        "uses", "reads tasks", "rows", "the lists"]
    assert messages[0]["relation"] == "uses" and messages[0]["location"]["line"] == 16
    assert messages[2]["ignored"] == "a reply, which depicts no relation"


def test_every_block_is_read_in_order() -> None:
    found = diagram("sequence/valid/every-block.mmd")
    assert found["location"]["label"] == "Every block the subset reads"
    assert [m["order"] for m in found["edges"]] == list(range(1, 9))
    assert found["edges"][0]["ignored"] == "it ends at 'clock', which is ignored."


def test_entities_carry_attributes_and_labels() -> None:
    entities = {n["location"]["source_id"]: n for n in diagram("er/valid/domain.mmd")["nodes"]}
    assert entities["CUSTOMER"]["kind"] == "Entity"
    assert entities["CUSTOMER"]["attributes"] == [
        {"name": "name", "type": "string"},
        {"name": "email", "type": "string", "keys": ["UK"]},
        {"name": "custNumber", "type": "int", "keys": ["PK", "FK"],
         "comment": "the number billing assigns"},
    ]
    assert entities["ADDRESS"]["location"]["label"] == "Delivery address"
    assert entities["INVOICE"]["location"]["label"] == "Invoice"
    assert "attributes" not in entities["LINE-ITEM"]


def test_relationships_carry_cardinality_at_each_end() -> None:
    edges = diagram("er/valid/domain.mmd")["edges"]
    ends = [(e["source_cardinality"], e["target_cardinality"], e["identifying"]) for e in edges]
    assert ends[:4] == [
        ("exactly_one", "zero_or_more", True),
        ("exactly_one", "one_or_more", True),
        ("one_or_more", "one_or_more", False),
        ("zero_or_one", "zero_or_one", True),
    ]
    assert ends[4][:2] == ("zero_or_more", "exactly_one")
    assert edges[1]["location"]["label"] == "contains many"


def test_classes_attach_entities_by_name_and_name_their_kind() -> None:
    entities = {n["location"]["source_id"]: n for n in diagram("er/valid/lists.mmd")["nodes"]}
    assert entities["TODO-LIST"]["element"] == "TODO-LIST"
    assert entities["TODO-LIST"]["element_kinds"] == ["Table"]
    assert entities["TASK"]["element"] == "todo.tasks"
    assert entities["TASK"]["location"]["label"] == "Task"


def test_c4_macros_attach_by_alias_and_name_their_profile_kind() -> None:
    shapes = {n["location"]["source_id"]: n for n in diagram("c4/valid/context.mmd")["nodes"]}
    assert shapes["user"]["kind"] == "C4Shape" and shapes["user"]["element"] == "user"
    assert shapes["user"]["element_kinds"] == ["Person"]
    assert shapes["user"]["description"] == "Someone who keeps lists"
    assert shapes["todo"]["element_kinds"] == ["SoftwareSystem"]
    assert shapes["mail"]["external"] is True and shapes["mail"]["macro"] == "System_Ext"
    assert shapes["mail"]["location"]["label"] == "Mail service"


def test_c4_relationships_carry_their_macro_and_parameters() -> None:
    found = diagram("c4/valid/context.mmd")
    assert found["location"]["label"] == "The Todo system in context"
    rel = found["edges"][1]
    assert rel["kind"] == "C4Relationship" and rel["relation"] == "sends reminders"
    assert (rel["macro"], rel["technology"]) == ("Rel_R", "SMTP")
    assert rel["location"]["line"] == 8


def test_c4_boundaries_nest_the_shapes_drawn_inside_them() -> None:
    file = "c4/valid/containers.mmd"
    shapes = {n["location"]["source_id"]: n for n in diagram(file)["nodes"]}
    assert shapes["org"]["kind"] == "C4Boundary" and "within" not in shapes["org"]
    assert shapes["org"]["ignored"].startswith("the organisation")
    assert shapes["todo"]["within"] == f"{file}/org"
    assert shapes["todo"]["element_kinds"] == ["SoftwareSystem"]
    assert shapes["web"]["within"] == shapes["taskstore"]["within"] == f"{file}/todo"
    assert shapes["taskstore"]["technology"] == "SQLite"
    assert "within" not in shapes["mail"]


def test_a_c4_directive_overrides_the_macro() -> None:
    shapes = {n["location"]["source_id"]: n
              for n in diagram("c4/valid/components.mmd")["nodes"]}
    assert shapes["page"]["element"] == "views" and "element_kinds" not in shapes["page"]
    assert shapes["legend"]["boundary_type"] == "note"


@pytest.mark.parametrize("source", [
    'C4Context\n  Deployment_Node(dn, "Host")\n',
    'C4Context\n  Person(a, "A")\n  Rel_Back(a, a, "x")\n',
    'C4Context\n  Person(a, A)\n',
    'C4Context\n  Person(a, "A", "d", "s", "t", "l", "extra")\n',
    'C4Context\n  Person(a, "A")\n  Rel(a, b, "uses")\n',
    'C4Context\n  Boundary(b, "B") {\n  }\n',
])
def test_c4_reader_rejects_what_its_subset_omits(source: str) -> None:
    with pytest.raises(Unsupported) as raised:
        c4.read(source)
    assert raised.value.line in (2, 3) and raised.value.text


@pytest.mark.parametrize(("macro", "family"), [
    ("ContainerDb_Ext", "Container"), ("SystemQueue", "System"), ("Rel_Down", "Rel"),
    ("System_Boundary", "System_Boundary"), ("Person_Ext", "Person"),
])
def test_c4_variants_belong_to_their_family(macro: str, family: str) -> None:
    assert c4.family(macro) == family


def test_unsupported_syntax_names_the_file_and_line() -> None:
    [finding] = models_for("sequence/invalid/MMD-3--box.mmd").mermaid.findings
    assert (finding.id, finding.file, finding.line) == ("MMD-3", "sequence/invalid/MMD-3--box.mmd",
                                                        3)
    assert "box Backend" in finding.message and "docs/mermaid.md" in finding.remedy


def test_an_unparsed_diagram_contributes_nothing() -> None:
    produced = models_for("sequence/invalid/MMD-3--box.mmd").mermaid
    assert produced.documents == {} and produced.diagrams == 1


def test_a_missing_input_is_a_finding(tmp_path: Path) -> None:
    [finding] = models_for("nowhere.md", root=tmp_path).mermaid.findings
    assert (finding.id, finding.file) == ("MMD-1", "nowhere.md")


def test_a_directory_contributes_its_mermaid_and_markdown(tmp_path: Path) -> None:
    (tmp_path / "diagrams").mkdir()
    (tmp_path / "diagrams" / "a.mmd").write_text("erDiagram\n  A:::Table\n", encoding="utf-8")
    (tmp_path / "diagrams" / "b.md").write_text("no diagrams\n", encoding="utf-8")
    (tmp_path / "diagrams" / "c.txt").write_text("sequenceDiagram\n", encoding="utf-8")
    produced = models_for("diagrams", root=tmp_path).mermaid
    assert list(produced.documents) == ["diagrams/a.mmd"]


def test_an_empty_diagram_declares_no_type(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text("```mermaid\n%% only a comment\n```\n", encoding="utf-8")
    [finding] = models_for("doc.md", root=tmp_path).mermaid.findings
    assert finding.id == "MMD-2" and "no diagram type" in finding.message


@pytest.mark.parametrize("directive", [
    "alias * todo.api",
    "attach api todo.api extra",
    "attach api -> db",
    "rename api",
])
def test_malformed_directives_are_findings(tmp_path: Path, directive: str) -> None:
    source = f"sequenceDiagram\n  %% slarti: {directive}\n  participant api\n  participant db\n"
    (tmp_path / "d.mmd").write_text(source, encoding="utf-8")
    found = models_for("d.mmd", root=tmp_path).mermaid.findings
    assert [(f.id, f.line) for f in found] == [("MMD-4", 2)]


def test_an_unterminated_front_matter_is_not_a_title() -> None:
    found = blocks.block("d", "d.mmd", 0, ["---", "sequenceDiagram"])
    assert found.title == "" and found.text.splitlines()[0] == "---"


def test_front_matter_that_is_not_yaml_gives_no_title() -> None:
    assert blocks.block("d", "d.mmd", 0, ["---", "title: [", "---", "erDiagram"]).title == ""


def test_readers_reject_what_their_subset_omits() -> None:
    with pytest.raises(Unsupported) as raised:
        sequence.read("sequenceDiagram\n  a<<->>b: both ways\n")
    assert raised.value.line == 2
    with pytest.raises(Unsupported):
        er.read('erDiagram\n  "Quoted name" ||--o{ B : x\n')


def test_kinds_resolve_through_the_project_schema(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    schema = (Path(__file__).parent / "data" / "vocabulary" / "project.yaml").read_text()
    (config.path("linkml") / "todo.yaml").write_text(
        schema + "  Cache:\n    is_a: Service\n", encoding="utf-8")
    (tmp_path / "d.mmd").write_text("erDiagram\n  redis:::Service\n", encoding="utf-8")
    elements = {"elements": [{"id": "redis", "kind": "Cache", "name": "Redis"}]}
    config = Config(root=tmp_path, paths=config.paths, mermaid=["d.mmd"])
    models = Models(config=config, _likec4={"a.yaml": elements})
    assert structure.check(models) == []


def test_the_runner_reports_mermaid_findings(tmp_path: Path) -> None:
    models = models_for("sequence/invalid/MMD-3--box.mmd")
    ctx = runner.Context(config=models.config, models=models, constraints=[])
    report, _ = runner.check(ctx, include_docs=False)
    assert "MMD-3" in {f.id for f in report.findings}


def test_mermaid_diagrams_are_vocabulary_input() -> None:
    models = models_for("sequence/valid/reading-tasks.mmd")
    assert len(models.vocabulary.nodes) == 3 and len(models.vocabulary.edges) == 4
    assert mermaid.produce(models.config).diagrams == 1


def _pin(root: Path, version: object) -> None:
    package = root / env.MERMAID_PACKAGE
    package.parent.mkdir(parents=True)
    package.write_text(json.dumps({"version": version}), encoding="utf-8")


@pytest.mark.parametrize(("version", "ok"), [
    ("10.9.3", False), ("11.0.0", True), ("12.2.0", True), ("13.0.0", False),
])
def test_a_pinned_mermaid_must_be_in_range(tmp_path: Path, version: str, ok: bool) -> None:
    _pin(tmp_path, version)
    probe = env.probe_mermaid(tmp_path)
    assert probe.ok is ok and probe.version == version
    assert probe.location == str(tmp_path / env.MERMAID_PACKAGE)


def test_no_pinned_mermaid_passes(tmp_path: Path) -> None:
    probe = env.probe_mermaid(tmp_path)
    assert probe.ok and ">=11.0.0,<13" in probe.detail


def test_an_unreadable_mermaid_version_fails(tmp_path: Path) -> None:
    _pin(tmp_path, "latest")
    assert not env.probe_mermaid(tmp_path).ok


def test_probe_all_checks_mermaid_only_when_asked(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(env, "probe", lambda req, cwd=None: env.probe_python())
    tools = [p.tool for p in env.probe_all(likec4=False)]
    assert "mermaid" not in tools
    assert [p.tool for p in env.probe_all(likec4=False, mermaid=tmp_path)][-1] == "mermaid"


def test_an_edge_directive_names_the_relation_over_the_label(tmp_path: Path) -> None:
    source = (
        "sequenceDiagram\n"
        "  %% slarti: attach api todo.api\n"
        "  %% slarti: attach db todo.db\n"
        "  %% slarti: attach api -> db reads tasks\n"
        "  api->>db: SELECT * FROM tasks\n"
    )
    (tmp_path / "d.mmd").write_text(source, encoding="utf-8")
    models = models_for("d.mmd", root=tmp_path)
    assert diagram_edges(models)[0]["relation"] == "reads tasks"
    assert findings_for(models) == []


@pytest.mark.parametrize(("blanket", "expected"), [
    ("", {"ATTACH-1"}),
    ("  %% slarti: ignore * drawn for the reader, not the architecture\n", set()),
])
def test_an_unlabelled_edge_needs_a_disposition(tmp_path: Path, blanket: str,
                                                expected: set[str]) -> None:
    source = (f"erDiagram\n{blanket}  %% slarti: alias TASK todo.tasks\n"
              '  TODO-LIST:::Table\n  TASK:::Table\n  TODO-LIST ||--o{ TASK : ""\n')
    (tmp_path / "d.mmd").write_text(source, encoding="utf-8")
    assert {f.id for f in findings_for(models_for("d.mmd", root=tmp_path))} == expected


def test_a_message_depicts_the_one_relation_between_its_elements(tmp_path: Path) -> None:
    source = ("sequenceDiagram\n  %% slarti: attach api todo.api\n"
              "  %% slarti: attach db todo.db\n  api->>db: load tasks\n")
    (tmp_path / "d.mmd").write_text(source, encoding="utf-8")
    assert findings_for(models_for("d.mmd", root=tmp_path)) == []


def test_a_c4_relationship_still_names_its_relation(tmp_path: Path) -> None:
    source = ('C4Container\n  Container(api, "API")\n  ContainerDb(db, "DB")\n'
              '  Rel(api, db, "load tasks")\n')
    (tmp_path / "d.mmd").write_text(source, encoding="utf-8")
    (finding,) = [f for f in findings_for(models_for("d.mmd", root=tmp_path))
                  if f.id == "DANGLE-2"]
    assert "it declares 'reads tasks'" in finding.message
    assert "'%% slarti: attach api -> db <relation>'" in finding.remedy


def test_mermaid_remedies_are_directives() -> None:
    fixture = "sequence/invalid/ATTACH-1--undeclared.mmd"
    (finding,) = findings_for(models_for(fixture))
    assert finding.id == "ATTACH-1"
    assert "'%% slarti: attach worker <element-id>'" in finding.remedy


def diagram_edges(models: Models) -> list[dict[str, Any]]:
    return [e for doc in models.mermaid.documents.values() for d in doc["diagrams"]
            for e in d["edges"]]


def test_doctor_lists_mermaid_inputs_and_probes_the_pin(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "slarti.toml").write_text('[paths]\nmermaid = ["docs"]\n', encoding="utf-8")
    _pin(tmp_path, "12.2.0")
    monkeypatch.setattr(env, "probe", lambda req, cwd=None: env.probe_python())
    result = CliRunner().invoke(app, ["doctor"])
    assert "['docs']" in result.stdout
    assert "mermaid  12.2.0" in result.stdout
