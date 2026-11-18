from __future__ import annotations

import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from rdflib import Graph
from rdflib.compare import to_isomorphic
from rdflib.namespace import RDF, SH
from rdflib.term import BNode, Literal, Node, URIRef

from slarti import proc, vocabulary
from slarti.config import Config


@dataclass(frozen=True)
class Validation:
    """The outcome of validating one negative fixture against the shapes."""

    conforms: bool
    report: str
    shapes: frozenset[str] = frozenset()
    error: str | None = None


def load_shapes(config: Config) -> Graph:
    """The hand-written shape files, merged into one graph."""
    graph = Graph()
    for path in config.shape_files():
        graph.parse(path, format="turtle")
    return graph


def merge_shapes(config: Config, target: Path) -> Path:
    """Write the merged shapes graph where pyshacl can read it."""
    target.write_text(load_shapes(config).serialize(format="turtle"), encoding="utf-8")
    return target


def _to_turtle(config: Config, fixture: Path, fixture_class: str | None, tmp: Path) -> Path:
    if fixture.suffix == ".ttl":
        return fixture
    schemas = config.schema_files()
    if not schemas or fixture_class is None:
        raise ValueError(
            f"YAML fixture {config.rel(fixture)} needs 'fixture_class' and a LinkML schema."
        )
    # linkml-convert takes no importmap, so it reads a copy whose slarti imports resolve here.
    staged = vocabulary.staged(schemas, tmp)
    out = tmp / f"{fixture.stem}.ttl"
    argv = [
        "linkml-convert",
        "-s",
        str(staged / schemas[0].name),
        "-C",
        fixture_class,
        "-t",
        "ttl",
        "-o",
        str(out),
        str(fixture),
    ]
    result = proc.run(argv, cwd=config.root)
    if result.code != 0:
        raise ValueError(f"linkml-convert failed for {config.rel(fixture)}: {result.stderr}")
    return out


def _closure(graph: Graph, node: Node) -> Graph:
    """The triples describing a node, following blank nodes."""
    out = Graph()
    todo, seen = [node], set()
    while todo:
        current = todo.pop()
        if current in seen:
            continue
        seen.add(current)
        for triple in graph.triples((current, None, None)):
            out.add(triple)
            if isinstance(triple[2], BNode):
                todo.append(triple[2])
    return out


def _same_shape(shapes: Graph, report: Graph, shape: Node, source: Node) -> bool:
    return bool(to_isomorphic(_closure(shapes, shape)) == to_isomorphic(_closure(report, source)))


def _holders(shapes: Graph, shape: Node) -> Iterator[Node]:
    for predicate in (SH.property, SH.sparql):
        yield from shapes.subjects(predicate, shape)


def _named_owners(shapes: Graph, report: Graph, source: Node) -> set[str]:
    """The named node shapes holding the shape a report result cites as its source."""
    if isinstance(source, URIRef):
        return {_name(shapes, source)}
    same = [s for s in set(shapes.subjects(SH.path)) if _same_shape(shapes, report, s, source)]
    return {_name(shapes, h) for h in _named_holders(shapes, same)}


def _named_holders(shapes: Graph, found: list[Node]) -> list[URIRef]:
    holders = (holder for shape in found for holder in _holders(shapes, shape))
    return [holder for holder in holders if isinstance(holder, URIRef)]


def _name(shapes: Graph, shape: URIRef) -> str:
    return shapes.namespace_manager.normalizeUri(shape).strip("<>")


def _has_path(shapes: Graph, shape: Node, path: Node) -> bool:
    own = any(shapes.triples((shape, SH.path, path)))
    return own or any(
        shapes.value(prop, SH.path) == path for prop in shapes.objects(shape, SH.property)
    )


def _implicated(shapes: Graph, data: Graph, report: Graph) -> frozenset[str]:
    """The named node shapes a violation report actually accuses."""
    names: set[str] = set()
    for result in report.objects(predicate=SH.result):
        source = report.value(result, SH.sourceShape)
        if source is not None:
            names |= _named_owners(shapes, report, source)
            continue
        focus = report.value(result, SH.focusNode)
        path = report.value(result, SH.resultPath)
        for kind in data.objects(focus, RDF.type):
            names |= _shapes_targeting(shapes, kind, path)
    return frozenset(names)


def _shapes_targeting(shapes: Graph, kind: Node, path: Node | None) -> set[str]:
    found = set()
    for shape in shapes.subjects(SH.targetClass, kind):
        if isinstance(shape, URIRef) and (path is None or _has_path(shapes, shape, path)):
            found.add(_name(shapes, shape))
    return found


def _report_graph(text: str) -> Graph:
    graph = Graph()
    graph.parse(data=text, format="turtle")
    return graph


def validate(config: Config, fixture: Path, fixture_class: str | None = None) -> Validation:
    """Run pyshacl over one fixture; a conforming negative fixture is a failure."""
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        try:
            data_path = _to_turtle(config, fixture, fixture_class, tmp)
        except ValueError as exc:
            return Validation(False, "", error=str(exc))
        shapes_path = merge_shapes(config, tmp / "shapes.ttl")
        argv = ["pyshacl", "-s", str(shapes_path), "-f", "turtle", str(data_path)]
        result = proc.run(argv, cwd=config.root)
        data = Graph()
        data.parse(data_path, format="turtle")
    return _validation(config, data, result.stdout + result.stderr)


def _validation(config: Config, data: Graph, text: str) -> Validation:
    try:
        report = _report_graph(text)
    except Exception:  # noqa: BLE001 - pyshacl failed before producing a report
        return Validation(False, text, error=f"pyshacl produced no report:\n{text.strip()}")
    flag = next(report.objects(predicate=SH.conforms), None)
    conforms = isinstance(flag, Literal) and flag.toPython() is True
    shapes = _implicated(load_shapes(config), data, report)
    return Validation(conforms=conforms, report=text, shapes=shapes)
