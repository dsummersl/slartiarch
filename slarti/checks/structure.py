from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from slarti.checks import drawn as drawn_checks
from slarti.domain import ModelRelation
from slarti.findings import Finding, Severity
from slarti.instances import Corpus, Drawn
from slarti.models import Models

MERMAID = "mermaid"
MESSAGE = "Message"


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


def _ends(drawn: Drawn) -> tuple[str, str]:
    """The names an edge's diagram gives its two ends."""
    source, _, target = drawn.name.partition("->")
    return source or drawn.source, target or drawn.target


def _named(drawn: Drawn) -> str:
    """How a diagram's directives name the node or edge: ``a`` or ``a -> b``."""
    return " -> ".join(_ends(drawn)) if drawn.is_edge else drawn.name or drawn.id


# (attached, ignored, reason given) -> the disposition rule that state breaks.
_BROKEN = {
    (False, False, False): "ATTACH-1",
    (True, True, False): "ATTACH-2",
    (True, True, True): "ATTACH-2",
    (False, True, False): "ATTACH-3",
}

_MESSAGES = {
    "ATTACH-1": "{what} has no disposition: it is neither attached nor ignored.",
    "ATTACH-2": "{what} is both attached and ignored.",
    "ATTACH-3": "{what} is ignored without a reason.",
}

# Each remedy as the notation the construct came from writes it.
_REMEDIES = {
    "ATTACH-1": "Give {what} '{slot}: <{target}>', or 'ignored: <reason>'.",
    "ATTACH-2": "Keep exactly one of '{slot}' and 'ignored' on {what}.",
    "ATTACH-3": "Say why {what} depicts nothing in the architecture, or attach it.",
}

_MERMAID_REMEDIES = {
    ("ATTACH-1", False): (
        "Add '%% slarti: attach {name} <element-id>' to the diagram, draw the node with a "
        "class or C4 macro naming its kind, or add '%% slarti: ignore {name} <reason>'."
    ),
    ("ATTACH-1", True): (
        "Label the edge with the relation it depicts, add '%% slarti: attach {name} "
        "<relation>' to the diagram, or add '%% slarti: ignore {name} <reason>'."
    ),
    ("ATTACH-2", False): "Keep exactly one of the attach and ignore directives for '{name}'.",
    ("ATTACH-2", True): "Keep exactly one of the attach and ignore directives for '{name}'.",
    ("ATTACH-3", False): "Give '%% slarti: ignore {name}' a reason, or attach the node.",
    ("ATTACH-3", True): "Give '%% slarti: ignore {name}' a reason, or attach the edge.",
}


def _disposition_remedy(drawn: Drawn, rule: str, what: str) -> str:
    if drawn.notation == MERMAID:
        return _MERMAID_REMEDIES[(rule, drawn.is_edge)].format(name=_named(drawn))
    slot, target = ("relation", "kind") if drawn.is_edge else ("element", "element-id")
    return _REMEDIES[rule].format(what=what, slot=slot, target=target)


def _disposition(drawn: Drawn) -> Finding | None:
    """ATTACH-1..ATTACH-3: a drawn construct is attached or ignored with a reason, never neither."""
    reason = bool((drawn.ignored or "").strip())
    rule = _BROKEN.get((drawn.attaches_to is not None, drawn.ignored is not None, reason))
    if rule is None:
        return None
    what = f"edge '{drawn.id}'" if drawn.is_edge else f"node '{drawn.id}'"
    return _at(drawn, rule, _MESSAGES[rule].format(what=what),
               _disposition_remedy(drawn, rule, what))


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


def _node_kind(node: Drawn, names: Names, models: Models) -> Finding | None:
    """KIND-1: a node that names its element's kind depicts an element of that kind."""
    element = names.element(node.attaches_to)
    if not node.attached or not node.kinds or element is None:
        return None
    kind = models.vocabulary.elements[element].kind
    if set(node.kinds) & set(drawn_checks.lineage(models, kind)):
        return None
    return _at(
        node,
        "KIND-1",
        f"node '{node.id}' is drawn as {_quoted(list(node.kinds))}, but element "
        f"'{element}' is a '{kind}'.",
        f"Draw node '{node.id}' as '{kind}', or attach it to an element of the kind it "
        "is drawn as.",
    )


