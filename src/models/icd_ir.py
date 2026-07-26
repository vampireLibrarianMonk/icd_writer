"""Semantic ICD Intermediate Representation (ICD IR).

Represents the engineering meaning of the document: requirements, interfaces,
messages, signals, systems, protocols, and relationships.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from src.models.common import SourceReference


class RequirementType(str, Enum):
    """Types of requirements in an ICD."""

    FUNCTIONAL = "functional"
    INTERFACE = "interface_requirement"
    PERFORMANCE = "performance"
    DESIGN = "design"
    ENVIRONMENTAL = "environmental"
    SAFETY = "safety"
    RELIABILITY = "reliability"
    DATA = "data"
    CONSTRAINT = "constraint"
    ASSUMPTION = "assumption"


class VerificationMethod(str, Enum):
    """Methods for verifying requirements."""

    TEST = "test"
    ANALYSIS = "analysis"
    INSPECTION = "inspection"
    DEMONSTRATION = "demonstration"
    SIMILARITY = "similarity"


class TbxStatus(str, Enum):
    """Status for TBD/TBR/TBC/TBS items."""

    TBD = "tbd"  # To Be Determined
    TBR = "tbr"  # To Be Resolved
    TBC = "tbc"  # To Be Confirmed
    TBS = "tbs"  # To Be Supplied


class ChangeRecord(BaseModel):
    """Record of a change to a requirement or interface."""

    revision: str
    date: str | None = None
    description: str
    author: str | None = None


class Requirement(BaseModel):
    """A single requirement extracted from an ICD."""

    id: str
    text_verbatim: str
    text_normalized: str | None = None
    requirement_type: RequirementType = RequirementType.INTERFACE
    verification_method: VerificationMethod | None = None
    section: str | None = None
    source: SourceReference | None = None
    extraction_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    human_verified: bool = False
    interface_ids: list[str] = Field(default_factory=list)
    parent_requirement_id: str | None = None
    tbx_items: list[TbxStatus] = Field(default_factory=list)
    change_history: list[ChangeRecord] = Field(default_factory=list)


class DataField(BaseModel):
    """A data field within a message or packet."""

    id: str
    name: str
    bit_offset: int
    bit_length: int
    data_type: str | None = None
    unit: str | None = None
    description: str | None = None
    valid_range: str | None = None
    default_value: str | None = None


class Message(BaseModel):
    """A message or packet definition."""

    id: str
    name: str
    direction: str | None = None  # "uplink", "downlink", "bidirectional"
    protocol: str | None = None
    total_bits: int | None = None
    fields: list[DataField] = Field(default_factory=list)
    description: str | None = None
    rate: str | None = None  # e.g., "1 Hz", "on demand"


class Signal(BaseModel):
    """A signal definition."""

    id: str
    name: str
    direction: str  # "input", "output", "bidirectional"
    data_type: str | None = None
    unit: str | None = None
    rate: str | None = None
    description: str | None = None
    interface_id: str | None = None
    source_system: str | None = None
    destination_system: str | None = None


class TransportInfo(BaseModel):
    """Transport layer information for an interface."""

    protocol: str | None = None
    physical_medium: str | None = None
    data_rate: str | None = None
    encoding: str | None = None


class Interface(BaseModel):
    """An interface definition between systems."""

    id: str
    name: str
    provider: str | None = None
    consumer: str | None = None
    transport: TransportInfo | None = None
    requirements: list[str] = Field(default_factory=list)  # requirement IDs
    messages: list[str] = Field(default_factory=list)  # message IDs
    signals: list[str] = Field(default_factory=list)  # signal IDs
    description: str | None = None


class System(BaseModel):
    """A system or subsystem participating in interfaces."""

    id: str
    name: str
    system_type: str = "system"  # system, subsystem, component
    parent_id: str | None = None
    interfaces: list[str] = Field(default_factory=list)  # interface IDs


class Acronym(BaseModel):
    """An acronym and its definition."""

    abbreviation: str
    definition: str
    first_occurrence_page: int | None = None


class RevisionInfo(BaseModel):
    """Document revision information."""

    revision: str
    date: str | None = None
    author: str | None = None
    description: str | None = None
    approved_by: str | None = None


class SemanticIcdIR(BaseModel):
    """Semantic ICD Intermediate Representation.

    The engineering meaning model: requirements, interfaces, messages,
    signals, systems, protocols, and relationships. Linked to the
    Document IR through stable identifiers.
    """

    document_id: str
    document_title: str | None = None
    revision: RevisionInfo | None = None
    revision_history: list[RevisionInfo] = Field(default_factory=list)

    systems: list[System] = Field(default_factory=list)
    interfaces: list[Interface] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    signals: list[Signal] = Field(default_factory=list)
    acronyms: list[Acronym] = Field(default_factory=list)
