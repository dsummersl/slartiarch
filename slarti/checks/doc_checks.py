from __future__ import annotations

from pathlib import Path

from slarti import docs, generate, inject
from slarti.config import Config
from slarti.findings import Finding, Severity
from slarti.models import Models
from slarti.registry import Constraint


def _doc3(file: str, message: str, subject: str, remedy: str) -> Finding:
    return Finding(
        id="DOC-3",
        severity=Severity.error,
        file=file,
        subject=subject,
        message=message,
        remedy=remedy,
    )


def _marker_findings(file: str, unknown: tuple[str, ...]) -> list[Finding]:
    return [
        _doc3(
            file,
            f"the document declares a generated region named '{name}', which slarti cannot fill.",
            name,
            "Use one of: constraints, unverified, ownership, diagram:<view>.",
        )
        for name in unknown
    ]


def _stale(file: str, region: str) -> Finding:
    return Finding(
        id="DOC-1",
        severity=Severity.error,
        file=file,
        subject=region,
        message=f"generated region '{region}' no longer matches the model it came from.",
        remedy="Run 'slartiarch check --fix' and commit the result.",
    )


def _doc4(file: str, constraint_id: str) -> Finding:
    return Finding(
        id="DOC-4",
        severity=Severity.error,
        file=file,
        subject=constraint_id,
        message=(
            f"constraint {constraint_id} is in the registry but has no row in the document tables."
        ),
        remedy="This is a generation bug in slarti; please report it with the registry entry.",
    )


def _bodies(text: str) -> dict[str, str]:
    return {r.name: r.body for r in inject.regions(text)}


def _region_findings(file: str, current: str, rendered: docs.Rendered) -> list[Finding]:
    if current == rendered.text:
        return []
    before, after = _bodies(current), _bodies(rendered.text)
    return [_stale(file, name) for name in sorted(after) if before.get(name) != after[name]]


def _table_findings(file: str, constraints: list[Constraint], text: str) -> list[Finding]:
    tables = "".join(r.body for r in inject.regions(text) if r.name in generate.TABLE_REGIONS)
    return [_doc4(file, c.id) for c in constraints if f"| {c.id} |" not in tables]


def _check_one_doc(
    config: Config, doc_path: Path, rendered: docs.Rendered,
) -> list[Finding]:
    file = config.rel(doc_path)
    current = doc_path.read_text(encoding="utf-8")
    findings: list[Finding] = []
    findings.extend(_marker_findings(file, rendered.unknown))
    findings.extend(_region_findings(file, current, rendered))
    return findings


def _check_existing(
    config: Config, models: Models, constraints: list[Constraint], doc_paths: list[Path],
) -> list[Finding]:
    fresh = generate.render_diagrams(config)
    try:
        rendered_docs = docs.render(config, constraints, models, fresh)
    except inject.MarkerError as exc:
        return [_doc3(config.rel(doc_paths[0]), str(exc), "-",
                      "Balance the slarti:begin and slarti:end markers.")]
    findings: list[Finding] = []
    for doc_path, rendered in zip(doc_paths, rendered_docs, strict=True):
        findings.extend(_check_one_doc(config, doc_path, rendered))
    all_tables = "".join(r.text for r in rendered_docs)
    findings.extend(_table_findings(config.rel(doc_paths[0]), constraints, all_tables))
    return findings


def _missing_doc_findings(config: Config, doc_paths: list[Path]) -> list[Finding]:
    findings = []
    for d in doc_paths:
        if not d.is_file():
            findings.append(
                _doc3(config.rel(d), "the architecture document does not exist.", "-",
                      "Run 'slarti init', or update slarti.toml.")
            )
    return findings


def check(config: Config, models: Models, constraints: list[Constraint]) -> list[Finding]:
    """DOC-1, DOC-3, DOC-4: the document seam — drift, markers, coverage."""
    doc_paths = config.document_paths()
    if not doc_paths:
        return []
    missing = _missing_doc_findings(config, doc_paths)
    if missing:
        return missing
    return _check_existing(config, models, constraints, doc_paths)