def _quoted(names: list[str]) -> str:
    return ", ".join(repr(n) for n in names)


def _listed(names: list[str]) -> str:
    """Names as prose: ``'a'``, ``'a' and 'b'``."""
    quoted = [repr(n) for n in names]
    return quoted[0] if len(quoted) == 1 else f"{', '.join(quoted[:-1])} and {quoted[-1]}"


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


def _endpoint_unattached(edge: Drawn, nodes: dict[str, Drawn], faulted: set[str]
                         ) -> Finding | None:
    """DANGLE-3, for ends that are ignored; an end with a disposition finding has its own."""
    loose = [n for n in (edge.source, edge.target) if not nodes[n].attached]
    if not loose or set(loose) & faulted:
        return None
    return _at(
        edge,
        "DANGLE-3",
        f"edge '{edge.id}' is attached, but {_ignored(loose)}.",
        "Attach the endpoint node to an element, or ignore the edge with a reason.",
    )


def _ignored(ends: list[str]) -> str:
    if len(ends) == 1:
        return f"its endpoint {_listed(ends)} is ignored"
    return f"its endpoints {_listed(ends)} are ignored"


def _labelled(relation: ModelRelation, label: str | None) -> bool:
    return label in (relation.kind, relation.title)


def depicted(edge: Drawn, ends: tuple[str, str], corpus: Corpus) -> list[ModelRelation]:
    """The relations an attached edge between two elements depicts.

    The relation its label names between those elements; else, when an end is an
    element others sit inside (a software system), the relation it names from or to
    those; else, for a sequence message, the one relation between the elements."""
    return _label_named(edge, ends, corpus) or _only_between(edge, ends, corpus)


def _between(ends: tuple[str, str], corpus: Corpus) -> list[ModelRelation]:
    return _exactly(corpus.relations, ends)


def _label_named(edge: Drawn, ends: tuple[str, str], corpus: Corpus) -> list[ModelRelation]:
    """The relations the edge's label names between the elements, or rolled up into them."""
    named = _labelled_as(edge, corpus)
    return _exactly(named, ends) or [r for r in named if _inside(r, ends, corpus)]


def _exactly(relations: list[ModelRelation], ends: tuple[str, str]) -> list[ModelRelation]:
    return [r for r in relations if (r.source, r.target) == ends]


def _labelled_as(edge: Drawn, corpus: Corpus) -> list[ModelRelation]:
    return [r for r in corpus.relations if _labelled(r, edge.attaches_to)]


def _inside(relation: ModelRelation, ends: tuple[str, str], corpus: Corpus) -> bool:
    """Whether a relation runs from within one element to within the other."""
    return corpus.within(relation.source, ends[0]) and corpus.within(relation.target, ends[1])


def _only_between(edge: Drawn, ends: tuple[str, str], corpus: Corpus
                  ) -> list[ModelRelation]:
    """For a sequence message, the one relation between the elements, if only one."""
    between = _between(ends, corpus) if edge.kind == MESSAGE else []
    return between if len(between) == 1 else []


def _declared(ends: tuple[str, str], corpus: Corpus) -> str:
    titles = sorted({r.title for r in _between(ends, corpus)})
    if not titles:
        return f"The architecture declares no relation from '{ends[0]}' to '{ends[1]}'."
    return f"From '{ends[0]}' to '{ends[1]}' it declares {_listed(titles)}."


def _relation_remedy(edge: Drawn, ends: tuple[str, str]) -> str:
    declare = f"Declare a '{edge.attaches_to}' relation from '{ends[0]}' to '{ends[1]}'"
    if edge.notation == MERMAID:
        return (f"{declare}, relabel the edge with a declared relation, or add "
                f"'%% slarti: attach {_named(edge)} <relation>' to the diagram.")
    return f"{declare}, or correct the edge's 'relation'."


