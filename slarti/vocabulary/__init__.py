from __future__ import annotations

import json
from functools import cache
from pathlib import Path

import yaml

IMPORT = "slarti:vocabulary"
SCHEMA = Path(__file__).with_name("vocabulary.yaml")


def importmap() -> dict[str, str]:
    """Resolve the vocabulary's import name to the copy shipped in this package."""
    return {IMPORT: str(SCHEMA.with_suffix(""))}


def write_importmap(target: Path) -> Path:
    """Write the importmap as the JSON file LinkML's generators read."""
    target.write_text(json.dumps(importmap()), encoding="utf-8")
    return target


@cache
def version() -> str:
    """The version of the vocabulary contract, as the schema declares it."""
    return str(yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))["version"])


__all__ = ["IMPORT", "SCHEMA", "importmap", "version", "write_importmap"]
