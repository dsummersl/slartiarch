from __future__ import annotations

from pathlib import Path

from slarti.checks import ownership
from tests.conftest import SCHEMA, make_models

NO_OWNER = SCHEMA.replace("    annotations:\n      owner: todo.api\n", "")
WRONG_OWNER = SCHEMA.replace("owner: todo.api", "owner: todo.nowhere")


def ids(findings: list) -> list[str]:
    return [f.id for f in findings]


def test_clean_seam_has_no_findings(models) -> None:
    assert ownership.check(models) == []


def test_own1_class_without_owner(tmp_path: Path) -> None:
    findings = ownership.check(make_models(tmp_path, NO_OWNER, owns=()))
    assert ids(findings) == ["OWN-1"]
    assert "has no owner" in findings[0].message


def test_own2_owner_is_not_an_element(tmp_path: Path) -> None:
    findings = ownership.check(make_models(tmp_path, WRONG_OWNER, owns=()))
    assert ids(findings) == ["OWN-2"]


def test_own3_owner_does_not_claim_the_class(tmp_path: Path) -> None:
    findings = ownership.check(make_models(tmp_path, owns=()))
    assert ids(findings) == ["OWN-3"]


def test_own4_element_claims_an_unknown_entity(tmp_path: Path) -> None:
    findings = ownership.check(make_models(tmp_path, owns=("Task", "Ghost")))
    assert ids(findings) == ["OWN-4"]
    assert "Ghost" in findings[0].message


def test_own5_two_containers_claim_the_same_class(tmp_path: Path) -> None:
    models = make_models(tmp_path)
    claimed = models.architecture.elements
    claimed["todo.db"] = claimed["todo.db"].model_copy(update={"owns": ["Task"]})
    findings = ownership.check(models)
    assert ids(findings) == ["OWN-5"]


def test_every_finding_is_complete(tmp_path: Path) -> None:
    findings = ownership.check(make_models(tmp_path, NO_OWNER, owns=("Ghost",)))
    assert findings
    for finding in findings:
        assert finding.id and finding.file and finding.remedy and finding.subject