def _relation_missing(edge: Drawn, nodes: dict[str, Drawn], names: Names, corpus: Corpus
                      ) -> Finding | None:
    source = names.element(nodes[edge.source].attaches_to)
    target = names.element(nodes[edge.target].attaches_to)
    # An endpoint that resolves to no single element already has its own finding.
    if source is None or target is None or depicted(edge, (source, target), corpus):
        return None
    ends = (source, target)
    return _at(
        edge,
        "DANGLE-2",
        f"edge '{edge.id}' depicts relation '{edge.attaches_to}', which the architecture "
        f"does not declare from '{source}' to '{target}'. {_declared(ends, corpus)}",
        _relation_remedy(edge, ends),
    )


@dataclass(frozen=True)
class _Drawing:
    """What every edge check needs: the nodes by id and which of them are at fault."""

    nodes: dict[str, Drawn]
    faulted: set[str]
    names: Names
    corpus: Corpus


def _edge_attachment(edge: Drawn, drawing: _Drawing) -> Finding | None:
    """DANGLE-2..DANGLE-4: an edge joins drawn nodes and depicts a relation that exists."""
    missing = _endpoint_missing(edge, drawing.nodes)
    if missing or not edge.attached:
        return missing
    return (_endpoint_unattached(edge, drawing.nodes, drawing.faulted)
            or _relation_missing(edge, drawing.nodes, drawing.names, drawing.corpus))


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


def _present(findings: list[Finding | None]) -> list[Finding]:
    return [f for f in findings if f is not None]


def _drawing(corpus: Corpus, names: Names, dispositions: list[Finding]) -> _Drawing:
    nodes = {n.id: n for n in corpus.nodes}
    return _Drawing(nodes, {f.subject for f in dispositions} & set(nodes), names, corpus)


def _drawn_findings(models: Models, names: Names) -> list[Finding]:
    corpus = models.vocabulary
    dispositions = _present([_disposition(d) for d in [*corpus.nodes, *corpus.edges]])
    drawing = _drawing(corpus, names, dispositions)
    return [
        *dispositions,
        *_present([_node_attachment(n, names) for n in corpus.nodes]),
        *_present([_node_kind(n, names, models) for n in corpus.nodes]),
        *_present([_edge_attachment(e, drawing) for e in corpus.edges]),
    ]


def _shown(corpus: Corpus, names: Names) -> drawn_checks.Shown:
    """The elements attached nodes depict, and the relations attached edges depict."""
    nodes = _attached(corpus, names)
    found = [r for e in corpus.edges for r in _edge_relations(e, nodes, corpus)]
    return drawn_checks.Shown({e for e in nodes.values() if e is not None},
                              _indices(corpus, found))


def _attached(corpus: Corpus, names: Names) -> dict[str, str | None]:
    """The element each attached node depicts, by node id."""
    return {n.id: names.element(n.attaches_to) for n in corpus.nodes if n.attached}


def _indices(corpus: Corpus, relations: list[ModelRelation]) -> set[int]:
    return {i for i, r in enumerate(corpus.relations) if any(r is f for f in relations)}


def _edge_relations(edge: Drawn, nodes: dict[str, str | None], corpus: Corpus
                    ) -> list[ModelRelation]:
    """The relations an attached edge between attached nodes depicts."""
    source, target = nodes.get(edge.source), nodes.get(edge.target)
    if not edge.attached or source is None or target is None:
        return []
    return depicted(edge, (source, target), corpus)


def check(models: Models) -> list[Finding]:
    """ATTACH-*, IDENT-*, DANGLE-*, DRAWN-*, KIND-1: diagrams against the architecture."""
    corpus = models.vocabulary
    names = Names.of(corpus)
    return [
        *_drawn_findings(models, names),
        *_ambiguous_names(corpus, names),
        *drawn_checks.check(models, _shown(corpus, names)),
    ]
