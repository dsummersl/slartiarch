from __future__ import annotations

from slarti import docs, generate
from slarti.checks import doc_checks
from slarti.registry import Constraint, Enforcer

DOCUMENT = """# Doc

<!-- slarti:begin constraints -->
<!-- slarti:end constraints -->

<!-- slarti:begin unverified -->
<!-- slarti:end unverified -->

<!-- slarti:begin diagram:index -->
<!-- slarti:end diagram:index -->
"""

CONSTRAINT = Constraint(
    id="D1",
    statement="A task belongs to exactly one list.",
    enforced_by=Enforcer(kind="linkml_slot", ref="Task.list"),
    reason=None,
    decision=None,
)


def prepare(models, text: str = DOCUMENT, diagrams: dict[str, str] | None = None, monkeypatch=None):
    models.config.document_paths()[0].write_text(text, encoding="utf-8")
    fresh = {"index": "graph TB"} if diagrams is None else diagrams
    monkeypatch.setattr(generate, "render_diagrams", lambda config: fresh)
    return fresh


def test_doc1_stale_region(models, monkeypatch) -> None:
    prepare(models, monkeypatch=monkeypatch)
    findings = doc_checks.check(models.config, models, [CONSTRAINT])
    assert "DOC-1" in [f.id for f in findings]


def test_a_generated_document_is_clean(models, monkeypatch) -> None:
    fresh = prepare(models, monkeypatch=monkeypatch)
    rendered = docs.render(models.config, [CONSTRAINT], models, fresh)[0]
    models.config.document_paths()[0].write_text(rendered.text, encoding="utf-8")
    assert doc_checks.check(models.config, models, [CONSTRAINT]) == []


def test_write_fixes_a_stale_region(models, monkeypatch) -> None:
    prepare(models, monkeypatch=monkeypatch)
    assert docs.write(models.config, [CONSTRAINT], models) == models.config.document_paths()
    assert doc_checks.check(models.config, models, [CONSTRAINT]) == []
    assert docs.write(models.config, [CONSTRAINT], models) == []


def test_write_leaves_unbalanced_markers_alone(models, monkeypatch) -> None:
    prepare(models, "<!-- slarti:begin constraints -->\n", monkeypatch=monkeypatch)
    assert docs.write(models.config, [CONSTRAINT], models) == []


def test_doc3_unknown_region(models, monkeypatch) -> None:
    text = DOCUMENT.replace("constraints -->", "mystery -->")
    prepare(models, text, monkeypatch=monkeypatch)
    assert "DOC-3" in [f.id for f in doc_checks.check(models.config, models, [])]


def test_doc3_unbalanced_markers(models, monkeypatch) -> None:
    prepare(models, "<!-- slarti:begin constraints -->\n", monkeypatch=monkeypatch)
    assert [f.id for f in doc_checks.check(models.config, models, [])] == ["DOC-3"]


def test_doc3_missing_document(models, monkeypatch) -> None:
    assert [f.id for f in doc_checks.check(models.config, models, [])] == ["DOC-3"]


def test_render_is_idempotent(models, monkeypatch) -> None:
    fresh = prepare(models, monkeypatch=monkeypatch)
    once = docs.render(models.config, [CONSTRAINT], models, fresh)[0].text
    models.config.document_paths()[0].write_text(once, encoding="utf-8")
    assert docs.render(models.config, [CONSTRAINT], models, fresh)[0].text == once


def test_an_empty_region_is_not_yet_generated_rather_than_stale() -> None:
    rendered = type("R", (), {"text": "<!-- slarti:begin ownership -->\nrows\n"
                                      "<!-- slarti:end ownership -->\n"})()
    current = "<!-- slarti:begin ownership -->\n<!-- slarti:end ownership -->\n"
    (finding,) = doc_checks._region_findings("a.md", current, rendered)
    assert "has not been generated yet" in finding.message
