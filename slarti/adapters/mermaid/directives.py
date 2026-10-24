from __future__ import annotations

import re
from dataclasses import dataclass, field

from slarti.adapters.mermaid.blocks import Directive
from slarti.adapters.mermaid.diagram import Instance, Line, Parsed, Shape

EVERYTHING = "*"

_EDGE = re.compile(r"^(?P<verb>attach|ignore)\s+(?P<source>\S+)\s+->\s+(?P<target>\S+)"
                   r"(?:\s+(?P<rest>.*))?$")
_NODE = re.compile(r"^(?P<verb>attach|ignore|alias)\s+(?P<name>\S+)(?:\s+(?P<rest>.*))?$")


class Malformed(Exception):
    """Raised for a ``%% slarti:`` directive that says nothing slarti can apply."""

    def __init__(self, directive: Directive, problem: str) -> None:
        super().__init__(problem)
        self.directive = directive
        self.problem = problem


@dataclass
class Dispositions:
    """What a diagram's directives say about its nodes and edges."""

    attach: dict[str, str] = field(default_factory=dict)
    ignore: dict[str, str] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    attach_edges: dict[tuple[str, str], str] = field(default_factory=dict)
    ignore_edges: dict[tuple[str, str], str] = field(default_factory=dict)
    named: dict[str, Directive] = field(default_factory=dict)
    paired: dict[tuple[str, str], Directive] = field(default_factory=dict)

    def element(self, name: str) -> str:
        return self.aliases.get(name, name)

    def attached(self, name: str) -> str | None:
        """The element a directive attaches a node to, through the diagram's aliases."""
        target = self.attach.get(name)
        return None if target is None else self.element(target)

    def blanket(self) -> Instance:
        """The disposition ``ignore *`` gives whatever nothing else disposes of."""
        reason = self.ignore.get(EVERYTHING)
        return {} if reason is None else {"ignored": reason}


def _rest(match: re.Match[str]) -> str:
    return (match.group("rest") or "").strip()


def _single(directive: Directive, rest: str) -> str:
    if not rest or len(rest.split()) != 1:
        raise Malformed(directive, "it names no element, or more than one")
    return rest


def _edge(found: Dispositions, directive: Directive, match: re.Match[str]) -> None:
    pair = (match.group("source"), match.group("target"))
    rest = _rest(match)
    if match.group("verb") == "attach":
        if not rest:
            raise Malformed(directive, "it names no relation")
        found.attach_edges[pair] = rest
    else:
        found.ignore_edges[pair] = rest
    found.paired[pair] = directive


def _node(found: Dispositions, directive: Directive, match: re.Match[str]) -> None:
    verb, name = match.group("verb"), match.group("name")
    if name == EVERYTHING and verb != "ignore":
        raise Malformed(directive, f"'{EVERYTHING}' can only be ignored")
    if verb == "ignore":
        found.ignore[name] = _rest(match)
    else:
        slots = {"attach": found.attach, "alias": found.aliases}
        slots[verb][name] = _single(directive, _rest(match))
    if name != EVERYTHING:
        found.named[name] = directive


def read(directives: list[Directive]) -> tuple[Dispositions, list[Malformed]]:
    """Every directive applied in order, and the ones that could not be."""
    found, malformed = Dispositions(), []
    for directive in directives:
        try:
            _apply(found, directive)
        except Malformed as exc:
            malformed.append(exc)
    return found, malformed


def _apply(found: Dispositions, directive: Directive) -> None:
    edge = _EDGE.match(directive.text)
    if edge:
        _edge(found, directive, edge)
        return
    node = _NODE.match(directive.text)
    if node is None:
        raise Malformed(directive, "it is not attach, ignore or alias")
    _node(found, directive, node)


def _undrawn_nodes(found: Dispositions, parsed: Parsed) -> list[Malformed]:
    return [Malformed(d, f"the diagram draws no node '{name}'")
            for name, d in found.named.items() if name not in parsed.nodes]


def _undrawn_edges(found: Dispositions, parsed: Parsed) -> list[Malformed]:
    drawn = {(e.source, e.target) for e in parsed.edges}
    return [Malformed(d, f"the diagram draws no edge from '{pair[0]}' to '{pair[1]}'")
            for pair, d in found.paired.items() if pair not in drawn]


def dangling(found: Dispositions, parsed: Parsed) -> list[Malformed]:
    """Directives naming a node, or a pair of nodes, the diagram never draws."""
    return [*_undrawn_nodes(found, parsed), *_undrawn_edges(found, parsed)]


def _explicit(slot: str, attached: str | None, ignored: str | None) -> Instance:
    """What directives say: attached, ignored, both (which a check reports), or nothing."""
    said: Instance = {}
    if attached is not None:
        said[slot] = attached
    if ignored is not None:
        said["ignored"] = ignored
    return said


def _classed(found: Dispositions, shape: Shape) -> Instance:
    if not shape.classes:
        return {}
    return {"element": found.element(shape.source_id), "element_kinds": list(shape.classes)}


def node(found: Dispositions, shape: Shape) -> Instance:
    """A node's disposition: directives first, then its classes, then a blanket ignore."""
    name = shape.source_id
    explicit = _explicit("element", found.attached(name), found.ignore.get(name))
    return explicit or _classed(found, shape) or found.blanket()


def _ended(pair: tuple[str, str], nodes: dict[str, Instance]) -> Instance:
    ignored = next((end for end in pair if "ignored" in nodes[end]), None)
    return {} if ignored is None else {"ignored": f"it ends at '{ignored}', which is ignored."}


def _labelled(line: Line) -> Instance:
    return {"relation": line.label} if line.label else {}


def edge(found: Dispositions, line: Line, nodes: dict[str, Instance]) -> Instance:
    """An edge's disposition: directives first; an ignored end ignores it; else its label."""
    pair = (line.source, line.target)
    explicit = _explicit("relation", found.attach_edges.get(pair), found.ignore_edges.get(pair))
    return explicit or _ended(pair, nodes) or _labelled(line) or found.blanket()
