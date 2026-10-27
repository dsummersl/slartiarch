from __future__ import annotations

import json

from slarti.findings import Finding, Report

REQUIRED = ("id", "severity", "file", "subject", "message", "remedy")


def finding(identifier: str = "REG-2") -> Finding:
    return Finding(
        id=identifier,
        severity="error",
        file="model/shapes/invariants.ttl",
        subject="todo:UniqueMembership",
        message="SHACL shape is enforced but no constraint references it.",
        remedy="Add a constraint, or delete the shape.",
        line=47,
    )


def test_every_finding_is_complete() -> None:
    payload = json.loads(Report([finding()], checked=34).as_json())
    assert payload["summary"] == {"errors": 1, "warnings": 0, "checked": 34}
    for item in payload["findings"]:
        assert all(item.get(key) for key in REQUIRED)


def test_findings_are_sorted_stably() -> None:
    report = Report([finding("REG-2"), finding("DOC-1"), finding("OWN-1")])
    assert [f.id for f in report.sorted_findings()] == ["DOC-1", "OWN-1", "REG-2"]


def test_findings_are_sorted_by_file_then_line() -> None:
    def at(file: str, line: int, rule: str) -> Finding:
        return Finding(id=rule, severity="error", file=file, line=line, subject="s",
                       message="m", remedy="r")

    report = Report([at("b.md", 1, "ATTACH-1"), at("a.md", 44, "ATTACH-1"),
                     at("a.md", 43, "DANGLE-2")])
    assert [(f.file, f.line) for f in report.sorted_findings()] == [
        ("a.md", 43), ("a.md", 44), ("b.md", 1)]


def test_the_summary_says_delegated_failures_are_counted_apart() -> None:
    report = Report(checked=3)
    report.delegated_failures = 1
    assert "1 delegated validation(s) failed" in report.as_text()
    assert "1 delegated" not in Report(checked=3).as_text()


def test_line_is_omitted_when_unknown() -> None:
    bare = Finding(id="OWN-1", severity="error", file="f", subject="s", message="m", remedy="r")
    assert "line" not in bare.model_dump(exclude_none=True)


def test_text_output_names_file_and_remedy() -> None:
    text = Report([finding()]).as_text()
    assert "model/shapes/invariants.ttl:47" in text
    assert "remedy:" in text


def test_clean_report_says_so() -> None:
    assert Report(checked=3).as_text() == "No findings (3 checks)."
