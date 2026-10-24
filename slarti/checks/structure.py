from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from slarti.domain import Element, Relation
from slarti.findings import Finding, Severity
from slarti.instances import Corpus, Drawn
from slarti.models import Models

DRAWN_ANNOTATION = "drawn"
TRUE = ("true", "True")


@dataclass(frozen=True)
class Names:
    """Every name an element answers to: its id and its declared aliases."""

    resolved: dict[str, list[str]]

    @classmethod
    def of(cls, corpus: Corpus) -> Names:
        found: dict[str, set[str]] = defaultdict(set)
        for element in corpus.elements:
            for name in [element, *corpus.aliases.get(element, [])]:
                found[name].add(element)
        return cls({name: sorted(ids) for name, ids in found.items()})

    def all(self, name: str | None) -> list[str]:
        return self.resolved.get(name or "", [])

    def element(self, name: str | None) -> str | None:
        """The one element a name resolves to, or None when it resolves to none or many."""
        ids = self.all(name)
        return ids[0] if len(ids) == 1 else None

    def ambiguous(self) -> dict[str, list[str]]:
        return {name: ids for name, ids in sorted(self.resolved.items()) if len(ids) > 1}


def _at(drawn: Drawn, rule: str, message: str, remedy: str) -> Finding:
    return Finding(
        id=rule,
        severity=Severity.error,
        file=drawn.file,
        line=drawn.line,
        subject=drawn.id,
        message=message,
        remedy=remedy,
    )


# (attached, ignored, reason given) -> the disposition rule that state breaks.
_BROKEN = {
    (False, False, False): "ATTACH-1",
    (True, True, False): "ATTACH-2",
    (True, True, True): "ATTACH-2",
    (False, True, False): "ATTACH-3",
}

_DISPOSITION = {
    "ATTACH-1": (
        "{what} has no disposition: it is neither attached nor ignored.",
        "Give {what} '{slot}: <{target}>', or 'ignored: <reason>'.",
    ),
    "ATTACH-2": (
        "{what} is both attached and ignored.",
        "Keep exactly one of '{slot}' and 'ignored' on {what}.",
    ),
    "ATTACH-3": (
        "{what} is ignored without a reason.",
        "Say why {what} depicts nothing in the architecture, or attach it.",
    ),
}


def _disposition(drawn: Drawn) -> Finding | None:
    """ATTACH-1..ATTACH-3: a drawn construct is attached or ignored with a reason, never neither."""
    reason = bool((drawn.ignored or "").strip())
    rule = _BROKEN.get((drawn.attaches_to is not None, drawn.ignored is not None, reason))
    if rule is None:
        return None
    what = f"edge '{drawn.id}'" if drawn.is_edge else f"node '{drawn.id}'"
    slot, target = ("relation", "kind") if drawn.is_edge else ("element", "element-id")
    message, remedy = _DISPOSITION[rule]
    return _at(
        drawn,
        rule,
        message.format(what=what),
        remedy.format(what=what, slot=slot, target=target),
    )


def _node_attachment(node: Drawn, names: Names) -> Finding | None:
    """IDENT-2 and DANGLE-1: a node's attachment names exactly one element."""
    ids = names.all(node.attaches_to)
    if not node.attached or len(ids) == 1:
        return None
    if ids:
        return _at(
            node,
            "IDENT-2",
            f"node '{node.id}' attaches to '{node.attaches_to}', which resolves to more "
            f"than one element: {', '.join(ids)}.",
            f"Attach node '{node.id}' by an element id, and give each alias to one element.",
        )
    return _at(
        node,
        "DANGLE-1",
        f"node '{node.id}' attaches to '{node.attaches_to}', which is not an element "
        "or an alias.",
        f"Attach node '{node.id}' to an element that exists, or declare '{node.attaches_to}'.",
    )


def _quoted(names: list[str]) -> str:
    return ", ".join(repr(n) for n in names)


def _endpoint_missing(edge: Drawn, nodes: dict[str, Drawn]) -> Finding | None:
    missing = [n for n in (edge.source, edge.target) if n not in nodes]
    if not missing:
        return None
    return _at(
        edge,
        "DANGLE-4",
        f"edge '{edge.id}' ends at {_quoted(missing)}, which no diagram draws as a node.",
        "Point the edge at node ids the corpus declares, or add the missing node.",
    )


