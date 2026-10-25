# 4. slarti owns its vocabulary; diagrams arrive through adapters

Date: 2026-10-24

## Status

Accepted

Supersedes invariant I8 of `docs/specs/slarti-project.md` and replaces the non-goal
"Not pluggable" with "No plugin API".

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
parsing and supports exactly two backends. That kept `slarti` from growing a
plugin API, which is still right. But it also made LikeC4's model the model
`slarti` checks, which tied the structure layer to one methodology and one
runtime.

## Decision

### Own the semantic vocabulary

`slarti` defines its own LinkML vocabulary:

- **Structural layer — what a diagram says.** `Diagram`, `Node`, `Edge` and
  `SourceLocation` (file, line, source ID, label), with subclasses added per
  diagram type as each is supported (`Participant`/`Message`, `State`/`Transition`,
  …). It describes notation and nothing else. It knows no methodology.
- **Architectural layer — what the user means.** A base `Element` and `Relation`
  that projects extend in their own LinkML schema with whatever kinds they use.
  C4 becomes an optional profile schema that `slarti` ships and a project may
  import. Nothing in `slarti`'s checks assumes it.

The ownership seam (`OWN-*`) is re-expressed against `Element` rather than LikeC4
containers. By providing its own definition of diagrams, `slarti` becomes
diagram-tool agnostic.

### Adapters

`slarti` ships two built-in adapters:

- **LikeC4.** The existing LikeC4 integration becomes an adapter that produces
  instances of the vocabulary.
- **Mermaid.** A parser in Python for a subset of Mermaid diagram types — ER,
  sequence and C4 to begin — with more added one type at a time. Syntax outside
  a supported subset is a finding, not a silent skip.

The input `slarti` checks is the vocabulary instances, not LikeC4 or Mermaid.
Adapters are one way to produce them. Any tool that emits instances conforming to
the vocabulary — a script, a generator, an adapter for another notation — is an
equally valid input. That is the extension point: a published data contract, not
a plugin API. `slarti` loads no third-party code and keeps no registry of
adapters.

### Checks run on the vocabulary

Every check operates on vocabulary instances, never on diagram syntax:

- **Identity** across diagrams resolves on unique IDs plus declared aliases. A
  name that resolves to more than one element is a finding; `slarti` does not
  guess.
- Each structural `Node` and `Edge` must be either **attached** to an
  architectural element or **ignored with a reason**. There is no third state.
  This is the same rule the registry applies to constraints: `enforced_by: none`
  is allowed, but only with a reason.
- Dangling checks run in both directions (I14): a node or edge with no
  disposition is a finding, and so is an attachment or alias naming an element
  that does not exist.

In Mermaid, dispositions are written in native syntax where possible (`class`
assignments map nodes to element kinds), with `%% slarti:` directives for what the
syntax cannot express, so diagrams still render unchanged.

## Consequences

- Projects that use the Mermaid adapter, or produce the vocabulary themselves,
  need `uv` and nothing else. Node is needed only by projects that keep LikeC4.
- Teams keep the diagrams and methodology they have. C4 is a profile, not the
  model.
- `slarti` now owns a parser. That is a real departure from "everything else is
  delegated", justified only because no Python Mermaid parser exists and the
  Node runtime is the cost being removed. Mermaid's syntax moves, so supported
  Mermaid versions are enforced as I9 requires for the other tools, and
  `slarti`'s own CI renders its Mermaid fixtures with mermaid-cli.
- The vocabulary becomes a public contract. Changing it breaks every producer,
  built-in or not, so it is versioned with `slarti` and changed with the same
  care as the CLI.
- For Mermaid input, LikeC4's validation is no longer free. Dangling-relation
  detection must be rebuilt on the vocabulary.
- Authors gain a small new burden: every node needs a disposition. That burden is
  the point — an undeclared box is exactly the drift `slarti` exists to surface.

## Alternatives considered

- **Keep LikeC4 as the only structure source.** Rejected: the runtime and
  methodology costs above are the reason for this ADR.
- **Annotations only, no parser.** Rejected: without knowing which nodes a
  diagram contains, `slarti` cannot find the ones nobody annotated, which is the
  check that matters most.
- **A plugin API for notation adapters.** Rejected: loading third-party code is
  the build system `slarti` refuses to become. Publishing the vocabulary gives
  the same reach — anyone can add a notation — without `slarti` hosting their
  code.
