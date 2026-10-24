from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import parse_qs

from slarti import proc, resolvers, vocabulary
from slarti.checks.ownership import owned_classes
from slarti.config import Config
from slarti.models import Models
from slarti.registry import Constraint, is_unenforced, kind_text

DIAGRAM_PREFIX = "diagram:"
LINKML_ERD_REGION = "linkml_erd"
TABLE_REGIONS = ("constraints", "unverified", "ownership")

_BOOL_ERD_OPTIONS = {
    "follow_references": "follow-references",
    "exclude_abstract_classes": "exclude-abstract-classes",
    "exclude_attributes": "exclude-attributes",
    "structural": "structural",
}


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _table(headers: list[str], rows: list[list[str]], empty: str) -> str:
    if not rows:
        return f"_{empty}_"
    lines = [_row(headers), _row(["---"] * len(headers))]
    lines.extend(_row(cells) for cells in rows)
    return "\n".join(lines)


def constraints_table(constraints: list[Constraint]) -> str:
    """The enforced-rules table: every rule and the enforcer that holds it."""
    rows = [
        [
            c.id,
            c.statement,
            f"{kind_text(c.enforced_by)} {resolvers.describe(c.enforced_by)}",
            c.decision or "-",
        ]
        for c in sorted(constraints, key=lambda c: c.id)
        if not is_unenforced(c.enforced_by)
    ]
    return _table(["ID", "Rule", "Enforced by", "Decision"], rows, "No enforced rules.")


def unverified_table(constraints: list[Constraint]) -> str:
    """The honest table: rules stated but not mechanically enforced."""
    rows = [
        [c.id, c.statement, c.reason or "-"]
        for c in sorted(constraints, key=lambda c: c.id)
        if is_unenforced(c.enforced_by)
    ]
    return _table(["ID", "Rule", "Why unenforced"], rows, "Every rule is enforced.")


def ownership_table(models: Models) -> str:
    """The ownership seam, rendered: which container owns which entity."""
    elements = models.vocabulary.elements
    rows = []
    for name in owned_classes(models):
        owner = models.class_annotation(name, "owner")
        title = (elements[owner].title or "-") if owner in elements else "-"
        rows.append([name, f"`{owner}`" if owner else "-", title])
    return _table(["Entity", "Owner", "Owner title"], rows, "No entities are owned.")


def render_diagrams(config: Config) -> dict[str, str]:
    """Delegate diagram generation to `likec4 codegen mermaid` (I2, §6), in a temp tree (I1)."""
    if not config.likec4_enabled():
        return {}
    with tempfile.TemporaryDirectory() as tmp:
        outdir = Path(tmp)
        argv = proc.likec4(["codegen", "mermaid", "-o", tmp, str(config.path("likec4"))])
        result = proc.run(argv, cwd=config.root)
        if result.code != 0:
            raise RuntimeError(f"likec4 codegen mermaid failed:\n{result.stderr or result.stdout}")
        return {p.stem: p.read_text(encoding="utf-8").strip() for p in sorted(outdir.glob("*.mmd"))}


def diagram_block(name: str, diagrams: dict[str, str]) -> str:
    if name not in diagrams:
        return f"_View `{name}` is not in the model._"
    return "```mermaid\n" + diagrams[name] + "\n```"


def _parse_erd_opts(region: str) -> list[str]:
    """Parse gen-erdiagram options from a region name like ``linkml_erd?classes=X,Y``."""
    _, _, qs = region.partition("?")
    extra: list[str] = []
    for key, values in parse_qs(qs, keep_blank_values=True).items():
        val = values[0] if values else ""
        extra += _erd_opt(key, val)
    return extra


def _classes_flags(val: str) -> list[str]:
    """Split a comma-separated class list into repeated ``--classes`` flags."""
    result: list[str] = []
    for name in val.split(","):
        stripped = name.strip()
        if stripped:
            result += ["--classes", stripped]
    return result


def _erd_opt(key: str, val: str) -> list[str]:
    flag = _BOOL_ERD_OPTIONS.get(key)
    if flag:
        return [f"--{flag}" if val in ("", "true", "1") else f"--no-{flag}"]
    if key == "classes":
        return _classes_flags(val)
    return [f"--{key.replace('_', '-')}", val]


def linkml_erd_block(models: Models, extra: list[str] | None = None) -> str:
    """Generate a Mermaid ER diagram from the LinkML schema via gen-erdiagram.

    ``extra`` is a list of additional CLI arguments forwarded to gen-erdiagram
    (e.g. ``["--classes", "Task,Report"]``).
    """
    index = models.config.schema_index()
    if index is None:
        return "_No LinkML schema found._"
    with tempfile.TemporaryDirectory() as tmp:
        imports = vocabulary.write_importmap(Path(tmp) / "importmap.json")
        argv = [
            "gen-erdiagram",
            "--format",
            "mermaid",
            "--importmap",
            str(imports),
            *(extra or []),
            str(index),
        ]
        result = proc.run(argv, cwd=models.config.root)
    if result.code != 0:
        return f"_gen-erdiagram failed:_\n{result.stderr or result.stdout}"
    return "```mermaid\n" + result.stdout.strip() + "\n```"


def _static_body(region: str, constraints: list[Constraint], models: Models) -> str | None:
    match region:
        case "constraints":
            return constraints_table(constraints)
        case "unverified":
            return unverified_table(constraints)
        case "ownership":
            return ownership_table(models)
        case _ if region == LINKML_ERD_REGION or region.startswith(LINKML_ERD_REGION + "?"):
            return linkml_erd_block(models, extra=_parse_erd_opts(region))
    return None


def region_content(
    region: str, constraints: list[Constraint], models: Models, diagrams: dict[str, str]
) -> str | None:
    """Generated body for a named region, or None if the name is unknown."""
    body = _static_body(region, constraints, models)
    if body is not None:
        return body
    if region.startswith(DIAGRAM_PREFIX):
        return diagram_block(region[len(DIAGRAM_PREFIX) :], diagrams)
    return None

