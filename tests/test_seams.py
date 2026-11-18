from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from slarti import config as config_module
from slarti import seams
from slarti.adapters import likec4
from slarti.checks import seams as seam_checks
from slarti.cli import app
from slarti.models import Contract, Models, class_span
from slarti.report import catalogue

FIXTURES = Path(__file__).parent / "data" / "seams"
RULES = ["SEAM-1", "SEAM-2"]


def write(root: Path, files: dict[str, str]) -> None:
    for name, body in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(body, encoding="utf-8")


def project(root: Path, corpus: str) -> Models:
    write(root, {
        "schema/todo.yaml": (FIXTURES / "schema.yaml").read_text(),
        "architecture/corpus.yaml": corpus,
        "slarti.toml": '[paths]\nlinkml = "schema"\ndocuments = []\ninstances = ["architecture"]\n',
    })
    models = Models(config=config_module.load(root))
    assert models.instances.findings == []
    return models


def fixture(root: Path, kind: str, rule: str) -> Models:
    return project(root, (FIXTURES / kind / f"{rule}.yaml").read_text())


@pytest.mark.parametrize("rule", RULES)
def test_invalid_fixture_fires_its_rule(tmp_path: Path, rule: str) -> None:
    findings = seam_checks.check(fixture(tmp_path, "invalid", rule))
    assert [f.id for f in findings] == [rule]
    assert findings[0].file == "architecture/corpus.yaml"
    assert findings[0].subject == "todo.api -> todo.db"


@pytest.mark.parametrize("rule", RULES)
def test_valid_fixture_is_silent(tmp_path: Path, rule: str) -> None:
    assert seam_checks.check(fixture(tmp_path, "valid", rule)) == []


def test_none_without_a_reason_is_seam_1(tmp_path: Path) -> None:
    models = project(tmp_path, (
        "elements:\n  - {id: a, kind: Service, name: A}\n  - {id: b, kind: Service, name: B}\n"
        "relations:\n  - {kind: Reads, source: a, target: b, contract: none}\n"
    ))
    [finding] = seam_checks.check(models)
    assert finding.id == "SEAM-1"
    assert "gives no reason" in finding.message


def test_a_contract_outside_the_project_does_not_resolve(tmp_path: Path) -> None:
    root = tmp_path / "project"
    (tmp_path / "outside.yaml").write_text("x: 1\n")
    models = project(root, (FIXTURES / "valid" / "SEAM-2.yaml").read_text())
    assert models.contract("../outside.yaml") is None
    assert models.contract("schema") == Contract(file="schema", directory=True)


def test_a_likec4_relation_is_told_to_use_metadata(tmp_path: Path) -> None:
    finding = seam_checks._missing(
        seam_checks.ModelRelation(source="a", target="b", title="t"), "model/x.c4")
    assert finding is not None and "metadata" in finding[2]


def test_every_rule_is_in_the_catalogue() -> None:
    assert set(RULES) <= {c.id for c in catalogue()}


def test_a_class_contract_spans_its_block(tmp_path: Path) -> None:
    models = fixture(tmp_path, "valid", "SEAM-1")
    contract = models.contract("Task")
    assert contract == Contract(file="schema/todo.yaml", lines=(20, 24))
    assert class_span(tmp_path / "schema/todo.yaml", "List") == (26, 27)
    assert class_span(tmp_path / "schema/todo.yaml", "Missing") is None


def test_a_class_from_an_import_is_not_a_project_contract(tmp_path: Path) -> None:
    assert fixture(tmp_path, "valid", "SEAM-1").contract("Element") is None


def test_directory_contracts_cover_the_files_inside() -> None:
    contract = Contract(file="db/migrations", directory=True)
    assert contract.covers("db/migrations/0001.sql")
    assert not contract.covers("db/migrations.sql")
    assert Contract(file="api.yaml").covers("api.yaml")


DIFF = """\
diff --git a/schema/todo.yaml b/schema/todo.yaml
index 1..2 100644
--- a/schema/todo.yaml
+++ b/schema/todo.yaml
@@ -21,0 +22,2 @@ classes:
+      done:
+        description: Whether it is done.
@@ -30 +32 @@ classes:
-x
+y
diff --git a/gone.yaml b/gone.yaml
deleted file mode 100644
--- a/gone.yaml
+++ /dev/null
@@ -1,3 +0,0 @@
-a
-b
-c
diff --git a/new.yaml b/new.yaml
new file mode 100644
--- /dev/null
+++ b/new.yaml
@@ -0,0 +1,2 @@
+a
+b
@@ -9,2 +8,0 @@
-gone
-gone
"""


def test_the_diff_is_read_as_hunks_at_the_head() -> None:
    changed = seams.parse_diff(DIFF)
    assert changed["schema/todo.yaml"].hunks == [(22, 23), (32, 32)]
    assert changed["gone.yaml"].deleted and changed["gone.yaml"].hunks == []
    assert changed["new.yaml"].hunks == [(1, 2), (8, 8)]


