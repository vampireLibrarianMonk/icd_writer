"""Semantic ICD Intermediate Representation (ICD IR).

Represents the engineering meaning of the document: requirements, interfaces,
messages, signals, systems, protocols, and relationships.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

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
    date: Optional[str] = None
    description: str
    author: Optional[str] = None


class Requirement(BaseModel):
    """A single requirement extracted from an ICD."""

    id: str
    text_verbatim: str
    text_normalized: Optional[str] = None
    requirement_type: RequirementType = RequirementType.INTERFACE
    verification_method: Optional[VerificationMethod] = None
    section: Optional[str] = None
    source: Optional[SourceReference] = None
    extraction_confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    human_verified: bool = False
    interface_ids: list[str] = Field(default_factory=list)
    parent_requirement_id: Optional[str] = None
    tbx_items: list[TbxStatus] = Field(default_factory=list)
    change_history: list[ChangeRecord] = Field(default_factory=list)


class DataField(BaseModel):
    """A data field within a message or packet."""

    id: str
    name: str
    bit_offset: int
    bit_length: int
    data_type: Optional[str] = None
    unit: Optional[str] = None
    description: Optional[str] = None
    valid_range: Optional[str] = None
    default_value: Optional[str] = None


class Message(BaseModel):
    """A message or packet definition."""

    id: str
    name: str
    direction: Optional[str] = None  # "uplink", "downlink", "bidirectional"
    protocol: Optional[str] = None
    total_bits: Optional[int] = None
    fields: list[DataField] = Field(default_factory=list)
    description: Optional[str] = None
    rate: Optional[str] = None  # e.g., "1 Hz", "on demand"


class Signal(BaseModel):
    """A signal definition."""

    id: str
    name: str
    direction: str  # "input", "output", "bidirectional"
    data_type: Optional[str] = None
    unit: Optional[str] = None
    rate: Optional[str] = None
    description: Optional[str] = None
    interface_id: Optional[str] = None
    source_system: Optional[str] = None
    destination_system: Optional[str] = None


class TransportInfo(BaseModel):
    """Transport layer information for an interface."""

    protocol: Optional[str] = None
    physical_medium: Optional[str] = None
    data_rate: Optional[str] = None
    encoding: Optional[str] = None


class Interface(BaseModel):
    """An interface definition between systems."""

    id: str
    name: str
    provider: Optional[str] = None
    consumer: Optional[str] = None
    transport: Optional[TransportInfo] = None
    requirements: list[str] = Field(default_factory=list)  # requirement IDs
    messages: list[str] = Field(default_factory=list)  # message IDs
    signals: list[str] = Field(default_factory=list)  # signal IDs
    description: Optional[str] = None


class System(BaseModel):
    """A system or subsystem participating in interfaces."""

    id: str
    name: str
    system_type: str = "system"  # system, subsystem, component
    parent_id: Optional[str] = None
    interfaces: list[str] = Field(default_factory=list)  # interface IDs


class Acronym(BaseModel):
    """An acronym and its definition."""

    abbreviation: str
    definition: str
    first_occurrence_page: Optional[int] = None


class RevisionInfo(BaseModel):
    """Document revision information."""

    revision: str
    date: Optional[str] = None
    author: Optional[str] = None
    description: Optional[str] = None
    approved_by: Optional[str] = None


class SemanticIcdIR(BaseModel):
    """Semantic ICD Intermediate Representation.

    The engineering meaning model: requirements, interfaces, messages,
    signals, systems, protocols, and relationships. Linked to the
    Document IR through stable identifiers.
    """

    document_id: str
    document_title: Optional[str] = None
    revision: Optional[RevisionInfo] = None
    revision_history: list[RevisionInfo] = Field(default_factory=list)

    systems: list[System] = Field(default_factory=list)
    interfaces: list[Interface] = Field(default_factory=list)
    requirements: list[Requirement] = Field(default_factory=list)
    messages: list[Message] = Field(default_factory=list)
    signals: list[Signal] = Field(default_factory=list)
    acronyms: list[Acronym] = Field(default_factory=list)
