from __future__ import annotations

from collections import Counter
from pathlib import Path

from slarti import fixtures, resolvers
from slarti.config import Config
from slarti.findings import Finding, Severity
from slarti.models import Models, shape_line
from slarti.registry import Constraint, is_unenforced, kind_text, referenced_shapes


def _reg1(config: Config, c: Constraint) -> Finding:
    return Finding(
        id="REG-1",
        severity=Severity.error,
        file=config.paths["constraints"],
        subject=c.id,
        line=c.line,
        message=(
            f"constraint {c.id} declares enforcer {kind_text(c.enforced_by)} "
            f"'{c.enforced_by.ref}', which does not resolve."
        ),
        remedy=(
            f"Create the enforcer '{c.enforced_by.ref}', correct the reference, "
            f"or record {c.id} as 'enforced_by: none' with a reason."
        ),
    )


def _reg3(config: Config, c: Constraint) -> Finding:
    return Finding(
        id="REG-3",
        severity=Severity.error,
        file=config.paths["constraints"],
        subject=c.id,
        line=c.line,
        message=f"constraint {c.id} is unenforced but gives no reason.",
        remedy=f"Add a 'reason' to {c.id} explaining why the rule cannot be enforced.",
    )


def _reg4(config: Config, constraint_id: str) -> Finding:
    return Finding(
        id="REG-4",
        severity=Severity.error,
        file=config.paths["constraints"],
        subject=constraint_id,
        message=f"constraint ID {constraint_id} is declared more than once.",
        remedy=f"Give each constraint a unique ID; rename one of the {constraint_id} entries.",
    )


def _reg5(config: Config, c: Constraint) -> Finding:
    return Finding(
        id="REG-5",
        severity=Severity.error,
        file=config.paths["constraints"],
        subject=c.id,
        line=c.line,
        message=f"constraint {c.id} cites decision {c.decision}, which no document records.",
        remedy=(
            f"Document decision {c.decision} in one of the configured architecture documents, "
            f"or drop the 'decision' field from {c.id}."
        ),
    )


def _reg8(config: Config, models: Models, c: Constraint) -> Finding:
    ref = c.enforced_by.ref or ""
    declared = resolvers.relation_location(config, models, ref)
    file, line = declared if declared else (config.paths["constraints"], c.line)
    return Finding(
        id="REG-8",
        severity=Severity.error,
        file=file,
        subject=c.id,
        line=line,
        message=f"constraint {c.id} forbids relation '{ref}', which now exists in the model.",
        remedy=f"Remove the forbidden relation '{ref}' from the model that declares it.",
    )


def _registry_findings(
    config: Config, models: Models, constraints: list[Constraint]
) -> list[Finding]:
    findings = [f for c in constraints for f in _one_constraint(config, models, c)]
    return findings + _duplicate_findings(config, constraints)


def _duplicate_findings(config: Config, constraints: list[Constraint]) -> list[Finding]:
    counts = Counter(c.id for c in constraints)
    return [_reg4(config, i) for i in sorted(i for i, n in counts.items() if n > 1)]


def _one_constraint(config: Config, models: Models, c: Constraint) -> list[Finding]:
    if is_unenforced(c.enforced_by):
        return [] if c.reason else [_reg3(config, c)]
    if resolvers.resolve(models, c.enforced_by):
        return []
    return _absent_violation(config, models, c) or [_reg1(config, c)]


def _absent_violation(config: Config, models: Models, c: Constraint) -> list[Finding] | None:
    absent = c.enforced_by.kind in resolvers.ABSENT_KINDS
    if absent and resolvers.absent_relation_violated(models, c.enforced_by.ref or ""):
        return [_reg8(config, models, c)]
    return None


def _decision_findings(config: Config, constraints: list[Constraint]) -> list[Finding]:
    all_text = "".join(
        p.read_text(encoding="utf-8") for p in config.document_paths() if p.is_file()
    )
    return [_reg5(config, c) for c in constraints if _decision_missing(c, all_text)]


def _decision_missing(c: Constraint, all_text: str) -> bool:
    return c.decision is not None and c.decision not in all_text


def _orphan_shapes(config: Config, models: Models, constraints: list[Constraint]) -> list[Finding]:
    referenced = referenced_shapes(constraints)
    return [
        _reg2(config, curie, path)
        for curie, path in sorted(models.shapes.items())
        if curie not in referenced
    ]


def _reg2(config: Config, curie: str, path: Path) -> Finding:
    return Finding(
        id="REG-2",
        severity=Severity.error,
        file=config.rel(path),
        subject=curie,
        line=shape_line(path, curie),
        message=(
            f"SHACL shape '{curie}' is enforced but no constraint in the registry references it."
        ),
        remedy=(
            f"Add a constraint to {config.paths['constraints']} with "
            f"enforced_by.kind=shacl_shape and ref='{curie}', or delete the shape."
        ),
    )


