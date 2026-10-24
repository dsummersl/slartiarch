# 5. One command checks the document; `--fix` regenerates it

Date: 2026-10-24

## Status

Accepted

## Context

`slarti docs` regenerated the document's generated regions, and `slarti docs
--check` was the drift gate. Both predate ADR-0004.

- `slarti check` already ran the document checks (`DOC-*`). `docs --check` ran the
  same checks again, with less output and no `--json`. CI ran them twice.
- `slarti docs` also wrote `likec4 codegen mermaid` output to `docs/diagrams/*.mmd`.
  Nothing read those files except `DOC-2`, which compared them with a fresh render.
  The same diagrams are already inlined in the `diagram:<view>` regions, where
  `DOC-1` catches a hand edit. The files are a LikeC4-only copy of what the
  document already holds.

## Decision

- `slarti check` is the only command that reports findings, document findings
  included.
- `slarti check --fix` regenerates every generated region, then checks. It is the
  fix for `DOC-1`; `DOC-3` and `DOC-4` cannot be fixed mechanically and are only
  reported.
- `slarti docs`, `slarti docs --check`, `docs/diagrams/`, the `diagrams` config
  path and `DOC-2` are removed. LikeC4 views render into a temp tree and go
  straight into their regions.

## Consequences

- One command, one report, one `--json`. Remedies say `slartiarch check --fix`.
- Configs that set `paths.diagrams` fail with an unknown-key error until the line
  is removed.
- `DOC-2` is retired, not renumbered: `DOC-3` and `DOC-4` keep their IDs.
- A rewritten document moves line numbers, so `check --fix` reloads the models
  before checking.
