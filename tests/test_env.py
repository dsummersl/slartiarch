from __future__ import annotations

import sys
from pathlib import Path

import pytest

from slarti import env, proc

LIKEC4 = next(r for r in env.REQUIREMENTS if r.tool == "likec4")


def fake_run(version: str):
    def run(argv, cwd=None):  # noqa: ANN001, ANN202 - test double
        return proc.Result(code=0, stdout=version, stderr="")

    return run


@pytest.mark.parametrize(
    ("version", "ok"),
    [("1.58.9", False), ("1.59.0", True), ("1.99.3", True), ("2.0.0", False)],
)
def test_range_boundaries(monkeypatch, version: str, ok: bool) -> None:
    monkeypatch.setattr(proc, "run", fake_run(version))
    assert env.probe(LIKEC4).ok is ok


def test_missing_tool_is_reported(monkeypatch) -> None:
    def missing(argv, cwd=None):  # noqa: ANN001, ANN202 - test double
        raise proc.ToolMissing(argv[0])

    monkeypatch.setattr(proc, "run", missing)
    probe = env.probe(LIKEC4)
    assert not probe.ok
    assert probe.version == "not found"


def test_out_of_range_names_the_range_and_the_upgrade(monkeypatch) -> None:
    monkeypatch.setattr(proc, "run", fake_run("2.1.0"))
    probe = env.probe(LIKEC4)
    assert ">=1.59.0,<2" in probe.detail
    assert "npm install" in probe.detail


def test_env_findings_are_complete(monkeypatch) -> None:
    monkeypatch.setattr(proc, "run", fake_run("0.1.0"))
    findings = env.env_findings([env.probe(LIKEC4)])
    assert [f.id for f in findings] == ["ENV-1"]
    assert findings[0].remedy


def test_parse_version_ignores_prefixes() -> None:
    assert env.parse_version("v22.3.1\n") == (22, 3, 1)
    assert env.parse_version("linkml, version 1.11") == (1, 11, 0)
    assert env.parse_version("no version here") is None


def test_a_tool_beside_the_interpreter_resolves_off_path(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "linkml").write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python"))
    monkeypatch.setenv("PATH", "")
    assert proc.resolve("linkml") == str(tmp_path / "linkml")
    assert proc.resolve("pyshacl") is None