def _reg6(config: Config, c: Constraint, message: str, remedy: str, path: Path) -> Finding:
    return Finding(
        id="REG-6",
        severity=Severity.error,
        file=config.rel(path),
        subject=c.id,
        message=message,
        remedy=remedy,
    )


def _fixture_findings(config: Config, c: Constraint) -> list[Finding]:
    path = config.root / str(c.enforced_by.fixture)
    if not path.is_file():
        return [
            _reg6(
                config,
                c,
                f"constraint {c.id} declares a fixture that does not exist.",
                f"Create {c.enforced_by.fixture} as a case that must violate "
                f"'{c.enforced_by.ref}'.",
                path,
            )
        ]
    outcome = fixtures.validate(config, path, c.enforced_by.fixture_class)
    if outcome.error is not None:
        return [
            _reg6(
                config,
                c,
                f"fixture for {c.id} could not be validated: {outcome.error}",
                _load_remedy(outcome.error),
                path,
            )
        ]
    if outcome.conforms:
        return [
            _reg6(
                config,
                c,
                f"the negative fixture for {c.id} conforms; the shape never fires.",
                f"Change the fixture so it violates '{c.enforced_by.ref}', or fix the shape.",
                path,
            )
        ]
    return [] if _names_shape(outcome, c) else [_reg7(config, c, path)]


def _load_remedy(error: str) -> str:
    if "Unknown CURIE prefix" in error:
        return (
            "Give the fixture's identifier a CURIE, such as 'id: todo:t1' "
            "(a bare 'id: t1' cannot be converted)."
        )
    return "Make the fixture loadable: use Turtle, or declare 'fixture_class'."


def _names_shape(outcome: fixtures.Validation, c: Constraint) -> bool:
    ref = c.enforced_by.ref or ""
    return ref in outcome.shapes or ref in outcome.report


def _reg7(config: Config, c: Constraint, path: Path) -> Finding:
    return Finding(
        id="REG-7",
        severity=Severity.error,
        file=config.rel(path),
        subject=c.id,
        message=(
            f"the fixture for {c.id} fails, but the violation report never names "
            f"'{c.enforced_by.ref}'."
        ),
        remedy=(
            f"Narrow the fixture so the only violation reported is '{c.enforced_by.ref}', "
            "or correct the declared ref."
        ),
    )


FIXTURE_SUFFIXES = (".ttl", ".yaml", ".yml", ".json")


def _valid_fixtures(config: Config) -> list[Path]:
    directory = config.path("shacl_valid")
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.rglob("*") if p.is_file() and p.suffix in FIXTURE_SUFFIXES)


def _valid_class(constraints: list[Constraint]) -> str | None:
    """The fixture class for YAML valid fixtures, when the registry declares exactly one."""
    classes = {c.enforced_by.fixture_class for c in constraints if c.enforced_by.fixture_class}
    return classes.pop() if len(classes) == 1 else None


def _reg9(config: Config, path: Path, message: str, remedy: str) -> Finding:
    return Finding(
        id="REG-9",
        severity=Severity.error,
        file=config.rel(path),
        subject=config.rel(path),
        message=message,
        remedy=remedy,
    )


def _valid_findings(config: Config, path: Path, fixture_class: str | None) -> list[Finding]:
    outcome = fixtures.validate(config, path, fixture_class)
    if outcome.error is not None:
        return [
            _reg9(
                config,
                path,
                f"valid fixture {config.rel(path)} could not be validated: {outcome.error}",
                _load_remedy(outcome.error),
            )
        ]
    if outcome.conforms:
        return []
    accused = ", ".join(f"'{s}'" for s in sorted(outcome.shapes)) or "a shape"
    return [
        _reg9(
            config,
            path,
            f"valid fixture {config.rel(path)} violates {accused}.",
            "Correct the fixture so it conforms, or relax the shape it violates.",
        )
    ]


def _valid_fixture_findings(config: Config, constraints: list[Constraint]) -> list[Finding]:
    fixture_class = _valid_class(constraints)
    return [f for p in _valid_fixtures(config) for f in _valid_findings(config, p, fixture_class)]


def check(config: Config, models: Models, constraints: list[Constraint]) -> list[Finding]:
    """REG-1..REG-9: the registry seam, checked in both directions (I14)."""
    findings = [
        *_registry_findings(config, models, constraints),
        *_decision_findings(config, constraints),
        *_orphan_shapes(config, models, constraints),
    ]
    for c in constraints:
        if c.enforced_by.fixture:
            findings.extend(_fixture_findings(config, c))
    return findings + _valid_fixture_findings(config, constraints)
