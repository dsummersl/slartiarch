# 3. The Python interfaces are a LinkML projection

Date: 2026-07-25

## Status

Accepted

## Context

ADR-0002 made the findings the interface and modelled the entities they are about
— `Finding`, `Report`, `Constraint`, `Enforcer` — as classes in
`model/schema/slarti.yaml`. The implementation nevertheless carried its own
hand-written dataclasses with the same names and roughly the same fields.

Two definitions of one entity is exactly the drift `slarti` exists to catch. The
schema could gain a slot the code never reads, or the code could gain a field the
shapes never see, and nothing would fail. The seam checks could not help: they
join LikeC4 to LinkML and the registry to the models, not the schema to the
Python that claims to implement it.

LinkML is a schema language whose point is projection: one definition, generated
into whatever shape a consumer needs — SHACL for pyshacl, JSON Schema for an
agent, Pydantic or TypeScript for an implementation. Hand-writing the Python was
declining the one thing LinkML is best at.

## Decision

`slarti/domain.py` is generated from `model/schema/slarti.yaml` by `gen-pydantic`
(`make domain`) and committed. It is the only definition of the domain entities;
`findings.py`, `registry.py`, `models.py`, `inject.py` and `env.py` import from it
rather than declaring their own.

Behaviour stays hand-written. The generated classes carry shape — fields, ranges,
cardinality, permissible values — and modules add the verbs around them
(`Report.as_schema`, `registry.is_unenforced`, `Likec4Model.owners_of`). The
serialised report is built as the generated `Report`, so `slarti check --json`
emits the shape the schema declares by construction.

Drift between the schema and the committed projection is a test failure
(`tests/test_domain.py`), the same gate `slartiarch check` applies to the
document.

## Consequences

- A slot added to the schema is a field in the implementation after `make domain`;
  a field the implementation wants must be argued for in the schema first.
- An enforcer kind that is not in the `EnforcerKind` enum is now rejected when the
  registry is read, with the permissible values named.
- The generated module is excluded from ruff, mypy and vulture: the schema is
  reviewed, its projection is not.
- `pydantic` becomes a runtime dependency.
- The same schema still generates SHACL, JSON Schema and TypeScript for other
  consumers — the projection to Python is one target among several, not a fork.
