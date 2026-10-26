# slarti — a coordination CLI for validated architecture documentation

**Status:** specification, pre-implementation
**Working name:** `slarti` — the tool's entire value is the joins between tools that. Slartibartfast, who designed Norway's fjords and won an award for the coastlines. An architect who is fussy about the details of his crinkly bits. Literally an award-winning designer of structures. I used this b/c it plays on the number 42 for arc42 (which itself uses hhgttt for the same reason).
cannot see each other. Rename freely.
**Language:** Python 3.11+, distributed as a `uv`-installable CLI.

---

## 1. Problem

Architecture documents drift, and the drift is invisible: a stale diagram looks
exactly like a fresh one, and an unenforced rule in prose reads exactly like an
enforced one.

Two tools already solve large parts of this well. **LikeC4** validates structure and
generates diagrams. **LinkML** validates entities and generates schemas, shapes and
diagrams. Neither can see the other, and neither can see the prose document that
claims what they enforce.

`slarti` coordinates them. It does not wrap them, hide them, or replace any part of
them. It owns exactly the joins nobody else can hold:

| Join | What goes wrong without it |
|------|----------------------------|
| Architecture ↔ diagrams | A box or arrow in a diagram depicts nothing in the architecture, or something that no longer exists. |
| Architecture ↔ LinkML | An entity exists that no container owns, or a container claims an entity that isn't in the schema. |
| Document ↔ rules | The constraints table says a rule is enforced by a shape that was deleted; or a shape exists that no rule references. |
| Document ↔ models | A diagram in the document no longer matches the model it came from. |

Everything else — parsing, validating, rendering, generating — is delegated. The one
exception is the built-in Mermaid adapter's parser (ADR-0004).

## 2. Non-goals

- **Not a build system.** No Makefile in the user's project, no task DSL, no plugin API.
- **Not a renderer.** Diagrams are hand-written Mermaid, or come from
  `likec4 codegen` / `likec4 export` and `linkml gen-erdiagram`. `slarti` reads or
  places them; it does not draw them.
- **Not a documentation site generator.** `likec4 build` already deploys to GitHub Pages.
- **No plugin API.** `slarti` loads no third-party code. It is extensible through
  data instead: any tool that produces instances of `slarti`'s vocabulary is a
  valid input. See I8 and ADR-0004.
- **Not an arc42 enforcer.** Sections omitted for lack of content are a feature; the
  tool must not require a complete template.
- **Not a formal methods tool.** Alloy/Z3/TLA+ exploration stays a human activity
  outside the build.

## 3. Personas

### 3.1 The architect

Owns the prose: goals, constraints, solution strategy, decisions. Thinks in terms
of rules and responsibilities, not YAML.

- **Needs:** confidence that every rule stated in the document is either enforced or
  visibly listed as unenforced; a decision record that survives the next refactor.
- **Fears:** a framework that makes them learn a new abstraction to say something
  they could have said in a sentence.
- **Success:** they write a constraint in the registry, run one command, and the
  document's constraints table regenerates with the rule and its enforcer. If the
  enforcer doesn't exist, the command says so by name.

### 3.2 The developer

Lives at the CLI. Already has a test runner, a linter, and opinions.

- **Needs:** a fast local check with the same output as CI; freedom to run `likec4
  start` or `linkml lint` directly without breaking anything; no second build system.
- **Fears:** a tool that owns config, caches model state, or produces different
  results than the underlying tools produce on their own.
- **Success:** `slarti check` finishes in seconds, its errors name a file and a line,
  and nothing it does is a mystery — every step is a subprocess they could have run.

### 3.3 The LLM agent

Edits model sources during a brainstorming or refinement session. Has no memory of
this repository between sessions.

- **Needs:** an unambiguous statement of which files it may edit; stable rule IDs to
  reason about; machine-readable findings with a remedy; idempotent commands that are
  safe to re-run.
- **Fails at:** noticing that a newly added shape wasn't registered, that a new class
  has no owner annotation, or that a generated region was edited by hand.
- **Success:** it edits model sources, runs `slarti check --json`, receives a finding
  with a rule ID and a specific remedy, fixes it, and converges — without ever
  touching a generated file.

The agent is a first-class consumer, not an afterthought. Where human ergonomics and
agent legibility conflict, prefer stable IDs and structured output.

## 4. Invariants

