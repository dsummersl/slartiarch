from __future__ import annotations

from lark import Token, Tree

from slarti.adapters.mermaid.diagram import Handler, Line, Parsed, parse, text, tokens, walk

HEADER = "sequenceDiagram"
PARTICIPANT = "Participant"
MESSAGE = "Message"


def _lifeline(parsed: Parsed, tree: Tree[Token], actor: bool) -> None:
    name, *label = [*tokens(tree, "ID"), *tokens(tree, "LABEL")]
    node = parsed.node(name, text(label[0]) if label else "")
    node.extra["actor"] = actor


def _participant(parsed: Parsed, tree: Tree[Token]) -> None:
    _lifeline(parsed, tree, actor=False)


def _actor(parsed: Parsed, tree: Tree[Token]) -> None:
    _lifeline(parsed, tree, actor=True)


def _message(parsed: Parsed, tree: Tree[Token]) -> None:
    source, target = tokens(tree, "ID")
    arrow, label = tokens(tree, "ARROW")[0], tokens(tree, "TEXT")[0]
    parsed.node(source)
    parsed.node(target)
    extra = {"order": len(parsed.edges) + 1, "arrow": str(arrow).rstrip("+-")}
    parsed.edges.append(Line(str(source), str(target), source.line or 1, text(label),
                             MESSAGE, extra))


def _note(parsed: Parsed, tree: Tree[Token]) -> None:
    for name in tokens(tree, "ID"):
        parsed.node(name)


def _title(parsed: Parsed, tree: Tree[Token]) -> None:
    rest = tokens(tree, "REST")
    parsed.title = text(rest[0]).lstrip(":").strip() if rest else ""


HANDLERS: dict[str, Handler] = {
    "participant": _participant,
    "actor": _actor,
    "message": _message,
    "note": _note,
    "title": _title,
}


def read(source: str) -> Parsed:
    """The participants and messages of a sequence diagram, in the order it draws them."""
    return walk(Parsed(PARTICIPANT), parse("sequence", source), HANDLERS)
