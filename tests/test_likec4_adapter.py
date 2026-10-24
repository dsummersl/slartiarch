from __future__ import annotations

from pathlib import Path

from slarti.adapters import likec4
from slarti.checks import structure
from slarti.models import Models
from tests.conftest import make_config

SOURCE = """model {
  todo = system 'Todo' {
    api = container 'API' {
      metadata {
        owns 'Task, TodoList'
      }
    }
    container db 'DB'
  }
  user = person 'User'
  user -> todo.api 'uses'
  todo.api -> todo.db 'reads'
}

views {
  view index {
    include *
  }
}
"""

PAYLOAD = {
    "elements": {
        "todo": {"id": "todo", "title": "Todo", "kind": "system"},
        "todo.api": {
            "id": "todo.api",
            "title": "API",
            "kind": "container",
            "description": {"txt": "Serves the lists."},
            "metadata": {"owns": "Task, TodoList"},
        },
        "todo.db": {"id": "todo.db", "title": "DB", "kind": "container"},
        "user": {"id": "user", "title": "User", "kind": "person"},
    },
    "relations": {
        "r1": {"id": "r1", "title": "uses", "source": {"model": "user"},
               "target": {"model": "todo.api"}},
        "r2": {"id": "r2", "title": "reads", "source": {"model": "todo.api"},
               "target": {"model": "todo.db"}},
    },
    "views": {
        "index": {
            "id": "index",
            "title": "Landscape",
            "nodes": [
                {"id": "user", "title": "User", "modelRef": "user"},
                {"id": "todo", "title": "Todo", "modelRef": "todo"},
                {"id": "todo.api", "title": "API", "modelRef": "todo.api"},
                {"id": "todo.db", "title": "DB", "modelRef": "todo.db"},
                {"id": "@gr1", "title": "Backend"},
            ],
            "edges": [
                {"id": "e1", "source": "user", "target": "todo", "label": "uses",
                 "relations": ["r1"]},
                {"id": "e2", "source": "todo.api", "target": "todo.db", "label": "reads",
                 "relations": ["r2"]},
            ],
        },
    },
}

C4 = "docs/slarti/likec4/todo.c4"


def adapted(tmp_path: Path) -> likec4.Documents:
    config = make_config(tmp_path)
    (config.path("likec4") / "todo.c4").write_text(SOURCE, encoding="utf-8")
    return likec4.translate(PAYLOAD, likec4.Sources.read(config))


def test_instances_are_keyed_by_the_c4_file_declaring_them(tmp_path: Path) -> None:
    documents = adapted(tmp_path)
    assert list(documents) == [C4]
    instance = documents[C4]
    assert [e["id"] for e in instance["elements"]] == ["todo", "todo.api", "todo.db", "user"]
    assert len(instance["relations"]) == 2
    assert [d["id"] for d in instance["diagrams"]] == ["index"]


def test_elements_carry_owns_and_description(tmp_path: Path) -> None:
    api = adapted(tmp_path)[C4]["elements"][1]
    assert api == {
        "id": "todo.api",
        "kind": "container",
        "name": "API",
        "owns": ["Task", "TodoList"],
        "description": "Serves the lists.",
    }


def test_both_declaration_forms_are_located(tmp_path: Path) -> None:
    sources = likec4.Sources.read(make_config(tmp_path))
    assert sources.element("todo.db", "container") == (sources.fallback, None)
    adapted(tmp_path)
    sources = likec4.Sources.read(make_config(tmp_path))
    assert sources.element("todo.api", "container") == (C4, 3)
    assert sources.element("todo.db", "container") == (C4, 8)


def test_views_become_diagrams_located_at_their_declaration(tmp_path: Path) -> None:
    diagram = adapted(tmp_path)[C4]["diagrams"][0]
    assert diagram["location"] == {"file": C4, "line": 16, "source_id": "index",
                                   "label": "Landscape"}
    node = diagram["nodes"][2]
    assert node["id"] == "index:todo.api" and node["element"] == "todo.api"
    assert node["location"]["source_id"] == "todo.api"
    assert diagram["nodes"][4]["ignored"] == likec4.GROUP_REASON


def test_derived_edges_are_ignored_and_direct_ones_attached(tmp_path: Path) -> None:
    derived, direct = adapted(tmp_path)[C4]["diagrams"][0]["edges"]
    assert derived["ignored"] == likec4.DERIVED_REASON and "relation" not in derived
    assert direct["relation"] == "reads"
    assert (direct["source"], direct["target"]) == ("index:todo.api", "index:todo.db")


def test_the_adapter_output_passes_the_diagram_checks(tmp_path: Path) -> None:
    models = Models(config=make_config(tmp_path), _likec4=adapted(tmp_path))
    assert len(models.vocabulary.nodes) == 5
    assert structure.check(models) == []


def test_instance_files_override_adapted_elements(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    (tmp_path / "corpus.yaml").write_text(
        "elements:\n  - id: todo.db\n    kind: Element\n    name: Store\n", encoding="utf-8"
    )
    config = type(config)(root=tmp_path, paths=config.paths, instances=["corpus.yaml"])
    models = Models(config=config, _likec4=adapted(tmp_path))
    assert models.vocabulary.element_files["todo.db"] == "corpus.yaml"
    assert models.vocabulary.element_files["todo.api"] == C4
