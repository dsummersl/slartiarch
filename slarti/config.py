from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_NAME = "slarti.toml"
PYPROJECT_NAME = "pyproject.toml"

DEFAULTS: dict[str, str] = {
    "likec4": "docs/slarti/likec4",
    "linkml": "docs/slarti/linkml",
    "linkml_index": "",
    "shacl": "docs/slarti/shacl",
    "constraints": "docs/slarti/constraints.yaml",
    "shacl_valid": "docs/slarti/data/valid",
    "shacl_invalid": "docs/slarti/data/invalid",
    "diagrams": "docs/diagrams",
}

DOCUMENTS_DEFAULT: list[str] = ["docs/architecture.md"]

# Path keys whose value is a list of paths rather than a single path.
LIST_KEYS = ("documents", "instances", "mermaid")


class ConfigError(Exception):
    """Raised when slarti.toml is missing or malformed."""


@dataclass(frozen=True)
class Config:
    """Resolved project paths. Paths only — no settings are mirrored (I6)."""

    root: Path
    paths: dict[str, str] = field(default_factory=lambda: dict(DEFAULTS))
    documents: list[str] = field(default_factory=lambda: list(DOCUMENTS_DEFAULT))
    instances: list[str] = field(default_factory=list)
    mermaid: list[str] = field(default_factory=list)

    def path(self, key: str) -> Path:
        return self.root / self.paths[key]

    def likec4_enabled(self) -> bool:
        """The LikeC4 adapter runs only when its directory holds a ``*.c4`` source."""
        directory = self.path("likec4")
        return directory.is_dir() and any(directory.rglob("*.c4"))

    def mermaid_enabled(self) -> bool:
        """The Mermaid adapter runs only when the config names Mermaid inputs."""
        return bool(self.mermaid)

    def instance_paths(self) -> list[Path]:
        return [self.root / i for i in self.instances]

    def document_paths(self) -> list[Path]:
        return [self.root / d for d in self.documents]

    def rel(self, target: Path) -> str:
        try:
            return str(target.resolve().relative_to(self.root.resolve()))
        except ValueError:
            return str(target)

    def schema_files(self) -> list[Path]:
        return sorted(self.path("linkml").glob("*.yaml"))

    def schema_index(self) -> Path | None:
        """The root schema file. ``linkml_index`` names one file;
        when absent, the alphabetically first ``*.yaml`` is the index."""
        files = self.schema_files()
        if not files:
            return None
        index_name = self.paths.get("linkml_index", "").strip()
        if index_name:
            candidate = self.path("linkml") / index_name
            if candidate in files:
                return candidate
        return files[0]

    def shape_files(self) -> list[Path]:
        return sorted(self.path("shacl").glob("*.ttl"))


def find_root(start: Path) -> Path | None:
    """Walk upward looking for the directory holding slarti.toml."""
    for candidate in [start.resolve(), *start.resolve().parents]:
        if (candidate / CONFIG_NAME).is_file():
            return candidate
    return None


def _from_raw(root: Path, raw: dict[str, Any], source_label: str) -> Config:
    configured = raw.get("paths", {})
    unknown = sorted(set(configured) - set(DEFAULTS) - set(LIST_KEYS))
    if unknown:
        raise ConfigError(f"Unknown path keys in {source_label}: {', '.join(unknown)}")
    docs = _merge_list(configured.get("documents"), DOCUMENTS_DEFAULT)
    instances = _merge_list(configured.get("instances"), [])
    mermaid = _merge_list(configured.get("mermaid"), [])
    path_keys = {k: str(v) for k, v in configured.items() if k not in LIST_KEYS}
    paths = dict(DEFAULTS) | path_keys
    return Config(root=root, paths=paths, documents=docs, instances=instances, mermaid=mermaid)


def _merge_list(raw: Any, default: list[str]) -> list[str]:
    if raw is None:
        return list(default)
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return [str(raw)]


def _find_pyproject_root(start: Path) -> Path | None:
    for candidate in [start, *start.parents]:
        pyproject = candidate / PYPROJECT_NAME
        if pyproject.is_file():
            raw = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            if "paths" in raw.get("tool", {}).get("slartiarch", {}):
                return candidate
    return None


def _load_toml(root: Path, name: str, source_label: str) -> Config:
    raw: dict[str, Any] = tomllib.loads((root / name).read_text(encoding="utf-8"))
    return _from_raw(root, raw, source_label)


def _load_pyproject(root: Path) -> Config:
    raw: dict[str, Any] = tomllib.loads((root / PYPROJECT_NAME).read_text(encoding="utf-8"))
    return _from_raw(root, raw["tool"]["slartiarch"], f"{PYPROJECT_NAME} [tool.slartiarch]")


def load(start: Path | None = None) -> Config:
    start = (start or Path.cwd()).resolve()

    root = find_root(start)
    if root is not None:
        return _load_toml(root, CONFIG_NAME, CONFIG_NAME)

    root = _find_pyproject_root(start)
    if root is not None:
        return _load_pyproject(root)

    raise ConfigError(
        f"No {CONFIG_NAME} or [tool.slartiarch] section in {PYPROJECT_NAME} found. "
        f"Run 'slarti init' first."
    )
