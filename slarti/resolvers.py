from __future__ import annotations

from collections.abc import Callable

from slarti.models import Models
from slarti.registry import Enforcer, is_unenforced, kind_text

RELATION_ARROW = "->"


def _split_relation(ref: str) -> tuple[str, str] | None:
    if RELATION_ARROW not in ref:
        return None
    source, target = ref.split(RELATION_ARROW, 1)
    return source.strip(), target.strip()


def _slot_exists(models: Models, ref: str) -> bool:
    view = models.schema
    if view is None or "." not in ref:
        return False
    class_name, slot_name = ref.split(".", 1)
    if view.get_class(class_name) is None:
        return False
    return slot_name in view.class_slots(class_name)


def _relation_exists(models: Models, ref: str) -> bool:
    pair = _split_relation(ref)
    return pair is not None and models.architecture.has_relation(*pair)


def _relation_absent(models: Models, ref: str) -> bool:
    pair = _split_relation(ref)
    if pair is None:
        return False
    known = models.architecture.elements
    return all(part in known for part in pair) and not models.architecture.has_relation(*pair)


def absent_relation_violated(models: Models, ref: str) -> bool:
    """Both elements exist but the forbidden relation is present."""
    pair = _split_relation(ref)
    if pair is None:
        return False
    source, target = pair
    model = models.architecture
    known = source in model.elements and target in model.elements
    return known and model.has_relation(source, target)


def _ownership_holds(models: Models, ref: str) -> bool:
    owner = models.class_annotation(ref, "owner")
    return owner is not None and owner in models.vocabulary.elements


RESOLVERS: dict[str, Callable[[Models, str], bool]] = {
    "shacl_shape": lambda models, ref: ref in models.shapes,
    "linkml_slot": _slot_exists,
    "linkml_class": lambda models, ref: bool(
        models.schema is not None and models.schema.get_class(ref) is not None
    ),
    "likec4_relation": _relation_exists,
    "likec4_absent_relation": _relation_absent,
    "likec4_element": lambda models, ref: ref in models.architecture.elements,
    "ownership": _ownership_holds,
    "external": lambda models, ref: True,
}


def describe(enforcer: Enforcer) -> str:
    """Human phrasing of an enforcer, for tables and messages."""
    if is_unenforced(enforcer):
        return "none"
    return f"`{enforcer.ref}`" if enforcer.ref else kind_text(enforcer)


def resolve(models: Models, enforcer: Enforcer) -> bool:
    """Answer: does this enforcer actually exist?"""
    if enforcer.kind is None:
        return True
    resolver = RESOLVERS.get(enforcer.kind)
    if resolver is None:
        return False
    return bool(resolver(models, enforcer.ref or ""))
