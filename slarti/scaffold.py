from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CONFIG = """# slarti: paths only. Settings belong to the tools that own them.
[paths]
likec4 = "docs/slarti/likec4"
linkml = "docs/slarti/linkml"
# linkml_index = "slarti.yaml"  # optional; root schema when splitting across files
shacl = "docs/slarti/shacl"
constraints = "docs/slarti/constraints.yaml"
shacl_valid = "docs/slarti/data/valid"
shacl_invalid = "docs/slarti/data/invalid"
documents = ["docs/architecture.md"]
"""

ARCH = """specification {
  element system
  element container
}

model {
  example = system 'Example' {
    api = container 'API' {
      metadata {
        owns 'Thing'
      }
    }
  }
}

views {
  view index {
    title 'Landscape'
    include *
  }
}
"""

SCHEMA = """id: https://example.org/example
name: example
prefixes:
  example: https://example.org/example/
  linkml: https://w3id.org/linkml/
default_prefix: example
default_range: string
imports:
  - linkml:types

classes:
  Thing:
    annotations:
      owner: example.api
    description: An example entity, owned by the API container.
    attributes:
      id:
        identifier: true
"""

CONSTRAINTS = """# The join table between prose and enforcement.
constraints: []
"""

DOCUMENT = """# Architecture

## Context

<!-- slarti:begin diagram:index -->
<!-- slarti:end diagram:index -->

## Ownership

<!-- slarti:begin ownership -->
<!-- slarti:end ownership -->

## Schema entities

<!-- slarti:begin linkml_erd -->
<!-- slarti:end linkml_erd -->

## Constraints

<!-- slarti:begin constraints -->
<!-- slarti:end constraints -->

## Unverified invariants

<!-- slarti:begin unverified -->
<!-- slarti:end unverified -->
"""


@dataclass(frozen=True)
class Scaffolded:
    """Files written by init, and files left alone because they existed."""

    written: list[str]
    skipped: list[str]


FILES: dict[str, str] = {
    "slarti.toml": CONFIG,
    "docs/slarti/likec4/example.c4": ARCH,
    "docs/slarti/linkml/example.yaml": SCHEMA,
    "docs/slarti/constraints.yaml": CONSTRAINTS,
    "docs/architecture.md": DOCUMENT,
}

DIRECTORIES = (
    "docs/slarti/shacl",
    "docs/slarti/data/valid",
    "docs/slarti/data/invalid",
)


def init(root: Path) -> Scaffolded:
    """Scaffold the conventional layout. Refuses to overwrite anything (I1)."""
    written, skipped = [], []
    for name in DIRECTORIES:
        (root / name).mkdir(parents=True, exist_ok=True)
    for name, body in sorted(FILES.items()):
        target = root / name
        if target.exists():
            skipped.append(name)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        written.append(name)
    return Scaffolded(written=written, skipped=skipped)
