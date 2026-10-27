# Producing vocabulary instances

`slarti` checks instances of its own vocabulary. Any tool that writes them — a
script, a generator, an adapter for a notation `slarti` does not read — is a valid
input. There is no plugin API: `slarti` loads no third-party code. The contract
is the data on this page.

## Configure the inputs

Name one or more files or directories under `instances`, alongside or instead of
LikeC4:

```toml
# slarti.toml (or [tool.slartiarch.paths] in pyproject.toml)
[paths]
linkml = "docs/slarti/linkml"
instances = ["docs/slarti/instances", "build/generated-architecture.json"]
```

A directory contributes every `*.yaml`, `*.yml` and `*.json` file beneath it.
LikeC4 runs only when the `likec4` directory holds a `*.c4` source; a project
whose structure is entirely hand-written or generated instances, or drawn in
Mermaid (see [mermaid.md](mermaid.md)), needs neither Node nor LikeC4.

## The schema

The vocabulary ships inside the package as `slarti/vocabulary/vocabulary.yaml`.
`slartiarch doctor` prints its path and version. A project schema imports it as
`slarti:vocabulary` (see the README) and declares the kinds of element and
relation it uses with `is_a: Element` and `is_a: Relation`.

Each file is validated as a `Corpus` before any seam check runs: against the
project schema when it imports the vocabulary, otherwise against the vocabulary
alone. `Element` and `Relation` are abstract, so a file that declares elements or
relations needs the project schema to say what their `kind`s are.

## Serialization

One file is one `Corpus`: a YAML or JSON mapping with any of three lists.

```yaml
diagrams:
  - id: docs/architecture.md#containers     # unique across every input
    location: {file: docs/architecture.md, line: 12}
    nodes:
      - id: docs/architecture.md#containers/api
        location: {file: docs/architecture.md, line: 14, source_id: api, label: API}
        element: api      # attached: the id or an alias of the element it depicts
      - id: docs/architecture.md#containers/legend
        location: {file: docs/architecture.md, line: 15, label: Legend}
        ignored: the diagram's key, not part of the system   # or ignored, with a reason
    edges:
      - source: docs/architecture.md#containers/api
        target: docs/architecture.md#containers/db
        location: {file: docs/architecture.md, line: 16, label: reads}
        relation: Reads   # the kind (or title) of a relation between the endpoints' elements
elements:
  - id: todo.api          # the permanent identifier the element is resolved by
    kind: Service         # a class in the project schema that is_a Element
    name: API             # required
    aliases: [api]        # optional: other names a diagram may use
    owns: [Task]          # optional: the schema classes this element is responsible for
relations:
  - kind: Reads           # a class in the project schema that is_a Relation
    source: todo.api      # element ids
    target: todo.db
    description: The API reads tasks from the database.
```

A node or edge may also name its structural class in `kind`, with the slots that
class adds: `Participant` (`actor`) and `Message` (`order`, `arrow`) for sequence
diagrams, `Entity` (`attributes`) and `EntityRelationship` (`source_cardinality`,
`target_cardinality`, `identifying`) for entity-relationship diagrams, and
`C4Shape` (`macro`, `external`, `technology`, `description`), `C4Boundary`
(`macro`, `boundary_type`) and `C4Relationship` (`macro`, `technology`,
`description`) for C4 diagrams. A node drawn inside another, such as a shape in a
boundary, names it in `within`. A node may also say which element kinds the
element it depicts must be, in `element_kinds` (`KIND-1`). All are optional; a
plain node or edge needs none of them.

Elements and relations may be split across files; `slarti` reads them as one
architecture. `owns` is the element's half of the ownership seam: a class whose
`owner` annotation names `todo.api` must appear in `todo.api`'s `owns`
(`OWN-1`..`OWN-5`).

### `SourceLocation`

Every diagram, node and edge carries a `location`, so a finding can point at the
source the producer read rather than at the instance file:

| Field       | Required | Meaning                                                       |
| ----------- | -------- | ------------------------------------------------------------- |
| `file`      | yes      | The source file, relative to the project root.                |
| `line`      | no       | The line the construct starts on, from 1. Omit it if unknown. |
| `source_id` | no       | The identifier the construct carries in its own notation.     |
| `label`     | no       | The text the construct shows when rendered.                   |

## Dispositions

Every node and edge must say how it stands to the architecture. It is either
**attached** — a node names the element it depicts in `element`, an edge names the
kind of relation it depicts in `relation` — or **ignored** with a reason in
`ignored`. There is no third state. An undeclared box is exactly the drift `slarti`
exists to surface.

A node attaches by an element's `id` or one of its `aliases`, so diagrams can use
the names they already show. An edge's `relation` must match the `kind` (or title)
of a relation declared from the element its source node depicts to the element its
target node depicts. Two looser matches spare a diagram from restating the model:

