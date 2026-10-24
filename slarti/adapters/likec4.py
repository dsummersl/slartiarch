from __future__ import annotations

import json
import re
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from slarti import proc
from slarti.config import Config

Instance = dict[str, Any]
Documents = dict[str, Instance]

GROUP_REASON = "a LikeC4 group, which frames other nodes and depicts no element."
DERIVED_REASON = (
    "LikeC4 derived this edge from relations between nested elements; "
    "those relations are checked where they are declared."
)


class AdapterError(Exception):
    """Raised when LikeC4 cannot produce the export the adapter translates."""


@dataclass(frozen=True)
class Sources:
    """The ``.c4`` files, read once so constructs the export leaves unlocated can be found."""

    fallback: str
    lines: dict[str, list[str]]

    @classmethod
    def read(cls, config: Config) -> Sources:
        directory = config.path("likec4")
        files = sorted(directory.rglob("*.c4")) if directory.is_dir() else []
        lines = {config.rel(p): p.read_text(encoding="utf-8").splitlines() for p in files}
        return cls(fallback=config.paths["likec4"], lines=lines)

    def find(self, *patterns: str) -> tuple[str, int | None]:
        """The first file and line matching any pattern, else the LikeC4 directory."""
        pattern = re.compile("|".join(f"(?:{p})" for p in patterns))
        found = ((file, _first_line(lines, pattern)) for file, lines in self.lines.items())
        return next(((f, n) for f, n in found if n is not None), (self.fallback, None))

    def element(self, identifier: str, kind: str) -> tuple[str, int | None]:
        local, kind = re.escape(identifier.rsplit(".", 1)[-1]), re.escape(kind)
        return self.find(rf"\s*{local}\s*=\s*{kind}\b", rf"\s*{kind}\s+{local}\b")

    def view(self, identifier: str) -> tuple[str, int | None]:
        return self.find(rf"\s*view\s+{re.escape(identifier)}\b")


def _first_line(lines: list[str], pattern: re.Pattern[str]) -> int | None:
    return next((n for n, text in enumerate(lines, start=1) if pattern.match(text)), None)


def _listed(raw: Instance, key: str) -> list[Any]:
    return list(raw.get(key) or [])


def _mapping(payload: Instance, key: str) -> dict[str, Instance]:
    raw = payload.get(key) or {}
    if not isinstance(raw, dict):
        raise AdapterError(f"Expected '{key}' to be a mapping in the LikeC4 export.")
    return raw


def _owns(raw: Instance) -> list[str]:
    metadata = raw.get("metadata") or {}
    owns = str(metadata.get("owns", "")) if isinstance(metadata, dict) else ""
    return sorted(part.strip() for part in owns.split(",") if part.strip())


def _text(raw: Instance, key: str) -> str:
    value = raw.get(key)
    if isinstance(value, dict):
        value = value.get("txt") or value.get("md")
    return "" if value is None else str(value)


def _element(raw: Instance) -> Instance:
    element: Instance = {
        "id": str(raw["id"]),
        "kind": str(raw.get("kind", "")),
        "name": _text(raw, "title"),
        "owns": _owns(raw),
    }
    description = _text(raw, "description")
    return element | ({"description": description} if description else {})


def _relation(raw: Instance) -> Instance:
    relation: Instance = {
        "source": str(raw["source"]["model"]),
        "target": str(raw["target"]["model"]),
        "description": _text(raw, "title"),
    }
    return relation | ({"kind": str(raw["kind"])} if raw.get("kind") else {})


def _location(file: str, line: int | None, source_id: str, label: str) -> Instance:
    location: Instance = {"file": file, "source_id": source_id, "label": label}
    return location | ({"line": line} if line else {})


def _node_id(view: str, node: str) -> str:
    return f"{view}:{node}"


def _node(view: str, raw: Instance, where: tuple[str, int | None]) -> Instance:
    node: Instance = {
        "id": _node_id(view, str(raw["id"])),
        "location": _location(*where, str(raw["id"]), _text(raw, "title")),
    }
    model = raw.get("modelRef")
    return node | ({"element": str(model)} if model else {"ignored": GROUP_REASON})


