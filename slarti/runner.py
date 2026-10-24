from __future__ import annotations

from dataclasses import dataclass

from slarti import registry
from slarti.checks import delegated, doc_checks, ownership, registry_checks, structure
from slarti.config import Config
from slarti.findings import Report
from slarti.models import Models
from slarti.registry import Constraint


@dataclass
class Context:
    """Everything a command needs: config, models and the registry."""

    config: Config
    models: Models
    constraints: list[Constraint]


def context(config: Config) -> Context:
    return Context(
        config=config,
        models=Models(config=config),
        constraints=registry.load(config.path("constraints")),
    )


def check(ctx: Context, include_docs: bool = True) -> tuple[Report, bool]:
    """Delegated validations first, then the instance inputs, then every slarti check.

    Malformed instance input stops the run before any seam check reads it."""
    report = Report()
    delegations = delegated.run_all(ctx.config)
    delegated_ok = delegated.report(delegations)
    malformed = ctx.models.instances.findings
    if malformed:
        report.extend(malformed)
        report.checked = len(delegations) + ctx.models.instances.files
        return report, delegated_ok
    report.extend(ownership.check(ctx.models))
    report.extend(structure.check(ctx.models))
    report.extend(registry_checks.check(ctx.config, ctx.models, ctx.constraints))
    if include_docs:
        report.extend(doc_checks.check(ctx.config, ctx.models, ctx.constraints))
    report.checked = _checked(ctx, len(delegations), include_docs)
    return report, delegated_ok


def _checked(ctx: Context, delegations: int, include_docs: bool) -> int:
    classes = len(ownership.owned_classes(ctx.models))
    elements = len(ctx.models.vocabulary.elements)
    docs_count = 4 if include_docs else 0
    seams = len(ctx.constraints) + len(ctx.models.shapes)
    inputs = ctx.models.instances.files
    drawn = len(ctx.models.vocabulary.nodes) + len(ctx.models.vocabulary.edges)
    return delegations + inputs + classes + elements + drawn + seams + docs_count
