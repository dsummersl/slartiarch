from __future__ import annotations

import re

from lark import Token, Tree

from slarti.adapters.mermaid.diagram import (
    Handler,
    Instance,
    Line,
    Parsed,
    Shape,
    Unsupported,
    parse,
    subtrees,
    text,
    tokens,
    walk,
)

HEADERS = ("C4Context", "C4Container", "C4Component")
SHAPE = "C4Shape"
BOUNDARY = "C4Boundary"
RELATIONSHIP = "C4Relationship"
EXTERNAL = "_Ext"

# The C4 profile kind each family of macro draws. A bare Boundary or an
# Enterprise_Boundary draws no kind of element, so it attaches by directive.
PROFILE = {
    "Person": "Person",
    "System": "SoftwareSystem",
    "System_Boundary": "SoftwareSystem",
    "Container": "Container",
    "Container_Boundary": "Container",
    "Component": "Component",
}

_DESCRIBED = ("label", "descr", "sprite", "tags", "link")
_BUILT = ("label", "techn", "descr", "sprite", "tags", "link")
_GROUPED = ("label", "tags", "link")

# Each family's parameters in positional order, as Mermaid's C4 syntax defines them.
PARAMETERS = {
    "Person": _DESCRIBED,
    "System": _DESCRIBED,
    "Container": _BUILT,
    "Component": _BUILT,
    "Boundary": ("label", "type", "tags", "link"),
    "Enterprise_Boundary": _GROUPED,
    "System_Boundary": _GROUPED,
    "Container_Boundary": _GROUPED,
    "Rel": _BUILT,
}

# The parameters the vocabulary records; the rest only change how the diagram renders.
RECORDED = {"label": "label", "techn": "technology", "descr": "description",
            "type": "boundary_type"}

_STORE = re.compile(r"(Db|Queue)$")


class _Outside(Exception):
    """Raised by a handler for a statement the grammar accepts but the subset does not."""

    def __init__(self, line: int) -> None:
        super().__init__(f"line {line}")
        self.line = line


def family(macro: str) -> str:
    """The macro a variant belongs to: ``ContainerDb_Ext`` is a ``Container``."""
    base = macro.removesuffix(EXTERNAL)
    return "Rel" if base.startswith("Rel") else _STORE.sub("", base)


def _parameter(names: tuple[str, ...], position: int, arg: Tree[Token]) -> str:
    named = tokens(arg, "NAMED")
    if named:
        name = str(named[0]).lstrip("$")
        return name if name in names else ""
    return names[position] if position < len(names) else ""


def _given(tree: Tree[Token], names: tuple[str, ...]) -> dict[str, str]:
    """Each argument's value by the parameter it gives, ``""`` for one no parameter takes."""
    args = [a for a in subtrees(tree) if a.data == "arg"]
    return {_parameter(names, position, arg): text(tokens(arg, "STRING")[0])
            for position, arg in enumerate(args)}


def _arguments(tree: Tree[Token], macro: Token) -> Instance:
    """The recorded parameters of a macro, or `_Outside` for one its family does not take."""
    given = _given(tree, PARAMETERS[family(str(macro))])
    if "" in given:
        raise _Outside(macro.line or 1)
    return {RECORDED[name]: value for name, value in given.items() if name in RECORDED}


def _declare(parsed: Parsed, tree: Tree[Token], terminal: str, kind: str) -> Shape:
    macro, name = tokens(tree, terminal)[0], tokens(tree, "ID")[0]
    found = _arguments(tree, macro)
    shape = parsed.node(name, found.pop("label", ""))
    shape.kind = kind
    profile = PROFILE.get(family(str(macro)))
    if profile is not None:
        shape.classes = [profile]
    shape.extra |= {"macro": str(macro)} | found
    return shape


def _element(parsed: Parsed, tree: Tree[Token]) -> None:
    shape = _declare(parsed, tree, "ELEMENT", SHAPE)
    shape.extra["external"] = shape.extra["macro"].endswith(EXTERNAL)


def _boundary(parsed: Parsed, tree: Tree[Token]) -> None:
    shape = _declare(parsed, tree, "BOUNDARY", BOUNDARY)
    before = set(parsed.nodes)
    walk(parsed, tree, HANDLERS)
    for name, node in parsed.nodes.items():
        if name not in before and node.within is None:
            node.within = shape.source_id


def _rel(parsed: Parsed, tree: Tree[Token]) -> None:
    macro = tokens(tree, "REL")[0]
    source, target = tokens(tree, "ID")
    found = _arguments(tree, macro)
    label = found.pop("label", "")
    parsed.edges.append(Line(str(source), str(target), source.line or 1, label, RELATIONSHIP,
                             {"macro": str(macro)} | found))


def _title(parsed: Parsed, tree: Tree[Token]) -> None:
    rest = tokens(tree, "REST")
    parsed.title = text(rest[0]) if rest else ""


HANDLERS: dict[str, Handler] = {
    "element": _element,
    "boundary": _boundary,
    "rel": _rel,
    "title": _title,
}


def _undeclared(parsed: Parsed) -> int | None:
    """The line of the first relationship naming an element the diagram does not declare."""
    return next((e.line for e in parsed.edges
                 if e.source not in parsed.nodes or e.target not in parsed.nodes), None)


def read(source: str) -> Parsed:
    """The elements, boundaries and relationships of a C4 diagram, in the order it draws them."""
    lines = source.splitlines()
    try:
        parsed = walk(Parsed(SHAPE), parse("c4", source), HANDLERS)
        undeclared = _undeclared(parsed)
        if undeclared is not None:
            raise _Outside(undeclared)
    except _Outside as exc:
        raise Unsupported(exc.line, lines[exc.line - 1].strip()) from exc
    return parsed