- **Roll-up.** An element sits inside another when it names it in `system` or
  `container`, as the C4 profile's `Container` and `Component` do. An edge to or
  from the outer element also depicts a relation of the same name to or from
  anything inside it, at any depth. A context diagram's `user -> todo: manages
  tasks` depicts the declared `user -> todo.cli: manages tasks`.
- **Sequence messages.** A `Message` edge whose `relation` matches nothing depicts
  the relation between its two elements when exactly one is declared, whatever its
  label, so a message can say `load task` where the relation says `reads and
  writes`.

| ID         | Meaning                                                                   |
| ---------- | ------------------------------------------------------------------------- |
| `ATTACH-1` | A node or edge has no disposition.                                        |
| `ATTACH-2` | A node or edge is both attached and ignored.                              |
| `ATTACH-3` | A node or edge is ignored with a blank reason.                            |
| `IDENT-1`  | An id or alias is declared by more than one element.                      |
| `IDENT-2`  | A node attaches through a name that resolves to more than one element.    |
| `DANGLE-1` | A node attaches to a name no element declares.                            |
| `DANGLE-2` | An edge's relation is not declared between its endpoints' elements.       |
| `DANGLE-3` | An attached edge ends at a node that is ignored.                          |
| `DANGLE-4` | An edge ends at a node id no diagram declares.                            |
| `DRAWN-1`  | An element of a kind that must be drawn appears in no diagram (opt-in).   |
| `DRAWN-2`  | A relation of a kind that must be drawn is depicted by no edge (opt-in).  |
| `KIND-1`   | A node's `element_kinds` names no kind its element is, or descends from.  |

Node and edge findings point at the `location` the producer read, not at the
instance file, and their remedies are written in the notation the construct came
from: instance slots for an instance file, `%% slarti:` directives for a Mermaid
diagram. An edge whose endpoint node has no disposition, or a broken one, is not
reported again as `DANGLE-3`; the node's own `ATTACH-*` finding covers it.

### Elements and relations that must be drawn

By default, an element or relation that no diagram draws is not a finding. The
reverse checks, `DRAWN-1` for elements and `DRAWN-2` for relations, are opt-in per
kind. List the kinds in the config, which needs no change to any schema and works
for the C4 profile's kinds as they are:

```toml
# slarti.toml (or [tool.slartiarch.checks] in pyproject.toml)
[checks]
drawn = ["Person", "Container", "Relationship"]
```

or annotate a kind in the project schema:

```yaml
classes:
  Service:
    is_a: Element
    annotations: {drawn: true}
```

Either way, every element of that kind, or of a kind beneath it, must be attached
to by at least one node, and every relation of that kind must be depicted by at
least one attached edge (a roll-up edge counts).

## The built-in LikeC4 adapter

The LikeC4 adapter is one producer among others. It runs `likec4 export json`
over the `likec4` directory and translates the export into the same instances an
instance file holds, one `Corpus` per `.c4` file:

- each LikeC4 element becomes an `Element` with its `kind`, `name`, `description`,
  and `owns` read from its `owns` metadata;
- each relationship becomes a `Relation`, kept with its source element;
- each view becomes a `Diagram`. A node depicting an element is attached to it;
  a group is ignored. An edge that draws a declared relationship is attached by
  that relationship's kind or title; an edge LikeC4 derived from relationships
  between nested elements is ignored, since those relationships are checked as
  declared.

Diagrams, nodes and edges carry a `SourceLocation` whose `file` and `line` point
at the view's declaration in the `.c4` source, and whose `source_id` is LikeC4's
own id. Elements are filed under the `.c4` file that declares them. When an
instance file declares an element with the same id, the instance file wins.

## The built-in Mermaid adapter

The Mermaid adapter is another producer. It parses the sequence and
entity-relationship diagrams in the files named under `mermaid`, in Python, and
emits one `Corpus` of diagrams per file. Dispositions are written as Mermaid
classes and `%% slarti:` comments, so the diagrams render unchanged. Syntax outside
the supported subset is a finding (`MMD-1`..`MMD-4`). [mermaid.md](mermaid.md)
documents the subset, the directives and the findings.

## Malformed input

Malformed input is a finding, not a crash, and it stops the run before any seam
check reads a partial architecture:

| ID      | Meaning                                                               |
| ------- | --------------------------------------------------------------------- |
| `INP-1` | A configured input path does not exist.                               |
| `INP-2` | A file is not a YAML or JSON mapping.                                 |
| `INP-3` | A file does not validate as `Corpus` against the vocabulary or schema. |

Each names the file and a remedy. `slartiarch report --json` lists them with the
rest of the checks.

## Versioning

The vocabulary carries its own `version`, separate from the package's, reported
by `slartiarch doctor` and `slartiarch report --json` under `vocabulary`. It is a
public contract: a change that would reject instances a producer already writes
is a breaking change and moves the version accordingly; adding an optional slot
does not. A producer should record the vocabulary version it targets and check it
against `report --json` in CI.
