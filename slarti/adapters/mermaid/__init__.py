from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from slarti.adapters.mermaid import c4, directives, er, sequence
from slarti.adapters.mermaid.blocks import Block, files_for, read
from slarti.adapters.mermaid.diagram import Instance, Parsed, Shape, Unsupported
from slarti.config import Config
from slarti.domain import Finding, Severity

Documents = dict[str, Instance]

READERS: dict[str, Callable[[str], Parsed]] = {
    sequence.HEADER: sequence.read,
    er.HEADER: er.read,
    **dict.fromkeys(c4.HEADERS, c4.read),
}

SUBSET_DOC = "docs/mermaid.md"


@dataclass
class Produced:
    """The Mermaid adapter's instances, keyed by the file declaring them, and its findings."""

    documents: Documents = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    diagrams: int = 0


def _at(block: Block, rule: str, line: int, message: str, remedy: str) -> Finding:
    return Finding(id=rule, severity=Severity.error, file=block.file, line=line,
                   subject=block.id, message=message, remedy=remedy)


def _missing(configured: str) -> Finding:
    return Finding(
        id="MMD-1",
        severity=Severity.error,
        file=configured,
        subject=configured,
        message=f"Mermaid input '{configured}' does not exist.",
        remedy="Create the file or directory, or remove it from 'mermaid' in the config.",
    )


def _header(block: Block) -> tuple[str, int]:
    """The diagram type a block declares, and the line it declares it on."""
    for number, text in enumerate(block.text.splitlines(), start=1):
        if text.strip():
            return text.split()[0], number
    return "", 1


def _unsupported_type(block: Block, header: str, line: int) -> Finding:
    shown = f"'{header}'" if header else "no diagram type"
    return _at(
        block, "MMD-2", block.line(line),
        f"diagram {block.id} declares {shown}, which slarti cannot read.",
        f"Draw it as one of {', '.join(sorted(READERS))} (see {SUBSET_DOC}), or move it "
        "out of the configured Mermaid inputs.",
    )


def _unsupported_syntax(block: Block, header: str, exc: Unsupported) -> Finding:
    return _at(
        block, "MMD-3", block.line(exc.line),
        f"'{exc.text}' is outside the supported {header} subset.",
        f"Rewrite the line with the syntax {SUBSET_DOC} lists for {header}, or move the "
        "diagram out of the configured Mermaid inputs.",
    )


def _malformed(block: Block, problem: directives.Malformed) -> Finding:
    directive = problem.directive
    return _at(
        block, "MMD-4", directive.line,
        f"directive 'slarti: {directive.text}' cannot be applied: {problem.problem}.",
        "Write 'attach <node> <element>', 'ignore <node> <reason>', 'alias <name> "
        "<element>', or the same with '<source> -> <target>' for an edge, naming what the "
        "diagram draws.",
    )


def _location(block: Block, line: int, source_id: str, label: str) -> Instance:
    return {"file": block.file, "line": block.line(line), "source_id": source_id,
            "label": label}


def _instances(block: Block, parsed: Parsed, found: directives.Dispositions) -> Instance:
    def node_id(name: str) -> str:
        return f"{block.id}/{name}"

    def within(shape: Shape) -> Instance:
        return {} if shape.within is None else {"within": node_id(shape.within)}

    shown = {name: directives.node(found, shape) for name, shape in parsed.nodes.items()}
    nodes = [
        {"id": node_id(name), "kind": shape.kind,
         "location": _location(block, shape.line, name, shape.label)}
        | within(shape) | shape.extra | shown[name]
        for name, shape in parsed.nodes.items()
    ]
    edges = [
        {"kind": line.kind, "source": node_id(line.source), "target": node_id(line.target),
         "location": _location(block, line.line, f"{line.source}->{line.target}", line.label)}
        | line.extra | directives.edge(found, line, shown)
        for line in parsed.edges
    ]
    return {"id": block.id, "location": {"file": block.file, "line": block.line(1),
                                         "label": parsed.title or block.title},
            "nodes": nodes, "edges": edges}


def translate(block: Block) -> tuple[Instance | None, list[Finding]]:
    """A block as a vocabulary diagram, or the findings that say why it cannot be one."""
    header, line = _header(block)
    reader = READERS.get(header)
    if reader is None:
        return None, [_unsupported_type(block, header, line)]
    try:
        parsed = reader(block.text)
    except Unsupported as exc:
        return None, [_unsupported_syntax(block, header, exc)]
    found, malformed = directives.read(block.directives)
    problems = [*malformed, *directives.dangling(found, parsed)]
    return _instances(block, parsed, found), [_malformed(block, p) for p in problems]


def _add(produced: Produced, block: Block) -> None:
    produced.diagrams += 1
    diagram, findings = translate(block)
    produced.findings.extend(findings)
    if diagram is not None:
        document = produced.documents.setdefault(block.file, {"diagrams": []})
        document["diagrams"].append(diagram)


def produce(config: Config) -> Produced:
    """Every configured Mermaid diagram as vocabulary instances; none when none is configured."""
    produced = Produced()
    for configured in config.mermaid:
        path = config.root / configured
        if not path.exists():
            produced.findings.append(_missing(configured))
            continue
        for file in files_for(path):
            for block in read(file, config.rel(file)):
                _add(produced, block)
    return produced
