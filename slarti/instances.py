from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from linkml.validator import validate
from linkml_runtime import SchemaView

from slarti import vocabulary
from slarti.config import Config
from slarti.domain import Element, Finding, Relation, Severity

SUFFIXES = (".yaml", ".yml", ".json")
TARGET_CLASS = "Corpus"


@dataclass
class Corpus:
    """The architectural elements and relations read from every instance file."""

    elements: dict[str, Element] = field(default_factory=dict)
    relations: list[Relation] = field(default_factory=list)
    element_files: dict[str, str] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)
    files: int = 0

    def owners_of(self, entity: str) -> list[str]:
        return sorted(e.id for e in self.elements.values() if entity in (e.owns or []))


def files_for(path: Path) -> list[Path]:
    """The instance files a configured path names: the file, or a directory's files."""
    if path.is_dir():
        return sorted(p for p in path.rglob("*") if p.is_file() and p.suffix in SUFFIXES)
    return [path]


def _missing(config: Config, path: Path) -> Finding:
    return Finding(
        id="INP-1",
        severity=Severity.error,
        file=config.rel(path),
        subject=config.rel(path),
        message=f"instance input '{config.rel(path)}' does not exist.",
        remedy="Create the file or directory, or remove it from 'instances' in the config.",
    )


def _unreadable(config: Config, path: Path, reason: str) -> Finding:
    return Finding(
        id="INP-2",
        severity=Severity.error,
        file=config.rel(path),
        subject=config.rel(path),
        message=f"instance file cannot be read as a corpus: {reason}",
        remedy="Write the file as a YAML or JSON mapping with diagrams, elements and relations.",
    )


def _nonconforming(config: Config, path: Path, message: str) -> Finding:
    return Finding(
        id="INP-3",
        severity=Severity.error,
        file=config.rel(path),
        subject=config.rel(path),
        message=f"instance file does not conform to the vocabulary: {message}",
        remedy=(
            f"Correct the instance so it validates as '{TARGET_CLASS}' against the "
            "project schema, or declare the missing kind in the schema."
        ),
    )


def _parse(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    return json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)


def _read(config: Config, path: Path) -> tuple[dict[str, Any] | None, Finding | None]:
    try:
        raw = _parse(path)
    except (yaml.YAMLError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        return None, _unreadable(config, path, str(exc).splitlines()[0])
    if not isinstance(raw, dict):
        return None, _unreadable(config, path, "the top level is not a mapping.")
    return raw, None


def validation_schema(index: Path | None) -> SchemaView:
    """The project schema when it extends the vocabulary, else the vocabulary alone."""
    view = SchemaView(str(index or vocabulary.SCHEMA), importmap=vocabulary.importmap())
    if view.get_class(TARGET_CLASS) is None:
        view = SchemaView(str(vocabulary.SCHEMA), importmap=vocabulary.importmap())
    view.merge_imports()
    return view


def _element(raw: dict[str, Any]) -> Element:
    return Element(
        id=str(raw["id"]),
        title=str(raw.get("name", "")),
        kind=str(raw.get("kind", "")),
        owns=sorted(str(o) for o in raw.get("owns") or []),
    )


def _relation(raw: dict[str, Any]) -> Relation:
    title = raw.get("description") or raw.get("kind") or ""
    return Relation(source=str(raw["source"]), target=str(raw["target"]), title=str(title))


def _add(corpus: Corpus, config: Config, path: Path, raw: dict[str, Any]) -> None:
    for element in raw.get("elements") or []:
        corpus.elements[str(element["id"])] = _element(element)
        corpus.element_files[str(element["id"])] = config.rel(path)
    corpus.relations.extend(_relation(r) for r in raw.get("relations") or [])


def _findings(config: Config, path: Path, raw: dict[str, Any], view: SchemaView) -> list[Finding]:
    results = validate(raw, view.schema, TARGET_CLASS).results
    return [_nonconforming(config, path, r.message) for r in results]


def _load_file(corpus: Corpus, config: Config, path: Path, view: SchemaView) -> None:
    corpus.files += 1
    raw, unreadable = _read(config, path)
    findings = [unreadable] if unreadable else _findings(config, path, raw or {}, view)
    corpus.findings.extend(findings)
    if not findings and raw is not None:
        _add(corpus, config, path, raw)


def load(config: Config) -> Corpus:
    """Read and validate every configured instance input, before any seam check runs."""
    corpus = Corpus()
    if not config.instances:
        return corpus
    view = validation_schema(config.schema_index())
    for configured in config.instance_paths():
        if not configured.exists():
            corpus.findings.append(_missing(config, configured))
            continue
        for path in files_for(configured):
            _load_file(corpus, config, path, view)
    return corpus
