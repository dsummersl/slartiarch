from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import yaml
from linkml_runtime import SchemaView
from rdflib import Graph
from rdflib.namespace import SH
from rdflib.term import URIRef

from slarti import instances, proc, vocabulary
from slarti.config import Config
from slarti.domain import Element, Relation
from slarti.instances import Corpus


class ModelError(Exception):
    """Raised when a delegated tool cannot produce a model dump."""


@dataclass(frozen=True)
class Architecture:
    """Architectural elements and relations, from LikeC4's export or instance files."""

    elements: dict[str, Element]
    relations: tuple[Relation, ...]
    views: tuple[str, ...]

    def has_relation(self, source: str, target: str) -> bool:
        return any(r.source == source and r.target == target for r in self.relations)


def _parse_owns(metadata: dict[str, str]) -> list[str]:
    raw = metadata.get("owns", "")
    return sorted(part.strip() for part in raw.split(",") if part.strip())


def _element(raw: dict[str, object]) -> Element:
    metadata = raw.get("metadata") or {}
    assert isinstance(metadata, dict)
    return Element(
        id=str(raw["id"]),
        title=str(raw.get("title", "")),
        kind=str(raw.get("kind", "")),
        owns=_parse_owns(metadata),
    )


def _relation(raw: dict[str, object]) -> Relation:
    source = raw["source"]
    target = raw["target"]
    assert isinstance(source, dict) and isinstance(target, dict)
    return Relation(
        source=str(source["model"]),
        target=str(target["model"]),
        title=str(raw.get("title", "")),
    )


def parse_likec4(payload: dict[str, object]) -> Architecture:
    """Build the model from a `likec4 export json` payload."""
    raw_elements = _mapping(payload, "elements")
    raw_relations = _mapping(payload, "relations")
    elements = {key: _element(value) for key, value in sorted(raw_elements.items())}
    relations = tuple(_relation(raw_relations[key]) for key in sorted(raw_relations))
    views = tuple(sorted(_mapping(payload, "views")))
    return Architecture(elements=elements, relations=relations, views=views)


def _mapping(payload: dict[str, object], key: str) -> dict[str, dict[str, object]]:
    raw = payload.get(key) or {}
    if not isinstance(raw, dict):
        raise ModelError(f"Expected '{key}' to be a mapping in the LikeC4 export.")
    return raw


EMPTY = Architecture(elements={}, relations=(), views=())


def export_likec4(config: Config) -> Architecture:
    """Invoke `likec4 export json` and parse the result; empty when LikeC4 is not used."""
    if not config.likec4_enabled():
        return EMPTY
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "model.json"
        argv = proc.likec4(["export", "json", "-o", str(out), str(config.path("likec4"))])
        result = proc.run(argv, cwd=config.root)
        if result.code != 0 or not out.is_file():
            raise ModelError(f"likec4 export json failed:\n{result.stderr or result.stdout}")
        payload = json.loads(out.read_text(encoding="utf-8"))
    return parse_likec4(payload)


def shape_names(files: list[Path]) -> dict[str, Path]:
    """Every SHACL shape IRI, as a CURIE, mapped to the file declaring it."""
    found: dict[str, Path] = {}
    for path in files:
        graph = Graph()
        graph.parse(path, format="turtle")
        for subject in sorted(set(graph.subjects(predicate=SH.targetClass)), key=str):
            if isinstance(subject, URIRef):
                found[graph.namespace_manager.normalizeUri(subject).strip("<>")] = path
    return found


def shape_line(path: Path, curie: str) -> int | None:
    """Best-effort line number for a shape declaration in a Turtle file."""
    local = curie.rsplit(":", maxsplit=1)[-1]
    for number, text in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if text.startswith((curie, local)) or text.startswith(f":{local}"):
            return number
    return None


@dataclass
class Models:
    """Lazily loaded views of both backends, plus the SHACL shapes."""

    config: Config
    _likec4: Architecture | None = field(default=None, repr=False)

    @property
    def likec4(self) -> Architecture:
        if self._likec4 is None:
            self._likec4 = export_likec4(self.config)
        return self._likec4

    @cached_property
    def instances(self) -> instances.Corpus:
        return instances.load(self.config)

    @cached_property
    def vocabulary(self) -> Corpus:
        """Every element and relation as a vocabulary instance; LikeC4's export is translated here."""
        corpus = self.instances
        likec4 = self.likec4
        source = self.config.paths["likec4"]
        return Corpus(
            elements=likec4.elements | corpus.elements,
            relations=[*likec4.relations, *corpus.relations],
            element_files=dict.fromkeys(likec4.elements, source) | corpus.element_files,
            findings=corpus.findings,
            files=corpus.files,
        )

    @cached_property
    def architecture(self) -> Architecture:
        """The vocabulary's elements and relations, plus LikeC4's views."""
        corpus = self.vocabulary
        return Architecture(
            elements=corpus.elements,
            relations=tuple(corpus.relations),
            views=self.likec4.views,
        )

    @cached_property
    def schema(self) -> SchemaView | None:
        index = self.config.schema_index()
        if index is None:
            return None
        return SchemaView(str(index), importmap=vocabulary.importmap())

    @cached_property
    def _schema_id_map(self) -> dict[str, str]:
        """Schema id → relative path for every file in the configured LinkML directory."""
        result: dict[str, str] = {}
        for path in self.config.schema_files():
            doc = yaml.safe_load(path.read_text())
            if isinstance(doc, dict) and "id" in doc:
                result[doc["id"]] = self.config.rel(path)
        return result

    @cached_property
    def schema_id_set(self) -> set[str]:
        return set(self._schema_id_map)

    def schema_file_for(self, class_name: str) -> str:
        """Relative path of the project file that declares the given class."""
        view = self.schema
        if view is None:
            return self.config.paths["linkml"]
        cls = view.get_class(class_name)
        if cls is not None and cls.from_schema in self._schema_id_map:
            return self._schema_id_map[cls.from_schema]
        index = self.config.schema_index()
        return self.config.rel(index) if index else self.config.paths["linkml"]

    @cached_property
    def shapes(self) -> dict[str, Path]:
        return shape_names(self.config.shape_files())

    def class_annotation(self, name: str, key: str) -> str | None:
        view = self.schema
        if view is None:
            return None
        cls = view.get_class(name)
        annotation = cls.annotations.get(key) if cls is not None else None
        return None if annotation is None else str(annotation.value)
