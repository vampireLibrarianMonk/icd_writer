"""Unit tests for the data models."""

from src.models.common import BoundingBox, DocumentMetadata
from src.models.document_ir import (
    DocumentIR,
    PageClassification,
    PageClassificationType,
    PageInfo,
    TextBlock,
    TextStyle,
)
from src.models.icd_ir import (
    Interface,
    Requirement,
    RequirementType,
    SemanticIcdIR,
    VerificationMethod,
)


def test_bounding_box_properties():
    bbox = BoundingBox(x0=10.0, y0=20.0, x1=110.0, y1=70.0)
    assert bbox.width == 100.0
    assert bbox.height == 50.0
    assert bbox.area == 5000.0


def test_page_classification():
    pc = PageClassification(
        page_number=1,
        classifications=[
            PageClassificationType.NATIVE_DIGITAL_TEXT,
            PageClassificationType.COVER,
        ],
        native_text_available=True,
        ocr_required=False,
        confidence=0.95,
    )
    assert pc.page_number == 1
    assert PageClassificationType.COVER in pc.classifications
    assert pc.native_text_available is True


def test_text_block():
    block = TextBlock(
        id="block-p01-b00",
        block_type="heading",
        page=1,
        bbox=BoundingBox(x0=72.0, y0=72.0, x1=540.0, y1=100.0),
        text_verbatim="Interface Control Document",
        reading_order=0,
        style=TextStyle(font_name="Helvetica-Bold", font_size_pt=18.0, bold=True),
        confidence=1.0,
    )
    assert block.id == "block-p01-b00"
    assert block.block_type == "heading"
    assert block.style.bold is True


def test_document_ir_page_count():
    metadata = DocumentMetadata(
        filename="test.pdf",
        sha256="abc123",
        page_count=3,
        file_size_bytes=1024,
    )
    doc = DocumentIR(
        metadata=metadata,
        pages=[
            PageInfo(
                page_number=i,
                width_pt=612.0,
                height_pt=792.0,
                classification=PageClassification(
                    page_number=i,
                    classifications=[PageClassificationType.NATIVE_DIGITAL_TEXT],
                ),
            )
            for i in range(1, 4)
        ],
    )
    assert doc.page_count == 3


def test_requirement_model():
    req = Requirement(
        id="REQ-CMD-001",
        text_verbatim="The flight computer shall accept command transfer frames.",
        requirement_type=RequirementType.INTERFACE,
        verification_method=VerificationMethod.TEST,
        section="3.2.4",
        extraction_confidence=0.97,
    )
    assert req.id == "REQ-CMD-001"
    assert req.requirement_type == RequirementType.INTERFACE
    assert req.verification_method == VerificationMethod.TEST


def test_interface_model():
    iface = Interface(
        id="IF-CMD-001",
        name="Command Upload Interface",
        provider="Ground Segment",
        consumer="Flight Computer",
        requirements=["REQ-CMD-001", "REQ-CMD-002"],
        messages=["MSG-CMD-UPLINK"],
    )
    assert iface.id == "IF-CMD-001"
    assert len(iface.requirements) == 2


def test_semantic_icd_ir():
    icd = SemanticIcdIR(
        document_id="NASA-ICD-001",
        document_title="Command and Data Handling ICD",
        requirements=[
            Requirement(
                id="REQ-001",
                text_verbatim="The system shall...",
                requirement_type=RequirementType.FUNCTIONAL,
                extraction_confidence=0.9,
            )
        ],
        interfaces=[Interface(id="IF-001", name="Cmd Upload", requirements=["REQ-001"])],
    )
    assert icd.document_id == "NASA-ICD-001"
    assert len(icd.requirements) == 1
    assert len(icd.interfaces) == 1
