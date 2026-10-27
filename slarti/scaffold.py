from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

CONFIG = """# slarti: paths, and opt-ins for slarti's own checks. Settings belong to the tools
# that own them.
[paths]
{structure}linkml = "docs/slarti/linkml"
# linkml_index = "slarti.yaml"  # optional; root schema when splitting across files
shacl = "docs/slarti/shacl"
constraints = "docs/slarti/constraints.yaml"
shacl_valid = "docs/slarti/data/valid"
shacl_invalid = "docs/slarti/data/invalid"
documents = ["docs/architecture.md"]

[checks]
# Kinds every element or relation of which some diagram must draw (DRAWN-1, DRAWN-2).
# drawn = ["Container", "Person"]
"""

LIKEC4_PATHS = 'likec4 = "docs/slarti/likec4"\n'

INSTANCE_PATHS = """instances = ["docs/slarti/instances"]
mermaid = ["docs/architecture.md"]
# likec4 = "docs/slarti/likec4"  # optional; needs Node (see: slartiarch init --likec4)
"""

INSTANCES = """# Vocabulary instances, written by hand. Any tool that emits this shape is an
# equally valid producer; LikeC4 is optional (slartiarch init --likec4).
elements:
  - id: example.api
    kind: Service
    name: API
    owns: [Service, Thing]
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
  project: https://example.org/example/
  linkml: https://w3id.org/linkml/
{prefixes}default_prefix: project
default_range: string
imports:
  - linkml:types
{imports}
classes:
{kinds}  Thing:
    annotations:
      owner: example.api
    description: An example entity, owned by the API {owner}.
    attributes:
      id:
        description: The thing's permanent identifier.
        identifier: true
"""

INSTANCE_SCHEMA = SCHEMA.format(
    prefixes="  slarti: https://dsummersl.github.io/slarti/\n",
    imports="  - slarti:vocabulary\n",
    kinds="""  Service:
    is_a: Element
    annotations:
      owner: example.api
    description: A process that serves requests.
""",
    owner="service",
)

LIKEC4_SCHEMA = SCHEMA.format(prefixes="", imports="", kinds="", owner="container")

CONSTRAINTS = """# The join table between prose and enforcement.
constraints: []
"""

DIAGRAM_SECTION = """## Context

<!-- slarti:begin diagram:index -->
<!-- slarti:end diagram:index -->

"""

DOCUMENT = """# Architecture

{diagram}## Ownership

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


def files(likec4: bool = False) -> dict[str, str]:
    """The scaffold: vocabulary instances by default, a LikeC4 model with ``likec4``."""
    common = {"docs/slarti/constraints.yaml": CONSTRAINTS}
    if likec4:
        return common | {
            "slarti.toml": CONFIG.format(structure=LIKEC4_PATHS),
            "docs/slarti/likec4/example.c4": ARCH,
            "docs/slarti/linkml/example.yaml": LIKEC4_SCHEMA,
            "docs/architecture.md": DOCUMENT.format(diagram=DIAGRAM_SECTION),
        }
    return common | {
        "slarti.toml": CONFIG.format(structure=INSTANCE_PATHS),
        "docs/slarti/instances/architecture.yaml": INSTANCES,
        "docs/slarti/linkml/example.yaml": INSTANCE_SCHEMA,
        "docs/architecture.md": DOCUMENT.format(diagram=""),
    }


DIRECTORIES = (
    "docs/slarti/shacl",
    "docs/slarti/data/valid",
    "docs/slarti/data/invalid",
)


def init(root: Path, likec4: bool = False) -> Scaffolded:
    """Scaffold the conventional layout. Refuses to overwrite anything (I1)."""
    written, skipped = [], []
    for name in DIRECTORIES:
        (root / name).mkdir(parents=True, exist_ok=True)
    for name, body in sorted(files(likec4).items()):
        target = root / name
        if target.exists():
            skipped.append(name)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        written.append(name)
    return Scaffolded(written=written, skipped=skipped)
