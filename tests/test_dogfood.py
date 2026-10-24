from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
USER_AUTHORED = ("model", "docs/architecture.md", "slarti.toml", "AGENTS.md")


def has_tools() -> bool:
    return shutil.which("linkml") is not None and (ROOT / "node_modules/.bin/likec4").exists()


needs_tools = pytest.mark.skipif(not has_tools(), reason="LikeC4 or LinkML is not installed")


def slarti(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["slartiarch", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )


def digest(paths: tuple[str, ...] = USER_AUTHORED) -> dict[str, str]:
    found = {}
    for name in paths:
        target = ROOT / name
        files = sorted(target.rglob("*")) if target.is_dir() else [target]
        for path in files:
            if path.is_file():
                found[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


@needs_tools
def test_slarti_checks_itself() -> None:
    result = slarti("check")
    assert result.returncode == 0, result.stdout + result.stderr


@needs_tools
def test_the_document_does_not_drift() -> None:
    result = slarti("check", "--no-docs")
    assert result.returncode == 0, result.stdout + result.stderr
    result = slarti("check")
    assert result.returncode == 0, result.stdout + result.stderr


@needs_tools
def test_check_touches_no_user_authored_file() -> None:
    before = digest()
    slarti("check")
    assert digest() == before


@needs_tools
def test_fix_is_idempotent() -> None:
    slarti("check", "--fix")
    once = digest(("docs",))
    slarti("check", "--fix")
    assert digest(("docs",)) == once


@needs_tools
def test_json_findings_are_machine_readable() -> None:
    result = slarti("check", "--json")
    payload = json.loads(result.stdout)
    assert payload["findings"] == []
    assert payload["summary"]["checked"] > 0
