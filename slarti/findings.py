from __future__ import annotations

import json

from slarti import __version__
from slarti.domain import Finding, Severity, Summary
from slarti.domain import Report as ReportSchema
from slarti.report import catalogue as _report_catalogue

__all__ = ["Finding", "Report", "Severity"]


def _check_catalogue() -> dict[str, str]:
    return {c.id: c.description for c in _report_catalogue()}


class Report:
    """A run's findings plus the count of checks performed.

    The accumulator is hand-written; the shape it serialises to is not. `as_schema`
    builds the LinkML-generated `Report`, so the JSON a caller parses is exactly the
    shape `model/schema/slarti.yaml` declares.
    """

    def __init__(self, findings: list[Finding] | None = None, checked: int = 0) -> None:
        self.findings: list[Finding] = list(findings or [])
        self.checked = checked
        self.delegated_failures = 0

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def extend(self, findings: list[Finding]) -> None:
        self.findings.extend(findings)

    @property
    def errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.error)

    @property
    def warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.warning)

    def sorted_findings(self) -> list[Finding]:
        """Findings in reading order: by file, then line, then rule."""
        return sorted(self.findings, key=lambda f: (f.file, f.line or 0, f.id, f.subject))

    def as_schema(self) -> ReportSchema:
        """The run as the generated `Report`, validated on construction."""
        return ReportSchema(
            seam_version=__version__,
            findings=self.sorted_findings(),
            summary=Summary(errors=self.errors, warnings=self.warnings, checked=self.checked),
        )

    def as_json(self) -> str:
        return self.as_schema().model_dump_json(indent=2, exclude_none=True)

    def as_json_verbose(self) -> str:
        failed_ids = {f.id for f in self.findings}
        catalogue = _check_catalogue()
        passed = [
            {"id": cid, "description": catalogue[cid].splitlines()[0]}
            for cid in sorted(catalogue)
            if cid not in failed_ids
        ]
        payload = {
            "findings": [f.model_dump(exclude_none=True) for f in self.sorted_findings()],
            "passed": passed,
            "summary": {
                "errors": self.errors,
                "warnings": self.warnings,
                "passed": len(passed),
                "checked": self.checked,
            },
        }
        return json.dumps(payload, indent=2, sort_keys=False)

    def _delegated(self) -> str:
        """The delegated failures, whose diagnostics their tools reported, not counted here."""
        if not self.delegated_failures:
            return ""
        return (f" {self.delegated_failures} delegated validation(s) failed; their own "
                "output, above, is not counted in these totals.")

    def as_text(self) -> str:
        if not self.findings:
            return f"No findings ({self.checked} checks).{self._delegated()}"
        lines = []
        for f in self.sorted_findings():
            where = f.file if f.line is None else f"{f.file}:{f.line}"
            lines.append(f"{f.severity}: [{f.id}] {where}: {f.message}")
            lines.append(f"  remedy: {f.remedy}")
        lines.append(f"{self.errors} error(s), {self.warnings} warning(s), "
                     f"{self.checked} checks.{self._delegated()}")
        return "\n".join(lines)