def _endpoint_unattached(edge: Drawn, nodes: dict[str, Drawn]) -> Finding | None:
    loose = [n for n in (edge.source, edge.target) if not nodes[n].attached]
    if not loose:
        return None
    return _at(
        edge,
        "DANGLE-3",
        f"edge '{edge.id}' is attached, but its endpoint {_quoted(loose)} is ignored "
        "or unattached.",
        "Attach the endpoint node to an element, or ignore the edge with a reason.",
    )


def _depicts(relation: Relation, ends: tuple[str | None, str | None], kind: str | None) -> bool:
    return (relation.source, relation.target) == ends and kind in (relation.kind, relation.title)


def _relation_missing(edge: Drawn, nodes: dict[str, Drawn], names: Names, corpus: Corpus
                      ) -> Finding | None:
    ends = (
        names.element(nodes[edge.source].attaches_to),
        names.element(nodes[edge.target].attaches_to),
    )
    # An endpoint that resolves to no single element already has its own finding.
    if None in ends or any(_depicts(r, ends, edge.attaches_to) for r in corpus.relations):
        return None
    return _at(
        edge,
        "DANGLE-2",
        f"edge '{edge.id}' depicts relation '{edge.attaches_to}', which the architecture "
        f"does not declare from '{ends[0]}' to '{ends[1]}'.",
        f"Declare a '{edge.attaches_to}' relation from '{ends[0]}' to '{ends[1]}', "
        "or correct the edge's 'relation'.",
    )


def _edge_attachment(edge: Drawn, nodes: dict[str, Drawn], names: Names, corpus: Corpus
                     ) -> Finding | None:
    """DANGLE-2..DANGLE-4: an edge joins drawn nodes and depicts a relation that exists."""
    missing = _endpoint_missing(edge, nodes)
    if missing or not edge.attached:
        return missing
    return _endpoint_unattached(edge, nodes) or _relation_missing(edge, nodes, names, corpus)


def _ambiguous_names(corpus: Corpus, names: Names) -> list[Finding]:
    """IDENT-1: every declared name resolves to exactly one element."""
    return [
        Finding(
            id="IDENT-1",
            severity=Severity.error,
            file=corpus.element_files.get(ids[0], ""),
            subject=name,
            message=f"name '{name}' resolves to more than one element: {', '.join(ids)}.",
            remedy=f"Leave '{name}' as the id or an alias of exactly one element.",
        )
        for name, ids in names.ambiguous().items()
    ]


def _drawn_kinds(models: Models) -> set[str]:
    """Element kinds whose class, or an ancestor's, is annotated ``drawn: true``."""
    view = models.schema
    if view is None:
        return set()
    return {
        name
        for name in view.all_classes()
        if any(
            models.class_annotation(a, DRAWN_ANNOTATION) in TRUE
            for a in view.class_ancestors(name)
        )
    }


def _shown(corpus: Corpus, names: Names) -> set[str | None]:
    return {names.element(n.attaches_to) for n in corpus.nodes if n.attached}


def _undrawn_elements(models: Models, corpus: Corpus, names: Names) -> list[Element]:
    kinds = _drawn_kinds(models)
    candidates = [corpus.elements[i] for i in sorted(set(corpus.elements) - _shown(corpus, names))]
    return [e for e in candidates if e.kind in kinds]


def _undrawn(models: Models, corpus: Corpus, names: Names) -> list[Finding]:
    """DRAWN-1: an element of a kind that opts in appears in at least one diagram."""
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
                f"Attach a node in some diagram to '{element.id}', or drop "
                f"'{DRAWN_ANNOTATION}: true' from kind '{element.kind}'."
            ),
        )
        for element in _undrawn_elements(models, corpus, names)
    ]


def _drawn_findings(corpus: Corpus, names: Names) -> list[Finding | None]:
    nodes = {n.id: n for n in corpus.nodes}
    return [
        *(_disposition(d) for d in [*corpus.nodes, *corpus.edges]),
        *(_node_attachment(n, names) for n in corpus.nodes),
        *(_edge_attachment(e, nodes, names, corpus) for e in corpus.edges),
    ]


def check(models: Models) -> list[Finding]:
    """ATTACH-*, IDENT-*, DANGLE-*, DRAWN-1: diagrams against the architecture, both ways."""
    corpus = models.vocabulary
    names = Names.of(corpus)
    found = [f for f in _drawn_findings(corpus, names) if f is not None]
    return [*found, *_ambiguous_names(corpus, names), *_undrawn(models, corpus, names)]
