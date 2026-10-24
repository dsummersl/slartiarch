from __future__ import annotations

from lark import Token, Tree

from slarti.adapters.mermaid.diagram import (
    Handler,
    Instance,
    Line,
    Parsed,
    parse,
    subtrees,
    text,
    tokens,
    walk,
)

HEADER = "erDiagram"
ENTITY = "Entity"
RELATIONSHIP = "EntityRelationship"

SOURCE_END = {"|o": "zero_or_one", "||": "exactly_one", "}o": "zero_or_more",
              "}|": "one_or_more"}
TARGET_END = {"o|": "zero_or_one", "||": "exactly_one", "o{": "zero_or_more",
              "|{": "one_or_more"}
IDENTIFYING = "--"


def _classed(parsed: Parsed, name: Token, classes: list[Token]) -> None:
    node = parsed.node(name)
    node.classes.extend(str(c) for c in classes if str(c) not in node.classes)


def _entity(parsed: Parsed, tree: Tree[Token]) -> None:
    labels = [text(t) for label in subtrees(tree) for t in label.children if isinstance(t, Token)]
    name = tokens(tree, "NAME")[0]
    parsed.node(name, labels[0] if labels else "")
    _classed(parsed, name, tokens(tree, "CLASS"))


def _attribute(tree: Tree[Token]) -> Instance:
    kind, name = tokens(tree, "TYPE")[0], tokens(tree, "ATTRIBUTE")[0]
    attribute: Instance = {"name": str(name), "type": str(kind)}
    keys = [str(k) for keys in subtrees(tree) for k in tokens(keys, "KEY")]
    comment = tokens(tree, "STRING")
    return (attribute | ({"keys": keys} if keys else {})
            | ({"comment": text(comment[0])} if comment else {}))


def _entity_block(parsed: Parsed, tree: Tree[Token]) -> None:
    entity, *attributes = subtrees(tree)
    _entity(parsed, entity)
    node = parsed.nodes[str(tokens(entity, "NAME")[0])]
    node.extra.setdefault("attributes", []).extend(_attribute(a) for a in attributes)


def _relationship(parsed: Parsed, tree: Tree[Token]) -> None:
    source, target = tokens(tree, "NAME")
    marker = str(tokens(tree, "RELATIONSHIP")[0])
    label = [*tokens(tree, "STRING"), *tokens(tree, "WORD")][0]
    parsed.node(source)
    parsed.node(target)
    extra = {
        "source_cardinality": SOURCE_END[marker[:2]],
        "target_cardinality": TARGET_END[marker[4:]],
        "identifying": marker[2:4] == IDENTIFYING,
    }
    parsed.edges.append(Line(str(source), str(target), source.line or 1, text(label),
                             RELATIONSHIP, extra))


def _class_assign(parsed: Parsed, tree: Tree[Token]) -> None:
    for name in tokens(tree, "NAME"):
        _classed(parsed, name, tokens(tree, "CLASS"))


HANDLERS: dict[str, Handler] = {
    "entity": _entity,
    "entity_block": _entity_block,
    "relationship": _relationship,
    "class_assign": _class_assign,
}


def read(source: str) -> Parsed:
    """The entities, attributes and relationships of an entity-relationship diagram."""
    return walk(Parsed(ENTITY), parse("er", source), HANDLERS)
