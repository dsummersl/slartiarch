from __future__ import annotations

import re
import sys
from datetime import (
    date,
    datetime,
    time
)
from decimal import Decimal
from enum import Enum
from typing import (
    Any,
    ClassVar,
    Literal,
    Optional,
    Union
)

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    field_validator,
    model_serializer
)


metamodel_version = "1.11.0"
version = "None"


class ConfiguredBaseModel(BaseModel):
    model_config = ConfigDict(
        serialize_by_alias = True,
        validate_by_name = True,
        validate_assignment = True,
        validate_default = True,
        extra = "forbid",
        arbitrary_types_allowed = True,
        use_enum_values = True,
        strict = False,
    )





class LinkMLMeta(RootModel):
    root: dict[str, Any] = {}
    model_config = ConfigDict(frozen=True)

    def __getattr__(self, key:str):
        return getattr(self.root, key)

    def __getitem__(self, key:str):
        return self.root[key]

    def __setitem__(self, key:str, value):
        self.root[key] = value

    def __contains__(self, key:str) -> bool:
        return key in self.root


linkml_meta = LinkMLMeta({'default_prefix': 'slarti',
     'default_range': 'string',
     'description': 'The entities slarti reasons about. Every class names the '
                    'element that owns it; every owning element claims it back '
                    '(OWN-1..OWN-5).',
     'id': 'https://dsummersl.github.io/slarti',
     'imports': ['linkml:types'],
     'name': 'slarti',
     'prefixes': {'linkml': {'prefix_prefix': 'linkml',
                             'prefix_reference': 'https://w3id.org/linkml/'},
                  'slarti': {'prefix_prefix': 'slarti',
                             'prefix_reference': 'https://dsummersl.github.io/slarti/'}},
     'source_file': 'docs/slarti/linkml/slarti.yaml',
     'title': 'The slarti domain'} )

class Severity(str, Enum):
    """
    Whether a finding blocks the build or merely informs.
    """
    error = "error"
    """
    The build fails.
    """
    warning = "warning"
    """
    The build continues.
    """


class EnforcerKind(str, Enum):
    """
    The enforcer kinds a constraint may name.
    """
    shacl_shape = "shacl_shape"
    """
    A hand-written SHACL shape.
    """
    linkml_slot = "linkml_slot"
    """
    A slot on a schema class.
    """
    linkml_class = "linkml_class"
    """
    A schema class.
    """
    likec4_relation = "likec4_relation"
    """
    A relation that must exist in the model.
    """
    likec4_absent_relation = "likec4_absent_relation"
    """
    A relation that must not exist in the model.
    """
    likec4_element = "likec4_element"
    """
    An element that must exist in the model.
    """
    ownership = "ownership"
    """
    The ownership seam between the schema and the model.
    """
    external = "external"
    """
    Something outside both models, which must give a reason.
    """



class Finding(ConfiguredBaseModel):
    """
    One machine-readable check result, addressed to a human or an agent.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'owner': {'tag': 'owner', 'value': 'slarti.findings'}},
         'from_schema': 'https://dsummersl.github.io/slarti'})

    id: str = Field(default=..., description="""A stable check ID such as OWN-1; retired IDs are never reused.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Finding', 'Constraint', 'ModelElement']} })
    severity: Severity = Field(default=..., description="""Whether the finding fails the build.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Finding']} })
    file: str = Field(default=..., description="""The file the finding is about.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Finding']} })
    line: Optional[int] = Field(default=None, description="""The line in that file, when the source can be located.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Finding', 'Constraint', 'Region']} })
    subject: str = Field(default=..., description="""The entity the finding is about, in domain terms.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Finding']} })
    message: str = Field(default=..., description="""What is wrong, phrased in domain terms rather than tool terms.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Finding']} })
    remedy: str = Field(default=..., description="""A sentence naming what to change to clear the finding.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Finding']} })


class Report(ConfiguredBaseModel):
    """
    The findings of one run, plus the number of checks performed.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'owner': {'tag': 'owner', 'value': 'slarti.findings'}},
         'from_schema': 'https://dsummersl.github.io/slarti'})

    seam_version: str = Field(default=..., description="""The version of slarti that produced the report.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Report']} })
    findings: Optional[list[Finding]] = Field(default=None, description="""Every finding of the run, in stable order.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Report']} })
    summary: Summary = Field(default=..., description="""The counts a caller reads before deciding whether to fail.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Report']} })


class Summary(ConfiguredBaseModel):
    """
    How a run came out, in counts.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'owner': {'tag': 'owner', 'value': 'slarti.findings'}},
         'from_schema': 'https://dsummersl.github.io/slarti'})

    errors: int = Field(default=..., description="""How many findings fail the build.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Summary']} })
    warnings: int = Field(default=..., description="""How many findings merely inform.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Summary']} })
    checked: int = Field(default=..., description="""How many checks the run performed.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Summary']} })


class Constraint(ConfiguredBaseModel):
    """
    One rule in the registry, with the enforcer that holds it.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'owner': {'tag': 'owner', 'value': 'slarti.registry'}},
         'from_schema': 'https://dsummersl.github.io/slarti'})

    id: str = Field(default=..., description="""The permanent identifier of the rule.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Finding', 'Constraint', 'ModelElement']} })
    statement: str = Field(default=..., description="""The rule, stated in one sentence of prose.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Constraint']} })
    enforced_by: Enforcer = Field(default=..., description="""The enforcer that holds the rule. Always present; an enforcer with no kind is the honest record of a rule nothing mechanically enforces.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Constraint']} })
    reason: Optional[str] = Field(default=None, description="""Why the rule is not mechanically enforced. Required when there is no enforcer.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Constraint']} })
    decision: Optional[str] = Field(default=None, description="""The decision record that introduced the rule.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Constraint']} })
    line: Optional[int] = Field(default=None, description="""Where the rule sits in the registry file.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Finding', 'Constraint', 'Region']} })


class Enforcer(ConfiguredBaseModel):
    """
    The thing that actually holds a rule, and the fixture that proves it fires.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'owner': {'tag': 'owner', 'value': 'slarti.registry'}},
         'from_schema': 'https://dsummersl.github.io/slarti'})

    kind: Optional[EnforcerKind] = Field(default=None, description="""What sort of enforcer this is.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Enforcer', 'ModelElement', 'ModelRelation']} })
    ref: Optional[str] = Field(default=None, description="""The identifier of the enforcer, resolved against the models.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Enforcer']} })
    fixture: Optional[str] = Field(default=None, description="""A case that must fail, naming this enforcer in the violation report.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Enforcer']} })
    fixture_class: Optional[str] = Field(default=None, description="""The schema class a YAML fixture instantiates.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Enforcer']} })


class ModelElement(ConfiguredBaseModel):
    """
    An architectural element, as a vocabulary instance, and the classes it owns.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'owner': {'tag': 'owner', 'value': 'slarti.models'}},
         'from_schema': 'https://dsummersl.github.io/slarti'})

    id: str = Field(default=..., description="""The fully qualified element identifier.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Finding', 'Constraint', 'ModelElement']} })
    title: str = Field(default=..., description="""The element's display title.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ModelElement', 'ModelRelation']} })
    kind: str = Field(default=..., description="""The element's kind, as its producer declares it.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Enforcer', 'ModelElement', 'ModelRelation']} })
    owns: list[str] = Field(default=..., description="""The schema classes this element claims.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ModelElement']} })


class ModelRelation(ConfiguredBaseModel):
    """
    A relation between two architectural elements.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'owner': {'tag': 'owner', 'value': 'slarti.models'}},
         'from_schema': 'https://dsummersl.github.io/slarti'})

    source: str = Field(default=..., description="""The element the relation starts at.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ModelRelation']} })
    target: str = Field(default=..., description="""The element the relation ends at.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ModelRelation']} })
    title: str = Field(default=..., description="""What the relation is called.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ModelElement', 'ModelRelation']} })
    kind: Optional[str] = Field(default=None, description="""The relation's kind, when its producer declares one.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Enforcer', 'ModelElement', 'ModelRelation']} })


