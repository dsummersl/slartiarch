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
whose structure is entirely hand-written or generated instances needs neither
Node nor LikeC4.

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
target node depicts.

| ID      | Meaning                                                                   |
| ------- | ------------------------------------------------------------------------- |
| `DSP-1` | A node or edge has no disposition.                                        |
| `DSP-2` | A node or edge is both attached and ignored.                              |
| `DSP-3` | A node or edge is ignored with a blank reason.                            |
| `IDN-1` | An id or alias is declared by more than one element.                      |
| `IDN-2` | A node attaches through a name that resolves to more than one element.    |
| `DNG-1` | A node attaches to a name no element declares.                            |
| `DNG-2` | An edge's relation is not declared between its endpoints' elements.       |
| `DNG-3` | An attached edge ends at a node that is ignored or unattached.            |
| `DNG-4` | An edge ends at a node id no diagram declares.                            |
| `VIS-1` | An element of a kind that must be drawn appears in no diagram (opt-in).   |

Node and edge findings point at the `location` the producer read, not at the
instance file. The reverse check is opt-in per element kind: annotate the kind in
the project schema, and every element of that kind, or of a kind beneath it, must
be attached to by at least one node.

```yaml
classes:
  Service:
    is_a: Element
    annotations: {drawn: true}
```

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
