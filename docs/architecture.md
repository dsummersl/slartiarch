# slarti — architecture

This document is generated in part by `slarti` itself (I13). The prose is
user-authored; every region between `slarti:begin` / `slarti:end` markers is
generated from `model/` and must never be hand-edited.

## 1. Introduction and goals

Architecture documents drift, and the drift is invisible: a stale diagram looks
exactly like a fresh one, and an unenforced rule in prose reads exactly like an
enforced one.

**LikeC4** validates structure and generates diagrams. **LinkML** validates
entities and generates schemas and projections. Neither can see the other, and
neither can see the prose document that claims what they enforce. `slarti` owns
exactly those joins:

- LikeC4 ↔ LinkML — the ownership seam.
- Document ↔ rules — the constraint registry.
- Document ↔ models — the drift gate.

Everything else — parsing, validating, rendering, generating — is delegated to
LikeC4, LinkML and pyshacl as subprocesses.

## 2. Definitions

The rest of this document uses these words in a narrow sense. They are defined
here so that a rule, a table row and a finding all mean the same thing.

### 2.1 Layer

A **layer** is *the kind of model a rule can be stated against*, and therefore the
kind of tool that can decide it. Every constraint in the registry declares one, and
the layer determines which enforcer kinds are legal for it:

| Layer | Model | Answers | Decided by | Enforcer kinds |
| --- | --- | --- | --- | --- |
| 1 — structure | LikeC4 | Which components exist, and which may talk to which? | `likec4 validate` + the JSON export | `likec4_element`, `likec4_relation`, `likec4_absent_relation`, `ownership` |
| 2 — schema | LinkML | What entities exist, and what shape is a single instance? | `linkml lint` / `linkml validate` | `linkml_class`, `linkml_slot` |
| 3 — instance | SHACL, run by pyshacl | Given real data, does this cross-field or cross-entity invariant hold? | `pyshacl` over a negative fixture | `shacl_shape` |
| none | — | Anything the three layers cannot see (runtime behaviour, code paths) | a test, or a human | `external`, or `enforced_by: none` with a reason |

The layers are ordered by what they can see, not by importance. Layer 1 can say
that the web container has no relation to the database; it cannot say that a field
is required. Layer 2 can say a slot is required; it cannot say that a subtask's list
matches its parent's. Layer 3 can say that; it cannot say anything about a code path
that never ran. A rule stated at the wrong layer is not enforced — it is only
mentioned — which is why `enforced_by: none` with a reason is a first-class answer.

### 2.2 LikeC4 — the structure layer

LikeC4 owns *the boxes and arrows*: elements, containment, relationships, views.

- **Responsibilities.** Parse `model/arch/*.c4`; reject unknown elements, dangling
  relations and invalid views; generate diagrams (`likec4 codegen mermaid`); expose
  the whole model as JSON (`likec4 export json`).
- **Not responsible for.** Anything about an instance of data. LikeC4 has no notion
  of a field, a type or a cardinality.
- **How `slarti` uses it.** Only the model adapters shell out to it (D5, D6). The
  export feeds the ownership seam and every layer-1 enforcer; `likec4 codegen`
  produces the diagrams that the document generator injects (D9).

### 2.3 LinkML — the schema layer

LinkML owns *the entities*: classes, slots, types, cardinality, and the generators
that project them.

- **Responsibilities.** Validate `model/schema/*.yaml`; resolve it as a `SchemaView`;
  generate SHACL (`gen-shacl`), ER diagrams, and implementation projections
  (`gen-pydantic`, `gen-typescript`, `gen-sqlddl`, `gen-json-schema`); convert YAML
  fixtures to RDF (`linkml-convert`).
- **Not responsible for.** Where an entity lives in the deployed system, and any
  invariant that spans two instances.
- **How `slarti` uses it.** The adapters read the `SchemaView` for the class list and
  the owner annotation on each class; layer-2 enforcers resolve against it.

### 2.4 pyshacl — the instance layer

pyshacl owns *the verdict on real data*: it runs a SHACL shapes graph against a data
graph and reports conformance.

- **Responsibilities.** Given the merged shapes (`model/shapes/*.ttl`, plus anything
  LinkML generated) and one fixture, decide conformance and name every violated
  shape.