class Region(ConfiguredBaseModel):
    """
    A generated region of the architecture document, between two markers.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'owner': {'tag': 'owner', 'value': 'slarti.docsgen'}},
         'from_schema': 'https://dsummersl.github.io/slarti'})

    name: str = Field(default=..., description="""The region name in its markers.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Region']} })
    body: str = Field(default=..., description="""The generated content between the markers.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Region']} })
    line: int = Field(default=..., description="""Where the opening marker sits in the document.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Finding', 'Constraint', 'Region']} })


class Probe(ConfiguredBaseModel):
    """
    The observed version and location of one delegated tool.
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'owner': {'tag': 'owner', 'value': 'slarti.env'}},
         'from_schema': 'https://dsummersl.github.io/slarti'})

    tool: str = Field(default=..., description="""The tool that was probed.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Probe']} })
    version: str = Field(default=..., description="""The version the probe detected, or 'not found'.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Probe']} })
    location: Optional[str] = Field(default=None, description="""Where the binary was found.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Probe']} })
    detail: str = Field(default=..., description="""The supported range, or why the probe failed.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Probe']} })
    ok: bool = Field(default=..., description="""Whether the tool may be used.""", json_schema_extra = { "linkml_meta": {'domain_of': ['Probe']} })


class ProjectPaths(ConfiguredBaseModel):
    """
    Where the model sources and the document live. Paths only (I6).
    """
    linkml_meta: ClassVar[LinkMLMeta] = LinkMLMeta({'annotations': {'owner': {'tag': 'owner', 'value': 'slarti.settings'}},
         'from_schema': 'https://dsummersl.github.io/slarti'})

    arch: Optional[str] = Field(default=None, description="""The LikeC4 sources directory.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProjectPaths']} })
    schema_dir: Optional[str] = Field(default=None, description="""The LinkML schema directory.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProjectPaths']} })
    shapes: Optional[str] = Field(default=None, description="""The hand-written SHACL directory.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProjectPaths']} })
    constraints: Optional[str] = Field(default=None, description="""The constraint registry file.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProjectPaths']} })
    data_valid: Optional[str] = Field(default=None, description="""Fixtures that must pass.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProjectPaths']} })
    data_invalid: Optional[str] = Field(default=None, description="""One fixture per rule, each of which must fail.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProjectPaths']} })
    document: Optional[str] = Field(default=None, description="""The architecture document.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProjectPaths']} })
    diagrams: Optional[str] = Field(default=None, description="""The generated diagram directory.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProjectPaths']} })
    build: Optional[str] = Field(default=None, description="""Transient output; gitignored.""", json_schema_extra = { "linkml_meta": {'domain_of': ['ProjectPaths']} })


# Model rebuild
# see https://pydantic-docs.helpmanual.io/usage/models/#rebuilding-a-model
Finding.model_rebuild()
Report.model_rebuild()
Summary.model_rebuild()
Constraint.model_rebuild()
Enforcer.model_rebuild()
ModelElement.model_rebuild()
ModelRelation.model_rebuild()
Region.model_rebuild()
Probe.model_rebuild()
ProjectPaths.model_rebuild()
