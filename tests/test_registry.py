from __future__ import annotations

from pathlib import Path

import pytest

from slarti import registry, resolvers
from slarti.checks import registry_checks

REGISTRY = """constraints:
  - id: D1
    statement: A task belongs to exactly one list.
    enforced_by:
      kind: linkml_slot
      ref: "Task.list"
    decision: ADR-004
  - id: U1
    statement: The API checks membership before every list access.
    enforced_by: none
    reason: Requires an implementation that does not exist.
"""


def write_registry(path: Path, text: str = REGISTRY) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_load_reads_both_forms(tmp_path: Path) -> None:
    constraints = registry.load(write_registry(tmp_path / "constraints.yaml"))
    assert [c.id for c in constraints] == ["D1", "U1"]
    assert constraints[0].enforced_by.kind == "linkml_slot"
    assert registry.is_unenforced(constraints[1].enforced_by)
    assert constraints[0].line is not None


def test_missing_registry_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(registry.RegistryError):
        registry.load(tmp_path / "nope.yaml")


def test_resolvers_answer_both_directions(models) -> None:
    here = registry.Enforcer(kind="linkml_slot", ref="Task.list")
    assert resolvers.resolve(models, here)
    gone = registry.Enforcer(kind="linkml_slot", ref="Task.gone")
    assert not resolvers.resolve(models, gone)
    absent = registry.Enforcer(kind="likec4_absent_relation", ref="todo.db -> todo.api")
    assert resolvers.resolve(models, absent)
    present = registry.Enforcer(kind="likec4_relation", ref="todo.api -> todo.db")
    assert resolvers.resolve(models, present)


def test_reg1_enforcer_does_not_exist(models) -> None:
    config = models.config
    write_registry(config.path("constraints"), REGISTRY.replace("Task.list", "Task.gone"))
    (config.document_paths()[0]).write_text("ADR-004", encoding="utf-8")
    constraints = registry.load(config.path("constraints"))
    findings = registry_checks.check(config, models, constraints)
    assert [f.id for f in findings] == ["REG-1"]
    assert "Task.gone" in findings[0].message


def test_reg3_unenforced_without_a_reason(models) -> None:
    config = models.config
    text = REGISTRY.replace("    reason: Requires an implementation that does not exist.\n", "")
    write_registry(config.path("constraints"), text)
    config.document_paths()[0].write_text("ADR-004", encoding="utf-8")
    constraints = registry.load(config.path("constraints"))
    assert [f.id for f in registry_checks.check(config, models, constraints)] == ["REG-3"]


def test_reg4_duplicate_id(models) -> None:
    config = models.config
    text = REGISTRY.replace("  - id: U1", "  - id: D1")
    write_registry(config.path("constraints"), text)
    config.document_paths()[0].write_text("ADR-004", encoding="utf-8")
    constraints = registry.load(config.path("constraints"))
    assert "REG-4" in [f.id for f in registry_checks.check(config, models, constraints)]


def test_reg5_decision_missing_from_the_document(models) -> None:
    config = models.config
    write_registry(config.path("constraints"))
    config.document_paths()[0].write_text("no decisions here", encoding="utf-8")
    constraints = registry.load(config.path("constraints"))
    assert [f.id for f in registry_checks.check(config, models, constraints)] == ["REG-5"]


SHAPE = """@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix example: <https://example.org/example/> .

example:TaskHasList
  a sh:NodeShape ;
  sh:targetClass example:Task ;
  sh:property [ sh:path example:list ; sh:minCount 1 ] .
"""


def test_reg2_orphaned_shape(models) -> None:
    config = models.config
    (config.path("shacl") / "invariants.ttl").write_text(SHAPE, encoding="utf-8")
    write_registry(config.path("constraints"))
    config.document_paths()[0].write_text("ADR-004", encoding="utf-8")
    constraints = registry.load(config.path("constraints"))
    findings = registry_checks.check(config, models, constraints)
    assert [f.id for f in findings] == ["REG-2"]
    assert findings[0].subject == "example:TaskHasList"


def test_reg6_fixture_does_not_exist(models) -> None:
    config = models.config
    text = REGISTRY.replace(
        '      ref: "Task.list"', '      ref: "Task.list"\n      fixture: model/data/invalid/D1.ttl'
    )
    write_registry(config.path("constraints"), text)
    config.document_paths()[0].write_text("ADR-004", encoding="utf-8")
    constraints = registry.load(config.path("constraints"))
    assert [f.id for f in registry_checks.check(config, models, constraints)] == ["REG-6"]


def test_absent_relation_aliases_and_reg8_names_the_declaring_file(models) -> None:
    config = models.config
    text = "constraints:\n  - id: T1\n    statement: no.\n    enforced_by:\n" \
           "      kind: absent_relation\n      ref: todo.api -> todo.db\n"
    write_registry(config.path("constraints"), text)
    constraints = registry.load(config.path("constraints"))
    findings = registry_checks.check(config, models, constraints)
    reg8 = [f for f in findings if f.id == "REG-8"]
    assert len(reg8) == 1
    assert "likec4" not in reg8[0].remedy.lower()
    assert reg8[0].file == "docs/slarti/likec4/todo.c4"


def test_a_bad_curie_error_suggests_a_curie_id() -> None:
    assert "id: todo:t1" in registry_checks._load_remedy("Unknown CURIE prefix: @base")
    assert "Turtle" in registry_checks._load_remedy("other")
