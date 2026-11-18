from __future__ import annotations

from collections.abc import Callable
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


NO_CONTRACT = "none"
CLASSES_KEY = "classes:"


@dataclass(frozen=True)
class Contract:
    """Where a relation's contract is written: a file, a directory, or one class of a schema."""

    file: str
    directory: bool = False
    lines: tuple[int, int] | None = None

    def covers(self, path: str) -> bool:
        """Whether a file, relative to the project root, is part of the contract."""
        if self.directory:
            return path.startswith(self.file.rstrip("/") + "/")
        return path == self.file


def _indent(text: str) -> int:
    return len(text) - len(text.lstrip())


def _significant(text: str) -> bool:
    stripped = text.strip()
    return bool(stripped) and not stripped.startswith("#")


def _first(lines: list[str], begin: int, wanted: Callable[[str], bool]) -> int | None:
    """The index of the first line from ``begin`` on that is wanted."""
    return next((n for n in range(begin, len(lines)) if wanted(lines[n])), None)


def _block_start(lines: list[str], name: str) -> int | None:
    """The index of a class's key line under the first top-level ``classes:``."""
    heading = _first(lines, 0, lambda text: text.rstrip() == CLASSES_KEY)
    key = f"{name}:"
    return None if heading is None else _first(lines, heading + 1, lambda t: t.strip() == key)


def _block_end(lines: list[str], start: int) -> int:
    """The index just past the last significant line of the block opened at ``start``."""
    depth = _indent(lines[start])
    end = _first(lines, start + 1, lambda t: _significant(t) and _indent(t) <= depth)
    body = [n for n in range(start, end or len(lines)) if _significant(lines[n])]
    return body[-1] + 1


def class_span(path: Path, name: str) -> tuple[int, int] | None:
    """The lines a class's block spans under the top-level ``classes:`` of a schema file."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = _block_start(lines, name)
    return None if start is None else (start + 1, _block_end(lines, start))


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
        produced = {"likec4": self.likec4, "mermaid": self.mermaid.documents}
        for notation, documents in produced.items():
            for file, raw in sorted(documents.items()):
                instances.add(adapted, file, raw, notation)
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

    def contract(self, ref: str) -> Contract | None:
        """Where a relation's contract resolves: a path inside the root, else a schema class."""
        return self._contract_path(ref) or self._contract_class(ref)

    def _contract_path(self, ref: str) -> Contract | None:
        root = self.config.root.resolve()
        candidate = (root / ref).resolve()
        if not candidate.exists() or not candidate.is_relative_to(root):
            return None
        return Contract(file=self.config.rel(candidate), directory=candidate.is_dir())

    def _contract_class(self, ref: str) -> Contract | None:
        view = self.schema
        cls = view.get_class(ref) if view is not None else None
        if cls is None or cls.from_schema not in self._schema_id_map:
            return None
        file = self._schema_id_map[cls.from_schema]
        return Contract(file=file, lines=class_span(self.config.root / file, ref))