@pytest.mark.parametrize("url", [
    "git@github.com:octo/repo.git",
    "https://github.com/octo/repo",
    "https://github.com/octo/repo.git",
    "ssh://git@github.com/octo/repo.git",
])
def test_github_remotes_become_web_urls(url: str) -> None:
    assert seams.remote_url(url) == "https://github.com/octo/repo"


def test_other_remotes_have_no_web_url() -> None:
    assert seams.remote_url("https://gitlab.example/octo/repo") is None


SPAN = seams.Range(base="main", head="abc123", prefix="sub/", web="https://github.com/o/r")


def test_only_hunks_inside_a_class_contract_cross_it(tmp_path: Path) -> None:
    models = fixture(tmp_path, "valid", "SEAM-1")
    found = seams.crossings(models, SPAN, seams.parse_diff(DIFF))
    [crossing] = found
    assert (crossing.source, crossing.target, crossing.contract) == ("todo.api", "todo.db", "Task")
    assert [(h.start, h.end) for h in crossing.hunks or []] == [(22, 23)]
    assert crossing.hunks[0].url == "https://github.com/o/r/blob/abc123/sub/schema/todo.yaml#L22-L23"


def test_a_change_outside_every_contract_crosses_nothing(tmp_path: Path) -> None:
    models = fixture(tmp_path, "valid", "SEAM-1")
    changed = {"schema/todo.yaml": seams.Changed(hunks=[(1, 3)])}
    assert seams.crossings(models, SPAN, changed) == []
    assert "No relation's contract changed" in seams.as_markdown(SPAN, [])


def test_a_deleted_contract_file_is_listed(tmp_path: Path) -> None:
    models = fixture(tmp_path, "valid", "SEAM-2")
    found = seams.crossings(models, SPAN, {"schema/todo.yaml": seams.Changed(deleted=True)})
    assert len(found) == 1
    assert "`schema/todo.yaml` (deleted)" in seams.as_markdown(SPAN, found)


def test_markdown_and_json_say_the_same(tmp_path: Path) -> None:
    models = fixture(tmp_path, "valid", "SEAM-1")
    found = seams.crossings(models, SPAN, seams.parse_diff(DIFF))
    text = seams.as_markdown(SPAN, found)
    payload = json.loads(seams.as_json(SPAN, found))
    assert "### Changed" in text and "TODO[additive|breaking|internal]" in text
    [crossing] = payload["crossings"]
    for value in (crossing["source"], crossing["target"], crossing["title"],
                  crossing["contract"], crossing["hunks"][0]["url"]):
        assert str(value) in text
    assert payload["head"] == "abc123"


def test_without_a_web_url_the_lines_are_named_but_not_linked(tmp_path: Path) -> None:
    models = fixture(tmp_path, "valid", "SEAM-1")
    span = seams.Range(base="main", head="abc123")
    text = seams.as_markdown(span, seams.crossings(models, span, seams.parse_diff(DIFF)))
    assert "`schema/todo.yaml#L22-L23`" in text


def test_likec4_relation_metadata_is_carried_through() -> None:
    raw = {"source": {"model": "a"}, "target": {"model": "b"}, "title": "calls",
           "metadata": {"contract": "none", "contract_reason": "in-process"}}
    relation = likec4._relation(raw)
    assert relation["contract"] == "none" and relation["contract_reason"] == "in-process"
    bare = likec4._relation({"source": {"model": "a"}, "target": {"model": "b"}})
    assert "contract" not in bare


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                          text=True).stdout


@pytest.fixture
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project(tmp_path, (FIXTURES / "valid" / "SEAM-1.yaml").read_text())
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@example.org", "add", ".")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@example.org",
        "commit", "-qm", "base")
    git(tmp_path, "remote", "add", "origin", "git@github.com:octo/todo.git")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _commit(root: Path, message: str) -> None:
    git(root, "-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "-qam", message)


def test_seams_command_lists_a_changed_contract(repository: Path) -> None:
    schema = repository / "schema/todo.yaml"
    schema.write_text(schema.read_text().replace("What to do.", "What there is to do."))
    _commit(repository, "reword")
    head = git(repository, "rev-parse", "HEAD").strip()
    result = CliRunner().invoke(app, ["seams", "--base", "HEAD~1"])
    assert result.exit_code == 0, result.stdout
    assert "`todo.api -> todo.db`" in result.stdout
    assert f"https://github.com/octo/todo/blob/{head}/schema/todo.yaml#L24" in result.stdout
    payload = json.loads(CliRunner().invoke(app, ["seams", "--base", "HEAD~1", "--json"]).stdout)
    assert payload["crossings"][0]["hunks"][0]["start"] == 24


def test_seams_command_lists_nothing_when_no_contract_changed(repository: Path) -> None:
    (repository / "notes.md").write_text("unrelated\n")
    git(repository, "add", "notes.md")
    _commit(repository, "notes")
    result = CliRunner().invoke(app, ["seams", "--base", "HEAD~1"])
    assert result.exit_code == 0
    assert "No relation's contract changed" in result.stdout


def test_seams_command_reports_a_bad_base(repository: Path) -> None:
    result = CliRunner().invoke(app, ["seams", "--base", "no-such-ref"])
    assert result.exit_code == 2
