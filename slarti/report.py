from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from slarti import __version__, resolvers, vocabulary
from slarti.checks import ownership as ownership_checks
from slarti.models import Models
from slarti.registry import Constraint, is_unenforced, kind_text

_KIND_TO_LAYER: dict[str | None, int | None] = {
    "likec4_element": 1,
    "likec4_relation": 1,
    "likec4_absent_relation": 1,
    "ownership": 1,
    "linkml_class": 2,
    "linkml_slot": 2,
    "shacl_shape": 3,
    "external": None,
}


def _layer_for(kind: str | None) -> int | None:
    return _KIND_TO_LAYER.get(kind)

CHECKS: dict[str, str] = {
    "OWN-1": (
        "A schema class declares no owning element.\n"
        "Remedy: add 'annotations: {owner: <element-id>}' to the class, and list the "
        "class in that element's 'owns'."
    ),
    "OWN-2": (
        "A schema class names an owner that is not an element in the architecture.\n"
        "Remedy: correct the owner annotation, or declare the element."
    ),
    "OWN-3": (
        "A schema class names an owner that does not claim it back.\n"
        "Remedy: add the class name to that element's 'owns'."
    ),
    "OWN-4": (
        "An element claims a class that is not in the schema.\n"
        "Remedy: remove the class from 'owns', or add the class to the schema."
    ),
    "OWN-5": (
        "A schema class is claimed by more than one element.\n"
        "Remedy: leave the class in exactly one element's 'owns'."
    ),
    "REG-1": (
        "A constraint declares an enforcer that does not resolve in the model.\n"
        "Remedy: create the enforcer, correct the ref, or record the rule as "
        "'enforced_by: none' with a reason."
    ),
    "REG-2": (
        "A SHACL shape exists that no constraint references.\n"
        "Remedy: add a constraint with enforced_by.kind=shacl_shape and that ref, or delete "
        "the shape."
    ),
    "REG-3": (
        "A constraint is unenforced but gives no reason.\n"
        "Remedy: add a 'reason' explaining why the rule cannot be mechanically enforced."
    ),
    "REG-4": "A constraint ID is declared twice.\nRemedy: give every constraint a unique ID.",
    "REG-5": (
        "A constraint cites a decision that no document records.\n"
        "Remedy: document the decision in one of the architecture documents, or drop the "
        "'decision' field."
    ),
    "REG-6": (
        "A declared negative fixture is missing, unloadable, or conforms.\n"
        "Remedy: make the fixture exist and violate the declared shape."
    ),
    "REG-7": (
        "A negative fixture fails, but the report never names the declared shape.\n"
        "Remedy: narrow the fixture, or correct the declared ref."
    ),
    "REG-8": (
        "A likec4_absent_relation constraint is violated — the forbidden relation now exists "
        "in the model.\n"
        "Remedy: remove the forbidden relation from the LikeC4 model."
    ),
    "DOC-1": (
        "A generated region is stale relative to its source.\n"
        "Remedy: run 'slarti docs' and commit the result."
    ),
    "DOC-2": (
        "A generated diagram differs from what the model generates — it was hand-edited.\n"
        "Remedy: never edit files under the diagrams directory; run 'slarti docs'."
    ),
    "DOC-3": (
        "A region marker is unbalanced, or names a region slarti cannot fill.\n"
        "Remedy: balance the markers; use constraints, unverified, ownership or diagram:<view>."
    ),
    "DOC-4": (
        "A constraint in the registry has no row in the generated tables.\n"
        "Remedy: this is a generation bug in slarti; report it with the registry entry."
    ),
    "INP-1": (
        "A configured instance input does not exist.\n"
        "Remedy: create the file or directory, or remove it from 'instances' in the config."
    ),
    "INP-2": (
        "An instance file is not a YAML or JSON mapping.\n"
        "Remedy: write the file as a mapping with diagrams, elements and relations."
    ),
    "INP-3": (
        "An instance file does not conform to the vocabulary or the project schema.\n"
        "Remedy: correct the instance so it validates as 'Corpus', or declare the missing "
        "kind in the project schema."
    ),
    "ATTACH-1": (
        "A diagram node or edge has no disposition: it is neither attached nor ignored.\n"
        "Remedy: attach it ('element' on a node, 'relation' on an edge), or give it "
        "'ignored: <reason>'."
    ),
    "ATTACH-2": (
        "A diagram node or edge is both attached and ignored.\n"
        "Remedy: keep exactly one of the attachment and 'ignored'."
    ),
    "ATTACH-3": (
        "A diagram node or edge is ignored without a reason.\n"
        "Remedy: say why it depicts nothing in the architecture, or attach it."
    ),
    "IDENT-1": (
        "A name (an element id or alias) resolves to more than one element.\n"
        "Remedy: leave the name as the id or an alias of exactly one element."
    ),
    "IDENT-2": (
        "A node attaches through a name that resolves to more than one element.\n"
        "Remedy: attach the node by an element id, and give each alias to one element."
    ),
    "DANGLE-1": (
        "A node attaches to a name that is not an element id or alias.\n"
        "Remedy: attach the node to an element that exists, or declare the element."
    ),
    "DANGLE-2": (
        "An edge depicts a relation the architecture does not declare between the "
        "elements its endpoints depict.\n"
        "Remedy: declare the relation, or correct the edge's 'relation'."
    ),
    "DANGLE-3": (
        "An attached edge has an endpoint node that is ignored or unattached.\n"
        "Remedy: attach the endpoint node to an element, or ignore the edge with a reason."
    ),
    "DANGLE-4": (
        "An edge ends at a node id that no diagram declares.\n"
        "Remedy: point the edge at declared node ids, or add the missing node."
    ),
    "DRAWN-1": (
        "An element of a kind annotated 'drawn: true' appears in no diagram.\n"
        "Remedy: attach a node in some diagram to the element, or drop the annotation "
        "from its kind."
    ),
    "KIND-1": (
        "A node drawn as one or more element kinds (a Mermaid class) depicts an element of "
        "none of them.\n"
        "Remedy: draw the node as its element's kind, or attach it to an element of the "
        "kind it is drawn as."
    ),
    "MMD-1": (
        "A configured Mermaid input does not exist.\n"
        "Remedy: create the file or directory, or remove it from 'mermaid' in the config."
    ),
    "MMD-2": (
        "A Mermaid diagram is of a type slarti cannot read.\n"
        "Remedy: draw it as a supported type (sequenceDiagram, erDiagram), or move it out "
        "of the configured Mermaid inputs."
    ),
    "MMD-3": (
        "A Mermaid diagram uses syntax outside the supported subset of its type.\n"
        "Remedy: rewrite the line with the syntax docs/mermaid.md lists, or move the "
        "diagram out of the configured Mermaid inputs."
    ),
    "MMD-4": (
        "A '%% slarti:' directive is malformed, or names a node or edge the diagram does "
        "not draw.\n"
        "Remedy: write attach, ignore or alias with names the diagram draws."
    ),
    "ENV-1": (
        "A delegated tool is missing or outside its supported version range.\n"
        "Remedy: run 'slarti doctor' and install a version inside the range."
    ),
}

