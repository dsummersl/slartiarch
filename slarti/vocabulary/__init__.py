from __future__ import annotations

import json
import re
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


_PREFIX_LINE = re.compile(r"^(\s+slarti:\s*).*$", re.MULTILINE)


def imports_vocabulary(text: str) -> bool:
    """Whether a schema's text imports the vocabulary or one of its profiles."""
    return any(name in text for name in importmap())


def localised(text: str, force: bool = False) -> str:
    """A schema's text with the ``slarti`` prefix pointing at this package.

    For tools that resolve imports but take no importmap, such as ``linkml lint``.
    ``force`` localises a schema that imports nothing of slarti's but is imported
    alongside one that does, so its own ``slarti`` prefix cannot undo the mapping."""
    if not force and not imports_vocabulary(text):
        return text
    return _PREFIX_LINE.sub(lambda m: m.group(1) + SCHEMA.parent.as_uri() + "/", text)


def staged(schemas: list[Path], target: Path) -> Path:
    """Copy schemas into ``target`` beside copies of the vocabulary and its profiles, every
    ``slarti:`` import rewritten to the sibling copy.

    For tools that take no importmap and merge prefixes strictly, such as
    ``linkml-convert``; namespaces are left as declared, so converted data keeps its IRIs."""
    sources = {IMPORT: SCHEMA, **PROFILES}
    local = {name: target / f"_slarti_{path.stem}" for name, path in sources.items()}

    def rewrite(text: str) -> str:
        for name, copy in local.items():
            pattern = rf"^(\s*-\s*){re.escape(name)}\s*$"
            replacement = r"\g<1>" + str(copy).replace("\\", "\\\\")
            text = re.sub(pattern, replacement, text, flags=re.MULTILINE)
        return text

    copies = {local[name].with_suffix(".yaml"): path for name, path in sources.items()}
    copies |= {target / schema.name: schema for schema in schemas}
    for copy, source in copies.items():
        copy.write_text(rewrite(source.read_text(encoding="utf-8")), encoding="utf-8")
    return target


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
    "imports_vocabulary",
    "localised",
    "staged",
    "profile_versions",
    "version",
    "write_importmap",
]
