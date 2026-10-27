# 6. Decisions are cited files, and a changed decision is re-reviewed

Date: 2026-10-27

## Status

Proposed

## Context

A constraint's `decision` field names the record that introduced the rule, as an
ID such as `ADR-0002`. `REG-5` checks only that this string appears somewhere in
the configured architecture documents. `slarti` does not know where a project
keeps its decision records, so it cannot tell when:

- **a record is cited by nothing.** A project adopting `slarti` usually arrives
  with records already written. Nothing points out the ones whose rules never made
  it into the registry, so the prose and the registry drift from the first day.
- **a cited record is gone.** Adopting `slarti` on a to-do app, renaming
  `docs/adr/0002-tasks-and-subtasks.md` raised nothing, because
  `docs/architecture.md` happened to say "see ADR-0002".
- **a cited record changed.** If a record's prose is edited, say "subtasks are one
  level deep" becomes "two levels", the constraint, its shape and its fixtures stay
  as they were, and `check` still passes.

Decision records come in many forms: Markdown in `docs/adr/`, reStructuredText,
plain text, and directory layouts of every kind. `slarti` cannot assume a naming
convention, a status line or a section structure without breaking for some of
them. It needs to work from file paths and file contents alone.

## Decision

- **Decision records are files matched by configured patterns.** A new path,
  `decisions`, takes a list of glob patterns relative to the project root:

  ```toml
  [paths]
  decisions = ["docs/adr/*"]   # the default
  ```

  Any file the patterns match is a decision record, whatever its format. When a
  pattern is set explicitly and matches no file, that is a finding (`REG-12`).
  When the default pattern matches nothing, decision checks are simply off.

- **A constraint cites a decision by path.** The path is the only identity
  `slarti` can rely on without parsing the file:

  ```yaml
  decision:
    path: docs/adr/0002-tasks-and-subtasks.md
    sha: 3f9c1a2b7e04
  ```

  A plain string (`decision: ADR-0002`) keeps its current meaning and its current
  `REG-5` check, so existing registries do not break.

- **`REG-5` checks a cited path.** A path-form decision must name an existing
  file matched by `decisions`.

- **`REG-10`: a decision record no constraint cites (warning).** Many records
  hold no checkable rule, for example "we record decisions as ADRs", or a record
  that has been superseded. They are accounted for the same way other uncheckable
  rules are: a constraint with `enforced_by: none` and a `reason` that cites the
  record. Or they are ignored, with a reason, in the config:

  ```toml
  [checks.decisions_ignored]
  "docs/adr/0001-record-architecture-decisions.md" = "process, not architecture"
  ```

  `slarti` does not read a record's status, since that would assume a format.

- **`REG-11`: a cited record changed since the constraint was reviewed.** `sha`
  is the first 12 hex digits of the SHA-256 of the whole file, after normalising
  line endings to `\n` and stripping trailing whitespace from each line. When the
  file's current hash differs from the stored one, the constraint is reported.
  Hashing the whole file means even a typo fix asks for a review. That is the
  cost of not parsing any format, and a review is cheap.

- **Only `slartiarch review` records a hash.** `slartiarch review <constraint-id>`
  or `slartiarch review <path>` writes the current hash into the matching
  constraints. It is the only command that does. `check --fix` never touches
  `sha`, because `--fix` is run by reflex, and a hash refreshed by reflex would
  make `REG-11` mean nothing. A path-form decision with no `sha` yet is reported
  as `REG-11`, with `review` as its remedy.

## Consequences

- A project's decision records and its registry are checked in both directions,
  like shapes and constraints already are (`REG-1`, `REG-2`).
- A prose change to a cited record shows up in review: the PR that edits the
  record also carries the `sha` change for every constraint someone re-reviewed.
  `slarti` cannot prove a person read the rule. It can make sure the moment to
  reread it is visible.
- Whole-file hashes give false positives on cosmetic edits. Hashing only part of
  a record would need format-specific parsing. If false positives become a
  problem, the remedy is a smaller normalisation, not a parser.
- The `decisions` patterns may also match `docs/architecture.md` or other prose,
  and its rules then get the same coverage and staleness checks. This is not the
  default.
- New finding IDs: `REG-10`, `REG-11`, `REG-12`. A new command: `review`. A new
  config path: `decisions`. A new check opt-in table: `[checks.decisions_ignored]`.
  The `Constraint.decision` slot in `docs/slarti/linkml/slarti.yaml` becomes a
  string or a `Decision` (`path`, `sha`).
- `slarti`'s own registry cites `ADR-000N` strings today. It moves to path-form
  decisions when this is implemented.