- **Not responsible for.** Deciding which fixtures exist or what they prove — that is
  the registry's job.
- **How `slarti` uses it.** Every layer-3 rule declares one negative fixture in
  `model/data/invalid/`. `slarti check` asserts the fixture *fails* and that the
  violation report *names that rule's shape* (`REG-6`, `REG-7`). A shape that stops
  firing is a finding, not a silently passing build.

### 2.5 Enforcer

The named thing that decides a rule: a shape IRI, a `Class.slot`, a LikeC4 relation,
or an ownership pair. A constraint without a resolvable enforcer is a `REG-1`
finding.

### 2.6 Seam

A join between two models that neither model can see: LikeC4 ↔ LinkML (ownership),
document ↔ registry, document ↔ models. Seams are the only thing `slarti` itself
enforces.

## 3. Constraints

- Python 3.11+, distributed as a `uv`-installable CLI.
- Exactly two backends: LikeC4 and LinkML. No abstraction layer over either.
  ADR-0004 (proposed) replaces this with `slarti`'s own vocabulary, produced by
  built-in LikeC4 and Mermaid adapters or by any other tool.
- No cache and no state file: everything is derived on each invocation.
- No JVM, no Docker and no browser on the default path.
- Supported ranges are enforced at runtime: LikeC4 `>=1.59,<2`, LinkML
  `>=1.11,<2`, Node `>=20`, Python `>=3.11,<4`. Outside the range `slarti`
  refuses to run rather than producing possibly-wrong output.

## 4. Context

The people who use `slarti`, the sources they edit, and the tools it delegates to.

<!-- slarti:begin diagram:index -->

```mermaid
---
title: "slarti in context"
---
graph TB
  Architect@{ shape: rectangle, label: "Architect" }
  Agent@{ shape: rectangle, label: "LLM agent" }
  Slarti@{ shape: rectangle, label: "slarti" }
  Likec4@{ shape: rectangle, label: "LikeC4" }
  Linkml@{ shape: rectangle, label: "LinkML" }
  Pyshacl@{ shape: rectangle, label: "pyshacl" }
  Sources@{ shape: rectangle, label: "Model sources" }
  Architect -. "`runs check and docs`" .-> Slarti
  Architect -. "`edits`" .-> Sources
  Agent -. "`runs check --json and applies remedies`" .-> Slarti
  Agent -. "`edits`" .-> Sources
  Slarti -. "`[...]`" .-> Likec4
  Slarti -. "`[...]`" .-> Linkml
  Slarti -. "`validates one negative fixture per rule`" .-> Pyshacl
  Slarti -. "`[...]`" .-> Sources
```

<!-- slarti:end diagram:index -->

## 5. Building block view

Inside `slarti`: the CLI gates on the environment, the runner orders the checks,
the adapters are the only components that talk to LikeC4 and LinkML, and the
document generator is the only component that writes.

<!-- slarti:begin diagram:containers -->