The tool's own constitution. Each is testable; each has a test in `slarti`'s suite.

| # | Invariant | Verified by |
|---|-----------|-------------|
| I1 | `slarti` writes only to generated regions (between markers), its own generated directories, and files it scaffolds once during `init`. It never modifies a user-authored file. | Snapshot test: hash every user-authored file before and after every command. |
| I2 | `slarti` never reimplements a validation that LikeC4 or LinkML performs. It invokes them as subprocesses and passes their diagnostics and exit codes through unaltered. | Code review + test asserting stderr passthrough is byte-identical. |
| I3 | Running an underlying tool directly produces the same result as running it via `slarti`. | Test: `likec4 validate` and `slarti check` produce identical LikeC4 diagnostics. |
| I4 | `slarti` holds no cache and no state file. Everything is derived on each invocation from the same sources the underlying tools read. | Test: no writes outside declared output paths; no `.slarti/` state dir exists. |
| I5 | Styling, view definitions and element kinds belong entirely to the user, in `specification` blocks and `likec4.config.ts`. `slarti` injects no styles and has no theme. | Test: generated output contains no `classDef`, no color, no style directive authored by `slarti`. |
| I6 | Config is passed through, never mirrored. `slarti` reads the user's `likec4.config.ts` and `pyproject.toml` locations; it does not restate their settings. | Review: `slarti.toml` contains paths and the opt-ins of `slarti`'s own checks (`[checks]`), nothing another tool owns. |
| I7 | Generation is idempotent. Running `slarti check --fix` twice produces byte-identical output. | Test: hash comparison across two runs. |
| I8 | `slarti` checks instances of its own LinkML vocabulary. Built-in adapters (LikeC4, Mermaid) produce them; any other producer is equally valid. No plugin API and no registry of adapters. *Supersedes the original "exactly two backends: LikeC4 and LinkML"; see ADR-0004 (accepted).* | Review: no plugin interface, no third-party code loaded. |
| I9 | Supported version ranges are enforced at runtime. Outside the range, `slarti` refuses to run rather than producing possibly-wrong output. | Test: mocked version probes at range boundaries. |
| I10 | The default path requires no JVM, no Docker, no browser and no Node. Node is needed only by a project that keeps a LikeC4 model; anything needing Playwright is opt-in and off by default. | Test: default `slarti check` and `slarti check --fix` in a container with none of these. `slarti`'s own CI checks itself with no Node installed. |
| I11 | Every finding carries a stable rule ID, a file path, and a remedy sentence. | Test: schema-validate the `--json` output; assert every finding is complete. |
| I12 | Findings are phrased in domain terms, not tool terms. "class `User` has no owner" — not "KeyError: 'owner'". | Review + golden-file tests over all finding types. |
| I13 | `slarti`'s own repository dogfoods `slarti`. Its architecture document is generated by itself. | CI runs `slarti check` on `slarti`. |
| I14 | Every slarti is checked in both directions. A dangling pointer and an unreferenced target are both findings. | Test: one fixture per direction per slarti. |

## 5. Supported tool versions

`slarti` targets a floor with a hard ceiling at the next major. Compatibility is
verified at runtime, not assumed.