REMEDY_PREFIX = "Remedy:"


@dataclass(frozen=True)
class Check:
    """One check ID, its description and its remedy."""

    id: str
    description: str
    remedy: str

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "description": self.description, "remedy": self.remedy}


def _check(identifier: str, text: str) -> Check:
    description, _, remedy = text.partition(REMEDY_PREFIX)
    return Check(id=identifier, description=description.strip(), remedy=remedy.strip())


def catalogue() -> list[Check]:
    """Every check slarti can emit, in ID order."""
    return [_check(identifier, text) for identifier, text in sorted(CHECKS.items())]


def _enforcer_catalog() -> list[dict[str, Any]]:
    return [
        {
            "kind": "shacl_shape",
            "description": "A SHACL shape exists in the shapes directory (pyshacl)",
            "ref_format": "SHACL IRI/CURIE, e.g. 'slarti:FindingCarriesRemedy'",
            "optional_fields": ["fixture", "fixture_class"],
        },
        {
            "kind": "linkml_slot",
            "description": "A slot is declared on a class in the LinkML schema",
            "ref_format": "ClassName.slotName, e.g. 'Finding.file'",
            "optional_fields": [],
        },
        {
            "kind": "linkml_class",
            "description": "A class exists in the LinkML schema",
            "ref_format": "class name, e.g. 'Finding'",
            "optional_fields": [],
        },
        {
            "kind": "likec4_relation",
            "description": "A directed relation exists between two LikeC4 elements",
            "ref_format": "source -> target, e.g. 'slarti.env -> likec4'",
            "optional_fields": [],
        },
        {
            "kind": "likec4_absent_relation",
            "description": "Two LikeC4 elements exist but have no relation between them",
            "ref_format": "source -> target, e.g. 'slarti.cli -> sources'",
            "optional_fields": [],
        },
        {
            "kind": "likec4_element",
            "description": "An element exists in the LikeC4 model",
            "ref_format": "element ID, e.g. 'slarti.findings'",
            "optional_fields": [],
        },
        {
            "kind": "ownership",
            "description": "A LinkML class declares an owner that exists in the LikeC4 model",
            "ref_format": "class name, e.g. 'Finding'",
            "optional_fields": [],
        },
        {
            "kind": "external",
            "description": "Enforced outside slarti (CI, etc.). Resolves; must give a reason.",
            "ref_format": "free-form",
            "optional_fields": [],
        },
    ]


