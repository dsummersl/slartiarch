from __future__ import annotations

from dataclasses import dataclass

from slarti.findings import Finding, Severity
from slarti.models import Models

DRAWN_ANNOTATION = "drawn"
TRUE = ("true", "True")


@dataclass(frozen=True)
class Shown:
    """The elements some diagram depicts, and the relations, by their index in the corpus."""

    elements: set[str]
    relations: set[int]


def lineage(models: Models, kind: str) -> list[str]:
    """A kind and, when the project schema declares it, every kind above it."""
    view = models.schema
    if view is None or view.get_class(kind) is None:
        return [kind]
    return list(view.class_ancestors(kind))


def _opted(models: Models, kind: str | None) -> bool:
    """Whether a kind, or one above it, is in ``[checks] drawn`` or annotated ``drawn: true``."""
    if not kind:
        return False
    return any(
        name in models.config.drawn
        or models.class_annotation(name, DRAWN_ANNOTATION) in TRUE
        for name in lineage(models, kind)
    )


def _opt_out(kind: str) -> str:
    return (f"or stop requiring '{kind}' to be drawn ('[checks] drawn' in the config, or "
            f"'{DRAWN_ANNOTATION}: true' on the kind or one above it)")


def _elements(models: Models, shown: Shown) -> list[Finding]:
    """DRAWN-1: an element of a kind that opts in appears in at least one diagram."""
    corpus = models.vocabulary
    return [
        Finding(
            id="DRAWN-1",
            severity=Severity.error,
            file=corpus.element_files.get(element.id, ""),
            subject=element.id,
            message=(
                f"element '{element.id}' is a '{element.kind}', which must be drawn, "
                "but no diagram shows it."
            ),
            remedy=(
                f"Attach a node in some diagram to '{element.id}', "
                f"{_opt_out(element.kind)}."
            ),
        )
        for identifier, element in sorted(corpus.elements.items())
        if identifier not in shown.elements and _opted(models, element.kind)
    ]


def _relations(models: Models, shown: Shown) -> list[Finding]:
    """DRAWN-2: a relation of a kind that opts in is depicted by at least one edge."""
    corpus = models.vocabulary
    return [
        Finding(
            id="DRAWN-2",
            severity=Severity.error,
            file=corpus.relation_file(index),
            subject=f"{relation.source} -> {relation.target}",
            message=(
                f"relation '{relation.title}' from '{relation.source}' to "
                f"'{relation.target}' is a '{relation.kind}', which must be drawn, but no "
                "diagram shows it."
            ),
            remedy=(
                f"Draw an edge labelled '{relation.title}' between nodes attached to "
                f"'{relation.source}' and '{relation.target}', {_opt_out(str(relation.kind))}."
            ),
        )
        for index, relation in enumerate(corpus.relations)
        if index not in shown.relations and _opted(models, relation.kind)
    ]


def check(models: Models, shown: Shown) -> list[Finding]:
    """DRAWN-1 and DRAWN-2: every element and relation of an opted-in kind is drawn."""
    return [*_elements(models, shown), *_relations(models, shown)]
