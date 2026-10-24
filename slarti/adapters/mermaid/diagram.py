from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

from lark import Lark, Token, Tree, UnexpectedInput

Instance = dict[str, Any]


class Unsupported(Exception):
    """Raised when a diagram's text falls outside the supported subset of its type."""

    def __init__(self, line: int, text: str) -> None:
        super().__init__(f"line {line}: {text}")
        self.line = line
        self.text = text


@dataclass
class Shape:
    """A node as the notation draws it, before any disposition is applied."""

    source_id: str
    line: int
    label: str
    kind: str
    classes: list[str] = field(default_factory=list)
    extra: Instance = field(default_factory=dict)
    within: str | None = None


@dataclass
class Line:
    """An edge as the notation draws it, before any disposition is applied."""

    source: str
    target: str
    line: int
    label: str
    kind: str
    extra: Instance = field(default_factory=dict)


@dataclass
class Parsed:
    """What one diagram draws: its nodes in order of appearance and its edges in order."""

    node_kind: str
    title: str = ""
    nodes: dict[str, Shape] = field(default_factory=dict)
    edges: list[Line] = field(default_factory=list)

    def node(self, token: Token, label: str = "") -> Shape:
        """The node a name refers to, drawn at its first mention."""
        name = str(token)
        if name not in self.nodes:
            self.nodes[name] = Shape(name, _line(token), name, self.node_kind)
        if label:
            self.nodes[name].label = label
        return self.nodes[name]


Handler = Callable[[Parsed, Tree[Token]], None]


def _line(token: Token) -> int:
    return token.line or 1


def text(token: Token) -> str:
    """A free-text token without surrounding space or quotes."""
    return str(token).strip().strip('"').strip()


def tokens(tree: Tree[Token], kind: str) -> list[Token]:
    """The direct children of a rule that are tokens of one type."""
    return [c for c in tree.children if isinstance(c, Token) and c.type == kind]


def subtrees(tree: Tree[Token]) -> Iterator[Tree[Token]]:
    return (c for c in tree.children if isinstance(c, Tree))


@cache
def grammar(name: str) -> Lark:
    path = Path(__file__).with_name(f"{name}.lark")
    return Lark(path.read_text(encoding="utf-8"), parser="lalr", maybe_placeholders=False)


def parse(name: str, source: str) -> Tree[Token]:
    """The parse tree of a diagram, or `Unsupported` naming the first line outside the subset."""
    try:
        return grammar(name).parse(source)
    except UnexpectedInput as exc:
        lines = source.splitlines()
        line = min(max(exc.line, 1), len(lines)) if lines else 1
        raise Unsupported(line, lines[line - 1].strip() if lines else "") from exc


def walk(parsed: Parsed, tree: Tree[Token], handlers: dict[str, Handler]) -> Parsed:
    """Visit rules in document order, letting each handler record what it draws."""
    for child in subtrees(tree):
        handler = handlers.get(str(child.data))
        if handler is None:
            walk(parsed, child, handlers)
        else:
            handler(parsed, child)
    return parsed
