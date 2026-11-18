from __future__ import annotations

from slarti import resolvers
from slarti.domain import ModelRelation
from slarti.findings import Finding, Severity
from slarti.models import NO_CONTRACT, Models

LIKEC4_SUFFIX = ".c4"


def _named(relation: ModelRelation) -> str:
    return f"relation '{relation.title}' from '{relation.source}' to '{relation.target}'"


def _declare(file: str) -> str:
    """How the relation's own notation writes a contract."""
    if file.endswith(LIKEC4_SUFFIX):
        return ("Add \"metadata { contract '<path or schema class>' }\" to the relation, or "
                "\"contract 'none'\" with a 'contract_reason'")
    return ("Give the relation 'contract: <path or schema class>', or 'contract: none' with "
            "a 'contract_reason'")


def _missing(relation: ModelRelation, file: str) -> tuple[str, str, str] | None:
    """SEAM-1: the relation names a contract, or says with a reason why it has none."""
    contract = (relation.contract or "").strip()
    if not contract:
        return ("SEAM-1", f"{_named(relation)} declares no contract.", f"{_declare(file)}.")
    return _unexplained(relation) if contract == NO_CONTRACT else None


def _unexplained(relation: ModelRelation) -> tuple[str, str, str] | None:
    if (relation.contract_reason or "").strip():
        return None
    return ("SEAM-1", f"{_named(relation)} has contract 'none' but gives no reason.",
            "Say in 'contract_reason' why the relation has no written contract, or "
            "name the contract.")


def _unresolved(models: Models, relation: ModelRelation) -> tuple[str, str, str] | None:
    """SEAM-2: a named contract is a path inside the project or a project schema class."""
    contract = (relation.contract or "").strip()
    if not contract or contract == NO_CONTRACT or models.contract(contract) is not None:
        return None
    return (
        "SEAM-2",
        f"{_named(relation)} names contract '{contract}', which is neither a path in the "
        "project nor a class of the project schema.",
        f"Point 'contract' at an existing file or directory relative to the project root, "
        f"or at a project schema class, or declare '{contract}'.",
    )


def _finding(models: Models, index: int, relation: ModelRelation) -> Finding | None:
    file = models.vocabulary.relation_file(index)
    found = _missing(relation, file) or _unresolved(models, relation)
    if found is None:
        return None
    rule, message, remedy = found
    subject = f"{relation.source} -> {relation.target}"
    location = resolvers.relation_location(models.config, models, subject)
    return Finding(
        id=rule,
        severity=Severity.error,
        file=file,
        line=location[1] if location and location[0] == file else None,
        subject=subject,
        message=message,
        remedy=remedy,
    )


def check(models: Models) -> list[Finding]:
    """SEAM-1 and SEAM-2: every relation says where its contract is written, and it exists."""
    relations = enumerate(models.vocabulary.relations)
    found = [_finding(models, index, relation) for index, relation in relations]
    return [f for f in found if f is not None]
