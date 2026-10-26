from __future__ import annotations

from slarti import generate
from slarti.registry import Constraint, Enforcer

ENFORCED = Constraint(
    id="D1",
    statement="A task belongs to exactly one list.",
    enforced_by=Enforcer(kind="linkml_slot", ref="Task.list"),
    reason=None,
    decision="ADR-004",
)
UNENFORCED = Constraint(
    id="U1",
    statement="The API checks membership.",
    enforced_by=Enforcer(),
    reason="No implementation exists.",
    decision=None,
)


def test_constraints_table_lists_only_enforced_rules() -> None:
    table = generate.constraints_table([UNENFORCED, ENFORCED])
    assert "| D1 |" in table
    assert "| U1 |" not in table
    assert "linkml_slot `Task.list`" in table


def test_unverified_table_lists_only_unenforced_rules() -> None:
    table = generate.unverified_table([UNENFORCED, ENFORCED])
    assert "| U1 |" in table
    assert "No implementation exists." in table
    assert "| D1 |" not in table


def test_tables_are_sorted_and_deterministic() -> None:
    forward = generate.constraints_table([ENFORCED, UNENFORCED])
    backward = generate.constraints_table([UNENFORCED, ENFORCED])
    assert forward == backward


def test_empty_tables_say_so() -> None:
    assert generate.constraints_table([]) == "_No enforced rules._"
    assert generate.unverified_table([]) == "_No rules are declared._"
    assert generate.unverified_table([ENFORCED]) == "_Every rule is enforced._"


ERD = """erDiagram
Service {
    integer port  
    string id  
    stringList owns  
}
Store {
    string id  
}

Service ||--|o Store : "store"
Service ||--}o Store : "owns"
"""


def test_the_erd_hides_slots_only_an_imported_schema_declares() -> None:
    shown = generate._hide_inherited(ERD, {"Service": {"id", "owns"}})
    assert "string id" in shown  # Store's own
    assert "owns" not in shown
    assert 'Service ||--|o Store : "store"' in shown
    assert "integer port" in shown


def test_inherited_slots_are_an_option_for_slarti_not_gen_erdiagram() -> None:
    region = "linkml_erd?inherited_slots=true&max_hops=2"
    assert generate._parse_erd_opts(region) == ["--max-hops", "2"]
    assert generate._keeps_inherited(region)
    assert not generate._keeps_inherited("linkml_erd")


def test_ownership_table_names_the_owner(models) -> None:
    table = generate.ownership_table(models)
    assert "| Task | `todo.api` | API |" in table


def test_diagram_block_wraps_mermaid() -> None:
    assert generate.diagram_block("index", {"index": "graph TB"}) == "```mermaid\ngraph TB\n```"


def test_missing_view_is_reported_in_place() -> None:
    assert "not in the model" in generate.diagram_block("gone", {})


def test_unknown_region_has_no_content(models) -> None:
    assert generate.region_content("mystery", [], models, {}) is None