```mermaid
---
title: "Inside slarti"
---
graph TB
  Architect@{ shape: rectangle, label: "Architect" }
  Agent@{ shape: rectangle, label: "LLM agent" }
  subgraph Slarti["`slarti`"]
    Slarti.Cli@{ shape: rectangle, label: "CLI" }
    Slarti.Runner@{ shape: rectangle, label: "Runner" }
    Slarti.Docsgen@{ shape: rectangle, label: "Document generator" }
    Slarti.Env@{ shape: rectangle, label: "Environment gate" }
    Slarti.Settings@{ shape: rectangle, label: "Config" }
    Slarti.Scaffold@{ shape: rectangle, label: "Scaffolder" }
    Slarti.Checks@{ shape: rectangle, label: "Checks" }
    Slarti.Registry@{ shape: rectangle, label: "Registry" }
    Slarti.Findings@{ shape: rectangle, label: "Findings" }
    Slarti.Models@{ shape: rectangle, label: "Model adapters" }
    Slarti.Vocabulary@{ shape: rectangle, label: "Vocabulary" }
  end
  Pyshacl@{ shape: rectangle, label: "pyshacl" }
  Likec4@{ shape: rectangle, label: "LikeC4" }
  Linkml@{ shape: rectangle, label: "LinkML" }
  Sources@{ shape: rectangle, label: "Model sources" }
  Architect -. "`runs check and docs`" .-> Slarti.Cli
  Agent -. "`runs check --json and applies remedies`" .-> Slarti.Cli
  Slarti.Cli -. "`runs the checks`" .-> Slarti.Runner
  Slarti.Cli -. "`regenerates the document`" .-> Slarti.Docsgen
  Slarti.Cli -. "`gates on tool versions`" .-> Slarti.Env
  Slarti.Cli -. "`resolves paths`" .-> Slarti.Settings
  Slarti.Cli -. "`reports the version`" .-> Slarti.Vocabulary
  Slarti.Cli -. "`scaffolds a new project`" .-> Slarti.Scaffold
  Slarti.Runner -. "`collects findings`" .-> Slarti.Checks
  Slarti.Runner -. "`loads the constraints`" .-> Slarti.Registry
  Slarti.Checks -. "`emits findings`" .-> Slarti.Findings
  Slarti.Checks -. "`reads both models`" .-> Slarti.Models
  Slarti.Docsgen -. "`reads the rules`" .-> Slarti.Registry
  Slarti.Models -. "`resolves the vocabulary import`" .-> Slarti.Vocabulary
  Slarti.Docsgen -. "`reads the model`" .-> Slarti.Models
  Slarti.Docsgen -. "`resolves the vocabulary import`" .-> Slarti.Vocabulary
  Slarti.Checks -. "`validates one negative fixture per rule`" .-> Pyshacl
  Slarti.Registry -. "`reads`" .-> Sources
  Slarti.Models -. "`export json`" .-> Likec4
  Slarti.Models -. "`SchemaView`" .-> Linkml
  Slarti.Models -. "`reads`" .-> Sources
  Slarti.Docsgen -. "`delegates diagram generation`" .-> Likec4
  Slarti.Docsgen -. "`writes generated regions only`" .-> Sources
  Slarti.Env -. "`probes the version`" .-> Likec4
  Slarti.Env -. "`probes the version`" .-> Linkml
```

<!-- slarti:end diagram:containers -->

## 6. The ownership seam

Every entity in the schema names the architectural element that owns it, and every
element claims its entities back. The check reads vocabulary `Element` instances, so
it holds the same for LikeC4, hand-written instances or any other producer. Both directions are checked (`OWN-1`..`OWN-5`), because
a dangling pointer and an unclaimed target are different failures.

<!-- slarti:begin ownership -->

| Entity | Owner | Owner title |
| --- | --- | --- |
| Constraint | `slarti.registry` | Registry |
| Element | `slarti.models` | Model adapters |
| Enforcer | `slarti.registry` | Registry |
| Finding | `slarti.findings` | Findings |
| Probe | `slarti.env` | Environment gate |
| ProjectPaths | `slarti.settings` | Config |
| Region | `slarti.docsgen` | Document generator |
| Relation | `slarti.models` | Model adapters |
| Report | `slarti.findings` | Findings |
| Summary | `slarti.findings` | Findings |

<!-- slarti:end ownership -->

## 7. Schema entities

The entities `slarti` reasons about, and how they relate to each other, as derived
from the LinkML schema.

<!-- slarti:begin linkml_erd -->

```mermaid
erDiagram
Constraint {
    string id  
    string decision  
    integer line  
    string reason  
    string statement  
}
Element {
    string id  
    string kind  
    stringList owns  
    string title  
}
Enforcer {
    string fixture  
    string fixture_class  
    EnforcerKind kind  
    string ref  
}
Finding {
    string id  
    string file  
    integer line  
    string message  
    string remedy  
    Severity severity  
    string subject  
}
Probe {
    string detail  
    string location  
    boolean ok  
    string tool  
    string version  
}
ProjectPaths {
    string arch  
    string build  
    string constraints  
    string data_invalid  
    string data_valid  
    string diagrams  
    string document  
    string schema_dir  
    string shapes  
}
Region {
    string name  
    string body  
    integer line  
}
Relation {
    string kind  
    string source  
    string target  
    string title  
}
Report {
    string seam_version  
}
Summary {
    integer checked  
    integer errors  
    integer warnings  
}

Constraint ||--|| Enforcer : "enforced_by"
Report ||--|| Summary : "summary"
Report ||--}o Finding : "findings"
```