def _direct(raw: Instance, ends: tuple[str | None, str | None],
            relations: dict[str, Instance]) -> list[Instance]:
    """The relations a drawn edge depicts between exactly the elements its nodes depict."""
    depicted = [relations[r] for r in _listed(raw, "relations") if r in relations]
    return [r for r in depicted if (r["source"], r["target"]) == ends]


def _edges(view: str, raw: Instance, ends: tuple[str | None, str | None],
           relations: dict[str, Instance], where: tuple[str, int | None]) -> list[Instance]:
    """One edge per relation the drawn edge depicts directly; one ignored edge otherwise."""
    base: Instance = {
        "source": _node_id(view, str(raw["source"])),
        "target": _node_id(view, str(raw["target"])),
        "location": _location(*where, str(raw["id"]), _text(raw, "label")),
    }
    direct = _direct(raw, ends, relations)
    if not direct:
        return [base | {"ignored": DERIVED_REASON}]
    return [base | {"relation": r.get("kind") or r["description"]} for r in direct]


def _diagram(identifier: str, raw: Instance, relations: dict[str, Instance],
             sources: Sources) -> Instance:
    where = sources.view(identifier)
    nodes = {str(n["id"]): n for n in _listed(raw, "nodes")}
    return {
        "id": identifier,
        "location": _location(*where, identifier, _text(raw, "title")),
        "nodes": [_node(identifier, n, where) for n in nodes.values()],
        "edges": _diagram_edges(identifier, raw, nodes, relations, where),
    }


def _diagram_edges(view: str, raw: Instance, nodes: dict[str, Instance],
                   relations: dict[str, Instance], where: tuple[str, int | None]
                   ) -> list[Instance]:
    drawn = [_edges(view, e, _ends(nodes, e), relations, where) for e in _listed(raw, "edges")]
    return [edge for edges in drawn for edge in edges]


def _ends(nodes: dict[str, Instance], edge: Instance) -> tuple[str | None, str | None]:
    def model(node: str) -> str | None:
        ref = nodes.get(node, {}).get("modelRef")
        return None if ref is None else str(ref)

    return model(str(edge["source"])), model(str(edge["target"]))


def translate(payload: Instance, sources: Sources) -> Documents:
    """Vocabulary instances from a ``likec4 export json`` payload, keyed by the file declaring them.

    Elements and views are found in the ``.c4`` source; a relation goes with its source element."""
    documents: Documents = defaultdict(lambda: {"diagrams": [], "elements": [], "relations": []})
    homes: dict[str, str] = {}
    for key, raw in sorted(_mapping(payload, "elements").items()):
        element = _element(raw)
        homes[key] = sources.element(key, element["kind"])[0]
        documents[homes[key]]["elements"].append(element)
    relations = {key: _relation(raw) for key, raw in sorted(_mapping(payload, "relations").items())}
    for relation in relations.values():
        documents[homes.get(relation["source"], sources.fallback)]["relations"].append(relation)
    for key, raw in sorted(_mapping(payload, "views").items()):
        diagram = _diagram(key, raw, relations, sources)
        documents[diagram["location"]["file"]]["diagrams"].append(diagram)
    return dict(documents)


def export(config: Config) -> Instance:
    """Run ``likec4 export json`` over the configured directory and read its payload."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "model.json"
        argv = proc.likec4(["export", "json", "-o", str(out), str(config.path("likec4"))])
        result = proc.run(argv, cwd=config.root)
        if result.code != 0 or not out.is_file():
            raise AdapterError(f"likec4 export json failed:\n{result.stderr or result.stdout}")
        payload: Instance = json.loads(out.read_text(encoding="utf-8"))
    return payload


def produce(config: Config) -> Documents:
    """The LikeC4 model as vocabulary instances; none when the project keeps no ``.c4`` source."""
    if not config.likec4_enabled():
        return {}
    return translate(export(config), Sources.read(config))
