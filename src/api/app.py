"""FastAPI application for the ICD Editor backend.

Provides REST endpoints for document loading, editing, rendering,
and session management. WebSocket support for real-time progress.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.api.models_config import (
    AVAILABLE_MODELS,
    ModelConfig,
    estimate_document_cost,
)
from src.api.session import Action, ActionType, Session


def create_app() -> FastAPI:
    app = FastAPI(
        title="ICD Writer",
        description="NASA ICD PDF Editor — load, edit, export",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # In-memory state (single-user MVP)
    state = {"session": None, "document_ir": None, "config": ModelConfig()}

    # ─── Session ────────────────────────────────────────────────────

    @app.post("/session/start")
    def start_session():
        """Start a new editing session."""
        state["session"] = Session()
        return {"session_id": state["session"].session_id}

    @app.get("/session")
    def get_session():
        """Get current session info."""
        session = state["session"]
        if not session:
            raise HTTPException(404, "No active session")
        return {
            "session_id": session.session_id,
            "started_at": session.started_at.isoformat(),
            "document": session.document_path,
            "edit_count": session.edit_count,
            "action_count": len(session.actions),
        }

    @app.get("/session/actions")
    def get_actions():
        """Get all actions in the current session (the journal)."""
        session = state["session"]
        if not session:
            raise HTTPException(404, "No active session")
        return {
            "actions": [a.model_dump(mode="json") for a in session.actions],
            "undo_available": len(session.undo_stack) > 0,
            "redo_available": len(session.redo_stack) > 0,
        }

    @app.post("/session/save")
    def save_session():
        """Persist the session journal to disk."""
        session = state["session"]
        if not session:
            raise HTTPException(404, "No active session")
        from src.output_dir import OutputDir

        out = OutputDir(document_name=Path(session.document_path).stem)
        journal_path = out.intermediate / "session_journal.json"
        session.save_journal(journal_path)
        session.record(ActionType.DOCUMENT_SAVED)
        return {"saved_to": str(journal_path)}

    # ─── Document ──────────────────────────────────────────────────

    @app.post("/document/open")
    def open_document(pdf_path: str):
        """Open a PDF and run the extraction pipeline."""
        from src.ingestion.pdf_reader import ingest_pdf
        from src.pipeline import process_pdf

        path = Path(pdf_path)
        if not path.exists():
            raise HTTPException(404, f"File not found: {pdf_path}")

        # Detect if scanned or digital
        import fitz

        doc = fitz.open(str(path))
        page = doc[0]
        has_text = len(page.get_text("text").strip()) > 10
        page_count = len(doc)
        doc.close()

        if has_text:
            # Digital PDF — use native extraction
            document_ir = process_pdf(path)
            state["document_ir"] = document_ir
            method = "native"
        else:
            # Scanned — return cost estimate, don't run yet
            cost = estimate_document_cost(page_count, config=state["config"])
            return {
                "status": "scanned_detected",
                "page_count": page_count,
                "estimated_cost": cost,
                "message": "Document appears scanned. Confirm to run OCR pipeline.",
            }

        # Record action
        session = state["session"]
        if session:
            session.document_path = str(path)
            session.document_sha256 = document_ir.metadata.sha256
            session.record(ActionType.DOCUMENT_OPENED, data={"path": str(path), "method": method})

        return {
            "status": "ready",
            "method": method,
            "pages": document_ir.page_count,
            "text_blocks": sum(len(p.text_blocks) for p in document_ir.pages),
        }

    @app.post("/document/open-ocr")
    def open_document_ocr(pdf_path: str):
        """Run OCR pipeline on a scanned PDF (after user confirms cost)."""
        from src.ocr import ocr_ingest

        path = Path(pdf_path)
        config = state["config"]

        document_ir, cost_tracker, review_flags = ocr_ingest(
            path,
            region=config.region,
            use_rekognition=config.rekognition_enabled,
            use_bedrock_classify=config.classification_enabled,
            use_bedrock_disambiguate=config.disambiguation_enabled,
        )
        state["document_ir"] = document_ir

        session = state["session"]
        if session:
            session.document_path = str(path)
            session.document_sha256 = document_ir.metadata.sha256
            session.record(
                ActionType.OCR_REQUESTED,
                data={"cost": cost_tracker.total_cost, "pages": document_ir.page_count},
            )

        return {
            "status": "ready",
            "method": "ocr",
            "pages": document_ir.page_count,
            "text_blocks": sum(len(p.text_blocks) for p in document_ir.pages),
            "review_flags": len(review_flags),
            "cost": cost_tracker.total_cost,
        }

    @app.get("/document/page/{page_number}")
    def get_page(page_number: int):
        """Get a page's text blocks for display."""
        doc_ir = state["document_ir"]
        if not doc_ir:
            raise HTTPException(404, "No document loaded")
        if page_number < 1 or page_number > doc_ir.page_count:
            raise HTTPException(400, f"Invalid page: {page_number}")

        page = doc_ir.pages[page_number - 1]
        return {
            "page_number": page_number,
            "width_pt": page.width_pt,
            "height_pt": page.height_pt,
            "blocks": [
                {
                    "id": b.id,
                    "text": b.text_verbatim,
                    "bbox": {"x0": b.bbox.x0, "y0": b.bbox.y0, "x1": b.bbox.x1, "y1": b.bbox.y1},
                    "type": b.block_type,
                    "font_size": b.style.font_size_pt if b.style else None,
                    "confidence": b.confidence,
                    "is_ocr": b.is_ocr,
                }
                for b in page.text_blocks
            ],
        }

    # ─── Editing ───────────────────────────────────────────────────


    @app.get("/document/page/{page_number}/image")
    def get_page_image(page_number: int):
        """Render a page as PNG image for the viewer."""
        import fitz
        from fastapi.responses import Response

        session = state["session"]
        if not session or not session.document_path:
            raise HTTPException(404, "No document loaded")

        doc = fitz.open(session.document_path)
        if page_number < 1 or page_number > len(doc):
            doc.close()
            raise HTTPException(400, f"Invalid page: {page_number}")

        page = doc[page_number - 1]
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        doc.close()

        return Response(content=img_bytes, media_type="image/png")

    # ─── Editing ───────────────────────────────────────────────────

    class EditRequest(BaseModel):
        block_id: str
        new_text: str

    @app.put("/document/block/{block_id}")
    def edit_block(block_id: str, req: EditRequest):
        """Edit a text block's content."""
        doc_ir = state["document_ir"]
        if not doc_ir:
            raise HTTPException(404, "No document loaded")

        # Find the block
        for page in doc_ir.pages:
            for block in page.text_blocks:
                if block.id == block_id:
                    old_text = block.text_verbatim
                    block.text_verbatim = req.new_text

                    # Record action
                    session = state["session"]
                    if session:
                        session.record(
                            ActionType.BLOCK_EDITED,
                            page=page.page_number,
                            block_id=block_id,
                            data={"old_text": old_text, "new_text": req.new_text},
                        )

                    return {
                        "status": "updated",
                        "block_id": block_id,
                        "page": page.page_number,
                        "old_text": old_text,
                        "new_text": req.new_text,
                    }

        raise HTTPException(404, f"Block not found: {block_id}")

    @app.post("/document/undo")
    def undo():
        """Undo the last edit."""
        session = state["session"]
        doc_ir = state["document_ir"]
        if not session or not doc_ir:
            raise HTTPException(400, "No active session or document")

        action = session.undo()
        if not action:
            raise HTTPException(400, "Nothing to undo")

        # Restore old text
        old_text = action.data.get("old_text", "")
        block_id = action.block_id
        for page in doc_ir.pages:
            for block in page.text_blocks:
                if block.id == block_id:
                    block.text_verbatim = old_text
                    return {"status": "undone", "block_id": block_id, "restored_text": old_text}

        return {"status": "undone", "block_id": block_id}

    @app.post("/document/redo")
    def redo():
        """Redo the last undone edit."""
        session = state["session"]
        doc_ir = state["document_ir"]
        if not session or not doc_ir:
            raise HTTPException(400, "No active session or document")

        action = session.redo()
        if not action:
            raise HTTPException(400, "Nothing to redo")

        # Re-apply new text
        new_text = action.data.get("new_text", "")
        block_id = action.block_id
        for page in doc_ir.pages:
            for block in page.text_blocks:
                if block.id == block_id:
                    block.text_verbatim = new_text
                    return {"status": "redone", "block_id": block_id, "applied_text": new_text}

        return {"status": "redone", "block_id": block_id}

    # ─── Export ────────────────────────────────────────────────────

    @app.post("/document/export")
    def export_pdf():
        """Export the current document state as a PDF."""
        doc_ir = state["document_ir"]
        session = state["session"]
        if not doc_ir:
            raise HTTPException(404, "No document loaded")

        from src.output_dir import OutputDir

        out = OutputDir(document_name=Path(session.document_path).stem if session else "export")
        # TODO: implement export from IR
        # For now, return the output path
        session.record(ActionType.DOCUMENT_EXPORTED, data={"path": str(out.reconstructed_pdf_path)})
        return {"status": "exported", "path": str(out.reconstructed_pdf_path)}

    # ─── Configuration ─────────────────────────────────────────────

    @app.get("/config/models")
    def get_model_config():
        """Get current model configuration."""
        return {
            "current": state["config"].model_dump(),
            "available": AVAILABLE_MODELS,
        }

    @app.put("/config/models")
    def update_model_config(config: ModelConfig):
        """Update model selection."""
        state["config"] = config
        return {"status": "updated", "config": config.model_dump()}

    @app.get("/config/cost-estimate")
    def get_cost_estimate(page_count: int = 15, tables: int = 2, diagrams: int = 1):
        """Get cost estimate for processing a document."""
        cost = estimate_document_cost(
            page_count, has_tables=tables, has_diagrams=diagrams, config=state["config"]
        )
        return cost

    return app


# Entry point for running directly
app = create_app()