@dataclass(frozen=True)
class Rule:
    """A registry constraint with its enforcer resolved against the models."""

    constraint: Constraint
    resolves: bool
    file: str

    @property
    def enforced(self) -> bool:
        return not is_unenforced(self.constraint.enforced_by)

    def as_dict(self) -> dict[str, Any]:
        c = self.constraint
        e = c.enforced_by
        return {
            "id": c.id,
            "statement": c.statement,
            "file": self.file,
            "line": c.line,
            "decision": c.decision,
            "reason": c.reason,
            "enforced": self.enforced,
            "enforcer": {
                "layer": _layer_for(e.kind),
                "kind": e.kind,
                "ref": e.ref,
                "fixture": e.fixture,
                "fixture_class": e.fixture_class,
                "description": resolvers.describe(e),
                "resolves": self.resolves,
            },
        }


@dataclass(frozen=True)
class Shape:
    """A SHACL shape, where it lives, and the rules that reference it."""

    curie: str
    file: str
    referenced_by: list[str]

    @property
    def orphaned(self) -> bool:
        return not self.referenced_by

    def as_dict(self) -> dict[str, Any]:
        return {
            "curie": self.curie,
            "file": self.file,
            "referenced_by": self.referenced_by,
            "orphaned": self.orphaned,
        }


@dataclass(frozen=True)
class Owned:
    """A schema class, the owner it names, and the elements claiming it."""

    name: str
    owner: str | None
    claimed_by: list[str]

    def as_dict(self) -> dict[str, Any]:
        return {"class": self.name, "owner": self.owner, "claimed_by": self.claimed_by}


