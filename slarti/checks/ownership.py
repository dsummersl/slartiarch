from __future__ import annotations

from slarti.findings import Finding, Severity
from slarti.instances import Corpus
from slarti.models import Models

OWNER_ANNOTATION = "owner"


def _is_owned(cls: object, schema_ids: set[str]) -> bool:
    abstract = getattr(cls, "abstract", False)
    mixin = getattr(cls, "mixin", False)
    from_schema = getattr(cls, "from_schema", "")
    return bool(not abstract and not mixin and from_schema in schema_ids)


def owned_classes(models: Models) -> list[str]:
    """Concrete schema classes that must declare an owning element.

    ``imports=True`` lets classes split across multiple files be visible;
    the ``linkml:types`` namespace and other truly-imported schemas are
    filtered out via ``from_schema`` against the project's own schema ids.
    """
    view = models.schema
    if view is None:
        return []
    schema_ids = models.schema_id_set
    return sorted(name for name, cls in view.all_classes(imports=True).items()
                  if _is_owned(cls, schema_ids))


def _missing_owner(name: str, schema_file: str) -> Finding:
    return Finding(
        id="OWN-1",
        severity=Severity.error,
        file=schema_file,
        subject=name,
        message=f"class '{name}' has no owner.",
        remedy=(
            f"Add 'annotations: {{owner: <element-id>}}' to class '{name}', "
            "and list the class in that element's 'owns'."
        ),
    )


def _unknown_owner(name: str, owner: str, schema_file: str) -> Finding:
    return Finding(
        id="OWN-2",
        severity=Severity.error,
        file=schema_file,
        subject=name,
        message=(
            f"class '{name}' names owner '{owner}', "
            "which is not an element in the architecture."
        ),
        remedy=(
            f"Point '{name}' at an element that exists, "
            f"or declare element '{owner}' in the architecture."
        ),
    )


def _unclaimed(name: str, owner: str, schema_file: str) -> Finding:
    return Finding(
        id="OWN-3",
        severity=Severity.error,
        file=schema_file,
        subject=name,
        message=f"class '{name}' names owner '{owner}', but '{owner}' does not claim it.",
        remedy=f"Add '{name}' to the 'owns' of element '{owner}'.",
    )


def _class_findings(models: Models, corpus: Corpus) -> list[Finding]:
    findings = []
    for name in owned_classes(models):
        owner = models.class_annotation(name, OWNER_ANNOTATION)
        schema_file = models.schema_file_for(name)
        if owner is None:
            findings.append(_missing_owner(name, schema_file))
        elif owner not in corpus.elements:
            findings.append(_unknown_owner(name, owner, schema_file))
        elif name not in corpus.elements[owner].owns:
            findings.append(_unclaimed(name, owner, schema_file))
    return findings


def _element_findings(models: Models, corpus: Corpus) -> list[Finding]:
    known = set(owned_classes(models))
    findings = []
    for element in sorted(corpus.elements.values(), key=lambda e: e.id):
        for entity in element.owns:
            if entity not in known:
                findings.append(
                    Finding(
                        id="OWN-4",
                        severity=Severity.error,
                        file=corpus.element_files[element.id],
                        subject=element.id,
                        message=(
                            f"element '{element.id}' claims class '{entity}', "
                            "which is not in the schema."
                        ),
                        remedy=(
                            f"Remove '{entity}' from the 'owns' of '{element.id}', "
                            "or add the class to the schema."
                        ),
                    )
                )
    return findings


def _double_claim_findings(models: Models, corpus: Corpus) -> list[Finding]:
    findings = []
    for name in owned_classes(models):
        owners = corpus.owners_of(name)
        if len(owners) > 1:
            findings.append(
                Finding(
                    id="OWN-5",
                    severity=Severity.error,
                    file=corpus.element_files[owners[0]],
                    subject=name,
                    message=(
                        f"class '{name}' is claimed by more than one element: "
                        + ", ".join(owners)
                        + "."
                    ),
                    remedy=f"Leave '{name}' in the 'owns' of exactly one element.",
                )
            )
    return findings


def check(models: Models) -> list[Finding]:
    """OWN-1..OWN-5: schema classes against vocabulary elements, in both directions (I14)."""
    corpus = models.vocabulary
    return [
        *_class_findings(models, corpus),
        *_element_findings(models, corpus),
        *_double_claim_findings(models, corpus),
    ]
