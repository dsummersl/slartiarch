from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import yaml
from linkml_runtime import SchemaView
from rdflib import Graph
from rdflib.namespace import SH
from rdflib.term import URIRef

from slarti import instances, vocabulary
from slarti.adapters import likec4, mermaid
from slarti.config import Config
from slarti.instances import Corpus


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
    """Lazily loaded vocabulary instances, the LinkML schema and the SHACL shapes."""

    config: Config
    _likec4: likec4.Documents | None = field(default=None, repr=False)

    @property
    def likec4(self) -> likec4.Documents:
        """The LikeC4 adapter's instances, keyed by the ``.c4`` file declaring them."""
        if self._likec4 is None:
            self._likec4 = likec4.produce(self.config)
        return self._likec4

    @cached_property
    def mermaid(self) -> mermaid.Produced:
        """The Mermaid adapter's instances and the findings it raised reading the diagrams."""
        return mermaid.produce(self.config)

    @cached_property
    def instances(self) -> instances.Corpus:
        return instances.load(self.config)

    @cached_property
    def vocabulary(self) -> Corpus:
        """Every producer's instances in one corpus: the adapters', then the instance files'."""
        adapted = Corpus()
        for documents in (self.likec4, self.mermaid.documents):
            for file, raw in sorted(documents.items()):
                instances.add(adapted, file, raw)
        return adapted.merged(self.instances)

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
