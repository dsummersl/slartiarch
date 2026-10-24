# 4. Mermaid is the structure source, mapped into slarti's own vocabulary

Date: 2026-10-24

## Status

Proposed

Supersedes invariant I8 of `docs/specs/slarti-project.md` and amends the non-goal
"Not pluggable".

## Context

LikeC4 owns the structure layer (§2.2 of the architecture). That choice has two
costs that only showed up once `slarti` was used outside its own repository.

**It adds a runtime.** LikeC4 is a Node package. A Python project that adopts
`slarti` now needs both Python and Node in CI, with pinned versions of each. Lua
projects need both and use neither. The tool that is meant to make architecture
cheap to keep honest makes it expensive to start.

**It picks a methodology.** LikeC4 is a C4 tool. Its elements are C4 elements and
its validation is C4 validation. A team that draws its architecture another way —
or that already has Mermaid diagrams in its docs — has to redraw the system in
LikeC4 before `slarti` can say anything about it.

Mermaid is already where most teams' diagrams live: it renders in GitHub, GitLab,
most doc sites and most editors, and it needs nothing installed to read. But
Mermaid diagrams carry little meaning on their own. A flowchart node is a label in
a box; nothing says whether it is a service, a database or a legend.

The spec's position until now (I8, "Not pluggable") was that `slarti` delegates all
parsing and supports exactly two backends. That position was right about adapters
— a registry of notation backends is the build system `slarti` refuses to become —
but it tied the structure layer to one methodology and one runtime.

## Decision

### Own the semantic vocabulary

`slarti` defines its own LinkML vocabulary:

- **Structural layer — what a diagram says.** `Diagram`, `Node`, `Edge` and
  `SourceLocation` (file, line, Mermaid ID, label), with subclasses added per
  diagram type as each is supported (`Participant`/`Message`, `State`/`Transition`,
  …). It describes notation and nothing else. It knows no methodology.
- **Architectural layer — what the user means.** A base `Element` and `Relation`
  that projects extend in their own LinkML schema with whatever kinds they use.
  C4 becomes an optional profile schema that `slarti` ships and a project may
  import. Nothing in `slarti`'s checks assumes it.


By providing its own definition for diagrams, `slarti` becomes diagram tool agnostic.

### Adapters

Add support for builtin adapters:

- change our existing likec4 implementation to an adapter that produces our semantic vocabulary
- add support for a subset of mermaid diagram types (ER, sequence, C4, to begin).

These adapters produce LinkML - likec4 and mermaid are not conceptually an input to the model that `slarti` operates on. The LinkML produced by these inputs are.

Support is per diagram type operates on the LinkML language produced (not the diagram tool syntax):

- **Identity** across diagrams resolves on unique IDs plus declared aliases. A
name that resolves to more than one element is a finding; `slarti` does not guess.
- Each structural `Node` and `Edge` must be either **attached** to an architectural
element or **ignored with a reason**. There is no third state. This is the same
rule the registry applies to constraints: `enforced_by: none` is allowed, but only
with a reason.

## Consequences

- Adopting `slarti` needs `uv` and nothing else. Node leaves users' CI.
- Teams keep the diagrams and methodology they have. C4 is a profile, not the
  model.
- `slarti` now owns a parser. That is a real departure from "everything else is
  delegated", justified only because no Python parser exists and the Node runtime
  is the cost being removed. Mermaid's syntax moves, so the version gate and the
  rendering check in `slarti`'s CI are load-bearing.
- LikeC4's validation and views are no longer free. Dangling-relation detection
  must be rebuilt.
- Authors gain a small new burden: every node needs a disposition. That burden is
  the point — an undeclared box is exactly the drift `slarti` exists to surface.

### Alternatives considered

- **Keep LikeC4 as the only structure source.** Rejected: the runtime and
  methodology costs above are the reason for this ADR.
- **Annotations only, no parser.** Rejected: without knowing which nodes a
  diagram contains, `slarti` cannot find the ones nobody annotated, which is the
  check that matters most.
- **One adapter per notation (Mermaid, PlantUML, Structurizr, …).** Rejected: it
  is the plugin system I8 exists to prevent. Other notations can reach `slarti`
  the way LikeC4 does, by generating Mermaid.