<!-- slarti:end linkml_erd -->

## 8. Enforced rules

Each rule below points at an enforcer that `slarti` resolves against the models on
every run. If the enforcer disappears, the rule becomes a `REG-1` finding rather
than a sentence that quietly stops being true.

<!-- slarti:begin constraints -->

| ID | Rule | Enforced by | Decision |
| --- | --- | --- | --- |
| D1 | Every finding carries a stable rule ID and a remedy sentence. | shacl_shape `slarti:FindingCarriesRemedy` | ADR-0002 |
| D2 | A constraint with no enforcer must give a reason. | shacl_shape `slarti:UnenforcedConstraintGivesReason` | ADR-0002 |
| D3 | An enforcer names the thing that enforces the rule. | shacl_shape `slarti:EnforcerNamesWhatItIs` | - |
| D4 | A finding names the file it is about. | linkml_slot `Finding.file` | - |
| D5 | The checks never invoke LikeC4 or LinkML themselves; the adapters do. | likec4_absent_relation `slarti.checks -> likec4` | - |
| D6 | The CLI never reads model sources directly; it goes through the adapters. | likec4_absent_relation `slarti.cli -> sources` | - |
| D7 | The environment gate probes LikeC4 before any command that shells out. | likec4_relation `slarti.env -> likec4` | - |
| D8 | Every domain entity is owned by exactly one container. | ownership `Finding` | ADR-0002 |
| D9 | The document generator writes only generated regions of the sources. | likec4_relation `slarti.docsgen -> sources` | - |

<!-- slarti:end constraints -->

## 9. Unverified invariants

Rules that are stated but not mechanically enforced. This table is the honest
case, not a failure: each entry must say why enforcement is not possible.

<!-- slarti:begin unverified -->

| ID | Rule | Why unenforced |
| --- | --- | --- |
| U1 | slarti never modifies a user-authored file. | Layer 1 can say which container writes to the sources, not that the write touched only a generated region. Verified instead by a test that hashes every user-authored file before and after each command. |
| U2 | Running a delegated tool directly produces the same result as running it via slarti. | No model can assert that a subprocess was passed through unaltered. Verified by a test asserting byte-identical diagnostics. |
| U3 | Generation is idempotent — running slarti docs twice produces identical output. | Idempotence is a property of a run, not of the model. Verified by a test that hashes the tree across two runs. |
| U4 | The Python interfaces the implementation uses are generated from the schema. | No model can assert that a module imports a generated projection rather than a copy of it. Verified instead by a test that regenerates slarti/domain.py from docs/slarti/linkml/slarti.yaml and fails if the committed file differs. |

<!-- slarti:end unverified -->

## 10. Decisions

- **ADR-0001 — Python project.** See `docs/adr/0001-python-project.md`.
- **ADR-0002 — Findings are the interface.** See
  `docs/adr/0002-findings-are-the-interface.md`. Findings, not exit codes, are how
  `slarti` speaks to both humans and agents. Every finding carries a stable rule
  ID, a file, a subject phrased in domain terms, and a remedy sentence; the same
  findings render as text or as JSON. Entities in the registry and the schema are
  shaped around that contract, which is why `Finding`, `Constraint` and `Enforcer`
  are modelled entities with shapes over them.
- **ADR-0003 — The Python interfaces are a LinkML projection.** See
  `docs/adr/0003-python-interfaces-are-a-linkml-projection.md`. The domain classes
  the implementation uses are generated from `model/schema/slarti.yaml` by
  `gen-pydantic` into `slarti/domain.py` and committed; behaviour is hand-written
  around them. Two definitions of one entity is the drift `slarti` exists to catch,
  so the schema is the only one, and a stale projection fails the test suite.

## 11. Risks and technical debt

- Upstream churn in LikeC4's JSON export or LinkML's generators would produce
  wrong findings. Mitigated by a hard version ceiling and a loud refusal to run.
- The registry becomes busywork if it ever stops generating these tables.
- YAML fixtures require a declared `fixture_class` to be converted to RDF;
  Turtle fixtures need nothing. Both are accepted.
