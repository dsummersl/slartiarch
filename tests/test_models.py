from __future__ import annotations

from pathlib import Path

from slarti import models as models_module
from slarti import report
from tests.conftest import make_models

SHAPE = """@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix todo: <https://example.org/todo/> .

todo:UniqueMembership
  a sh:NodeShape ;
  sh:targetClass todo:Membership ;
  sh:property [ sh:path todo:list ; sh:minCount 1 ] .
"""


def test_likec4_reaches_checks_only_as_vocabulary_instances(tmp_path: Path) -> None:
    models = make_models(tmp_path)
    corpus = models.vocabulary
    assert sorted(corpus.elements) == ["todo", "todo.api", "todo.db"]
    assert corpus.element_files["todo.api"] == models.config.paths["likec4"] + "/todo.c4"
    assert corpus.owners_of("Task") == ["todo.api"]
    assert corpus.owners_of("Ghost") == []
    assert corpus.has_relation("todo.api", "todo.db")
    assert not corpus.has_relation("todo.db", "todo.api")


def test_shape_names_are_curies(tmp_path: Path) -> None:
    path = tmp_path / "invariants.ttl"
    path.write_text(SHAPE, encoding="utf-8")
    found = models_module.shape_names([path])
    assert list(found) == ["todo:UniqueMembership"]
    assert models_module.shape_line(path, "todo:UniqueMembership") == 4


def test_every_check_id_has_a_remedy() -> None:
    catalogue = report.catalogue()
    assert {c.id for c in catalogue} == set(report.CHECKS)
    assert all(c.description and c.remedy for c in catalogue)