@dataclass(frozen=True)
class Report:
    """The whole state of the project: rules, shapes, ownership and checks."""

    rules: list[Rule]
    shapes: list[Shape]
    ownership: list[Owned]
    checks: list[Check]
    constraints_file: str

    @property
    def enforced(self) -> list[Rule]:
        return [r for r in self.rules if r.enforced]

    @property
    def unenforced(self) -> list[Rule]:
        return [r for r in self.rules if not r.enforced]

    @property
    def orphaned(self) -> list[Shape]:
        return [s for s in self.shapes if s.orphaned]

    def as_json(self) -> str:
        payload = {
            "seam_version": __version__,
            "vocabulary": {
                "import": vocabulary.IMPORT,
                "version": vocabulary.version(),
                "profiles": vocabulary.profile_versions(),
            },
            "constraints_file": self.constraints_file,
            "enforcer_kinds": _enforcer_catalog(),
            "constraints": [r.as_dict() for r in self.rules],
            "shacl": [s.as_dict() for s in self.shapes],
            "linkml_ownership": [o.as_dict() for o in self.ownership],
            "checks": [c.as_dict() for c in self.checks],
            "summary": {
                "constraints": len(self.rules),
                "enforced": len(self.enforced),
                "unenforced": len(self.unenforced),
                "shacl_shapes": len(self.shapes),
                "orphaned_shapes": len(self.orphaned),
                "owned_classes": len(self.ownership),
                "checks": len(self.checks),
            },
        }
        return json.dumps(payload, indent=2, sort_keys=False)

    def as_text(self) -> str:
        lines = ["Enforced:"]
        lines.extend(_enforced_lines(self.enforced))
        lines.append("")
        lines.append("Unenforced (declared, with a reason):")
        lines.extend(_unenforced_lines(self.unenforced))
        lines.append("")
        lines.append("Orphaned shapes (declared, unreferenced):")
        lines.extend(f"  {s.curie}  {s.file}" for s in self.orphaned)
        lines.append("")
        lines.append("Checks:")
        lines.extend(f"  {c.id}  {c.description.splitlines()[0]}" for c in self.checks)
        lines.append("")
        lines.append(
            f"{len(self.enforced)} enforced, {len(self.unenforced)} unenforced, "
            f"{len(self.orphaned)} orphaned shape(s)."
        )
        return "\n".join(lines)


def _enforced_lines(rules: list[Rule]) -> list[str]:
    lines = []
    for rule in rules:
        enforcer = resolvers.describe(rule.constraint.enforced_by)
        mark = "" if rule.resolves else "  (UNRESOLVED)"
        lines.append(f"  {rule.constraint.id}  {rule.constraint.statement}")
        lines.append(f"      <- {kind_text(rule.constraint.enforced_by)} {enforcer}{mark}")
    return lines


def _unenforced_lines(rules: list[Rule]) -> list[str]:
    lines = []
    for rule in rules:
        lines.append(f"  {rule.constraint.id}  {rule.constraint.statement}")
        lines.append(f"      reason: {rule.constraint.reason or '-'}")
    return lines


def _shapes(models: Models, constraints: list[Constraint]) -> list[Shape]:
    shapes = []
    for curie, path in sorted(models.shapes.items()):
        referenced_by = sorted(
            c.id
            for c in constraints
            if c.enforced_by.kind == "shacl_shape" and c.enforced_by.ref == curie
        )
        shapes.append(
            Shape(curie=curie, file=models.config.rel(path), referenced_by=referenced_by)
        )
    return shapes


def _ownership(models: Models) -> list[Owned]:
    return [
        Owned(
            name=name,
            owner=models.class_annotation(name, ownership_checks.OWNER_ANNOTATION),
            claimed_by=models.vocabulary.owners_of(name),
        )
        for name in ownership_checks.owned_classes(models)
    ]


def build(models: Models, constraints: list[Constraint]) -> Report:
    """Resolve every seam into one report."""
    ordered = sorted(constraints, key=lambda c: c.id)
    file = models.config.paths["constraints"]
    return Report(
        rules=[Rule(c, resolvers.resolve(models, c.enforced_by), file) for c in ordered],
        shapes=_shapes(models, ordered),
        ownership=_ownership(models),
        checks=catalogue(),
        constraints_file=file,
    )


__all__ = ["Check", "Owned", "Report", "Rule", "Shape", "build", "catalogue"]