| Tool | Range | Probe |
|------|-------|-------|
| LinkML | `>=1.11,<2` | `linkml --version` |
| Python | `>=3.11,<4` | interpreter |
| Mermaid | `>=11,<13`, when the project pins one | `node_modules/mermaid/package.json` |
| LikeC4 | `>=1.59,<2`, only with a LikeC4 model | `likec4 --version` |
| Node | `>=20` (LikeC4's floor), only with a LikeC4 model | `node --version` |

LikeC4 and Node are probed only when the `likec4` directory holds a `*.c4` source;
otherwise `slarti doctor` reports them as not required. `slarti` runs no Mermaid of
its own: it gates a project's pinned Mermaid, and its own CI renders every Mermaid
fixture with a pinned mermaid-cli.

Policy:

- On every invocation that shells out, probe once and cache **in-process only** (I4).
- Below floor or at/above ceiling → exit 2 with the detected version, the required
  range, and the upgrade command. Never a warning; never proceed.
- A new minor of either tool is adopted by raising the floor in a `slarti` release,
  with the changelog naming what changed. The ceiling moves only on a `slarti` major.
- `slarti doctor` reports every probe, its result, and where the binary was found.

Rationale: these tools move fast, and their JSON exports and codegen output are the
substrate every slarti check reads. A silent format change would produce wrong
findings, which is worse than no findings.

## 6. What `slarti` owns

Five things, and no more:

1. **The ownership slarti.** LinkML class annotations ↔ the `owns` of vocabulary
   elements, checked in both directions.
2. **The diagram seam.** Every node and edge of every diagram is attached to an
   element or relation, or ignored with a reason (ADR-0004).
3. **The constraint registry** and its joins: every rule points at a real enforcer,
   every enforcer is referenced by a rule.
4. **Document injection and the drift gate.**
5. **Conventions:** project layout, `init` scaffolding, and the agent skill file.

Everything else is delegated:

| Concern | Delegated to |
|---------|--------------|
| Structural validation | the vocabulary's own schema, via `linkml validate`; `likec4 validate` for a LikeC4 model |
| Diagram generation | the author, in Mermaid (default); `likec4 codegen mermaid` for a LikeC4 model, `likec4 export png` (opt-in) |
| Diagram rendering | whatever renders Mermaid: GitHub, a doc site, an editor |
| Interactive site | `likec4 build` — invoked by the user, not by `slarti` |
| Layer-1 model assertions | the user's own test suite, in LikeC4's documented idiom |
| Instance input | any producer of vocabulary instances; `slarti` loads no third-party code |
| Schema validation | `linkml lint`, `linkml validate` |
| SHACL generation | `gen-shacl` |
| ER diagram | `gen-erdiagram` |
| Instance validation | `pyshacl` |
| Implementation projections | `gen-pydantic`, `gen-typescript`, `gen-sqlddl`, `gen-json-schema` |

## 7. Project layout

Created by `slarti init`, and assumed thereafter. Paths are configurable in
`slarti.toml` but the defaults are the convention:

```
slarti.toml                     paths and slarti's own check opt-ins; nothing mirrored
AGENTS.md                     the agent contract (scaffolded, then user-owned)

docs/
  architecture.md             user-authored prose, Mermaid diagrams + generated regions
  slarti/
    instances/*.yaml          user-authored — vocabulary instances: elements, relations
    likec4/*.c4               optional, user-authored — LikeC4 (init --likec4)
    linkml/*.yaml             user-authored — LinkML
    shacl/*.ttl               user-authored — hand-written SHACL
    constraints.yaml          user-authored — the rule registry
    data/valid/*              fixtures that must pass
    data/invalid/*            one file per rule; each must fail, naming its rule

build/                        transient; gitignored
```

Note `data/invalid/` is **one fixture per rule**. A single combined negative fixture
only proves that at least one shape works; per-rule fixtures make each rule
individually load-bearing. `slarti check` asserts each fixture fails *and* that the
violation report names that fixture's declared rule.

## 8. The constraint registry

`model/constraints.yaml` is the join table between prose and enforcement. It is
user- and agent-authored; `slarti` reads it and generates document tables from it.

```yaml
constraints:
  - id: D8
    statement: A subtask belongs to the same list as its parent.
    enforced_by:
      layer: 3
      kind: shacl_shape
      ref: "todo:SubtaskSharesListWithParent"
      fixture: model/data/invalid/D8.yaml
    decision: ADR-004

  - id: D2
    statement: A task belongs to exactly one list.
    enforced_by:
      layer: 2
      kind: linkml_slot
      ref: "Task.list"

  - id: D1
    statement: The web UI never talks to the database directly.
    enforced_by:
      layer: 1
      kind: likec4_absent_relation
      ref: "todo.web -> todo.db"

  - id: U1
    statement: The API checks membership before every list access.
    enforced_by: none
    reason: >-
      Layer 1 can assert the relationship exists, not that every code path
      uses it. Requires an implementation that does not exist.
```

Recognised `kind` values map to a resolver that answers *does this enforcer actually
exist?*: `shacl_shape`, `linkml_slot`, `linkml_class`, `likec4_relation`,
`likec4_absent_relation`, `likec4_element`, `ownership`, `external` (with a required
`reason`).

`enforced_by: none` requires a `reason` and is not a failure — it is the honest case,
and it populates the unverified-invariants table.

## 9. Checks

Every check has a stable ID. IDs are permanent; retired checks are never reused.

**Ownership slarti (`OWN-*`)**

| ID | Finding |
|----|---------|
| OWN-1 | Class has no `owner` annotation |
| OWN-2 | Class names an owner that is not an `Element` in the vocabulary instances |
| OWN-3 | Class names an owner that does not list it under `owns` |
| OWN-4 | `Element` lists a class under `owns` that is not in the schema |
| OWN-5 | Class is claimed by more than one `Element` |

The ownership checks read only vocabulary instances. LikeC4's export reaches them
translated into `Element`s, as any other producer's instances do.

**Diagram slarti (`ATTACH-*`, `IDENT-*`, `DANGLE-*`, `DRAWN-*`)**

| ID | Finding |
|----|---------|
| ATTACH-1 | `Node` or `Edge` is neither attached nor ignored |
| ATTACH-2 | `Node` or `Edge` is both attached and ignored |
| ATTACH-3 | `Node` or `Edge` is ignored without a reason |
| IDENT-1 | An id or alias resolves to more than one `Element` |
| IDENT-2 | A `Node` attaches through a name that resolves to more than one `Element` |
| DANGLE-1 | A `Node` attaches to a name that is no `Element`'s id or alias |
| DANGLE-2 | An `Edge` depicts a `Relation` not declared between its endpoints' elements |
| DANGLE-3 | An attached `Edge` ends at a `Node` that is ignored or unattached |
| DANGLE-4 | An `Edge` ends at a node id no `Diagram` declares |
| DRAWN-1 | An `Element` whose kind is annotated `drawn: true` appears in no `Diagram` |

These read vocabulary instances only, never diagram syntax. Identity resolves on
ids plus declared aliases; `slarti` never guesses between candidates.

**Registry slarti (`REG-*`)**

| ID | Finding |
|----|---------|
| REG-1 | Constraint points at an enforcer that does not exist |
| REG-2 | SHACL shape exists that no constraint references |
| REG-3 | `enforced_by: none` without a `reason` |
| REG-4 | Duplicate constraint ID |
| REG-5 | Constraint references a decision ID absent from the document |
| REG-6 | Constraint declares a fixture that does not exist, or that pyshacl accepts |
| REG-7 | Fixture fails, but the violation report does not name the declared shape |

**Document slarti (`DOC-*`)**

| ID | Finding |
|----|---------|
| DOC-1 | Generated region is stale relative to its source |
| DOC-2 | *Retired: committed diagram files were removed (ADR-0005); a hand-edited region is DOC-1* |
| DOC-3 | Marker opened without a matching close, or unknown region name |
| DOC-4 | Constraint in the registry has no row in the generated table (generation bug) |

**Environment (`ENV-*`)**: version out of range, tool not found, Node too old.

## 10. Commands

| Command | Behaviour |
|---------|-----------|
| `slarti init` | Scaffold layout, `slarti.toml`, `AGENTS.md`, a minimal `.c4` and LinkML schema, an empty registry, and a CI workflow. Refuses to overwrite. |
| `slarti doctor` | Probe every tool, report version and path, verify ranges. |
| `slarti check` | Delegated validations (LikeC4, LinkML, pyshacl per-fixture) then all slarti checks. This is the CI command. |
| `slarti check --json` | Same, as structured findings on stdout. Human output suppressed. |
| `slarti check --fix` | Regenerate diagrams and registry tables into the generated regions of the documents, then check. The only command that writes. |
| `slarti report` | Every seam in report form: enforced rules, unenforced rules, orphaned shapes, and the check catalogue. The headline command. |
| `slarti report --json` | The same report, fully detailed: resolved enforcers, shape references, ownership, elements, and every check with its remedy. Primarily for agents. |

**Exit codes:** `0` clean · `1` findings · `2` environment or usage error.

Findings JSON:

```json
{
  "seam_version": "0.3.0",
  "findings": [
    {
      "id": "REG-2",
      "severity": "error",
      "file": "model/shapes/invariants.ttl",
      "line": 47,
      "subject": "todo:UniqueMembership",
      "message": "SHACL shape 'todo:UniqueMembership' is enforced but no constraint in the registry references it.",
      "remedy": "Add a constraint to model/constraints.yaml with enforced_by.kind=shacl_shape and ref='todo:UniqueMembership', or delete the shape."
    }
  ],
  "summary": {"errors": 1, "warnings": 0, "checked": 34}
}
```

## 11. Implementation

- **Python 3.11+**, `uv`-managed, published to PyPI, installable as
  `uv tool install slarti`.
- **CLI:** `typer` — small, typed, good help output. `argparse` acceptable if
  dependency count becomes a concern.
- **Dependencies (target: under six):** `typer`, `linkml-runtime` (SchemaView, for
  reading the schema as objects rather than parsing YAML), `rdflib` (shape IRIs),
  `tomli-w`, `pyyaml`. `pyshacl` and `linkml` are invoked as subprocesses, not
  imported — they are the user's pinned versions, not `slarti`'s.
- **Node tools** are invoked via `npx --no-install`, and only for a LikeC4 model, so
  the user's pinned LikeC4 is used and `slarti` never installs anything.
- **Model access:** vocabulary instances, from instance files and the built-in
  adapters (LikeC4 via `likec4 export json`, Mermaid parsed in Python); LinkML via
  `SchemaView`.
  Investigate LikeC4's `likec4.config.ts` custom-generator hook as an alternative —
  if it gives a stable, documented model dump, prefer it.
- **Injection:** replace the whole region between markers with a single regex
  substitution — no append path, idempotent by construction.

**Determinism is a hard requirement** (I7). Every generator must sort
deterministically before emitting: classes, slots, relationships, table rows. If an
upstream generator emits non-deterministic ordering, normalise it before injection
rather than accepting churn in the drift gate.

## 12. Testing

- **Unit** per check, one fixture per direction (I14).
- **Golden files** for every generated region and every finding message.
- **Idempotence:** run every generator twice, compare hashes.
- **Isolation (I1):** hash all user-authored files before and after every command.
- **Version gate (I9):** mocked probes at floor, ceiling, and outside.
- **Container test (I10):** default commands succeed with no JVM, Docker or browser.
- **Dogfood (I13):** `slarti`'s own repo carries `docs/slarti/`, `docs/architecture.md`
  and a registry, and CI runs `slarti check` against itself with no Node installed.
  Its architecture is vocabulary instances drawn in Mermaid, not a LikeC4 model.
- **Example project** used as an end-to-end fixture, exercising a refinement that
  changes both layers and a rule that becomes reachable only after it.

## 13. Spikes, before any implementation

Each of these can change the design. Timebox: one day total.

| # | Question | If the answer is no |
|---|----------|---------------------|
| S1 | Does `likec4 codegen mermaid` render a **dynamic view** as a Mermaid sequence diagram? | `slarti` owns one narrow renderer for dynamic views only, or the runtime view links to the LikeC4 site. |
| S2 | Is SVG export available in current LikeC4? (PNG-only as of mid-2025.) | Mermaid inline stays the default; PNG remains opt-in. |
| S3 | Is the `likec4.config.ts` custom-generator API documented and stable enough to depend on? | Use `likec4 export json` and pin the range tightly. |
| S4 | Is `gen-shacl` output deterministically ordered across runs? | Normalise before injection. |
| S5 | Can shape IRIs be located to a **line number** in the user's Turtle for findings? | Findings carry file and subject only, no line. |

## 14. Milestones

| # | Deliverable |
|---|-------------|
| M0 | Spikes S1–S5 resolved and recorded. |
| M1 | `doctor`, `check` with delegated validations and the ownership slarti. Exit codes and `--json`. |
| M2 | Registry, resolvers for every `kind`, `REG-*` checks, per-rule negative fixtures, `report`. |
| M3 | `docs` and `docs --check`: diagram placement, generated constraint tables, drift gate. |
| M4 | `init` scaffolding, `AGENTS.md`, CI workflow template, the check catalogue in `report`. |
| M5 | Dogfood (I13), example project, docs, PyPI release. |

## 15. Risks

| Risk | Response |
|------|----------|
| Upstream churn breaks a slarti check | Hard version ceiling (I9); fail loudly rather than silently mis-report. |
| Scope creep toward becoming a build system | Non-goals are normative; every new command must be justified against the four owned concerns in §6. |
| Small audience | Primary user is the author and the author's clients. Built as internal tooling that happens to be public; adoption is not the success criterion. |
| The registry becomes busywork | It must generate the document tables, so maintaining it *replaces* work rather than adding it. If that ever stops being true, the design has failed. |
| Agents edit generated regions anyway | `AGENTS.md` states the contract; `DOC-1` catches violations; `check` blocks the merge. |
