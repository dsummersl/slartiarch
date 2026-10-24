from __future__ import annotations

from pathlib import Path

import pytest

from slarti.adapters.likec4 import Documents
from slarti.config import DEFAULTS, Config
from slarti.models import Models

SCHEMA = """id: https://example.org/example
name: example
prefixes:
  example: https://example.org/example/
  linkml: https://w3id.org/linkml/
default_prefix: example
default_range: string
imports:
  - linkml:types
classes:
  Task:
    annotations:
      owner: todo.api
    attributes:
      id:
        identifier: true
      list:
"""


def make_config(root: Path) -> Config:
    for key in ("likec4", "linkml", "shacl", "shacl_valid", "shacl_invalid"):
        (root / DEFAULTS[key]).mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    return Config(root=root, paths=dict(DEFAULTS))


def make_model(owns: tuple[str, ...] = ("Task",)) -> Documents:
    elements = [
        {"id": "todo", "name": "Todo", "kind": "system", "owns": []},
        {"id": "todo.api", "name": "API", "kind": "container", "owns": list(owns)},
        {"id": "todo.db", "name": "DB", "kind": "container", "owns": []},
    ]
    relations = [{"source": "todo.api", "target": "todo.db", "description": "reads"}]
    return {DEFAULTS["likec4"] + "/todo.c4": {"elements": elements, "relations": relations}}


def make_models(root: Path, schema: str = SCHEMA, owns: tuple[str, ...] = ("Task",)) -> Models:
    config = make_config(root)
    (config.path("linkml") / "example.yaml").write_text(schema, encoding="utf-8")
    return Models(config=config, _likec4=make_model(owns))


@pytest.fixture
def models(tmp_path: Path) -> Models:
    return make_models(tmp_path)


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return make_config(tmp_path)
