from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import yaml

IMPORT = "slarti:vocabulary"
SCHEMA = Path(__file__).with_name("vocabulary.yaml")

# Optional profiles: schemas a project may import, which slarti's checks never assume.
PROFILES = {"slarti:c4": Path(__file__).with_name("c4.yaml")}


def importmap() -> dict[str, str]:
    """Resolve the vocabulary's and each profile's import name to the copy in this package."""
    schemas = {IMPORT: SCHEMA, **PROFILES}
    return {name: str(path.with_suffix("")) for name, path in schemas.items()}


def write_importmap(target: Path) -> Path:
    """Write the importmap as the JSON file LinkML's generators read."""
    target.write_text(json.dumps(importmap()), encoding="utf-8")
    return target


@cache
def _schema_version(schema: Path) -> str:
    return str(yaml.safe_load(schema.read_text(encoding="utf-8"))["version"])


def version() -> str:
    """The version of the vocabulary contract, as the schema declares it."""
    return _schema_version(SCHEMA)


def profile_versions() -> dict[str, str]:
    """The version of each optional profile, keyed by its import name."""
    return {name: _schema_version(path) for name, path in PROFILES.items()}


__all__ = [
    "IMPORT",
    "PROFILES",
    "SCHEMA",
    "importmap",
    "profile_versions",
    "version",
    "write_importmap",
]
