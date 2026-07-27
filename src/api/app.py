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


class EditRequest(BaseModel):
    """Request body for editing a text block."""
    new_text: str


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

    @app.post("/document/upload")
    async def upload_document(file: UploadFile):
        """Upload a PDF file from the user's machine."""
        import tempfile
        import shutil

        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "File must be a PDF")

        # Save to a temp location
        upload_dir = Path("uploads")
        upload_dir.mkdir(exist_ok=True)
        save_path = upload_dir / file.filename

        with open(save_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # Now open it via the normal pipeline
        return {"saved_path": str(save_path), "filename": file.filename}


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

    @app.get("/document/page/{page_number}/table")
    def get_page_table(page_number: int):
        """Detect and return table structure for a page.

        Uses raw span-level extraction (finer than Document IR blocks)
        to detect and present table structure.
        """
        import fitz

        session = state["session"]
        if not session or not session.document_path:
            raise HTTPException(404, "No document loaded")

        doc = fitz.open(session.document_path)
        if page_number < 1 or page_number > len(doc):
            doc.close()
            raise HTTPException(400, f"Invalid page: {page_number}")

        page = doc[page_number - 1]
        page_height = page.rect.height
        raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        doc.close()

        # Collect individual text spans with positions
        # Exclude header/footer areas (top 70pt and bottom 60pt)
        spans = []
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    chars = span.get("chars", [])
                    text = "".join(c["c"] for c in chars).strip()
                    if text:
                        y0 = span["bbox"][1]
                        # Skip header and footer regions
                        if y0 < 70 or y0 > page_height - 60:
                            continue
                        spans.append({
                            "text": text,
                            "x0": span["bbox"][0],
                            "y0": span["bbox"][1],
                            "x1": span["bbox"][2],
                            "y1": span["bbox"][3],
                        })

        if len(spans) < 6:
            return {"has_table": False}

        # Cluster x positions into columns (30pt tolerance)
        x_values = [s["x0"] for s in spans]
        columns = _cluster_positions(x_values, tolerance=30)

        # Cluster y positions into rows (8pt tolerance)
        y_values = [s["y0"] for s in spans]
        rows = _cluster_positions(y_values, tolerance=8)

        if len(columns) < 2 or len(rows) < 3:
            return {"has_table": False}

        # Build table grid
        table_data = []
        for row_y in rows:
            row_cells = []
            for col_x in columns:
                cell_spans = [
                    s for s in spans
                    if abs(s["x0"] - col_x) < 30 and abs(s["y0"] - row_y) < 8
                ]
                cell_text = " ".join(s["text"] for s in cell_spans)
                row_cells.append({"text": cell_text, "block_id": None})
            table_data.append(row_cells)

        # Filter empty rows
        table_data = [row for row in table_data if any(c["text"] for c in row)]

        if len(table_data) < 2:
            return {"has_table": False}

        return {
            "has_table": True,
            "columns": len(columns),
            "rows": len(table_data),
            "data": table_data,
            "row_y_min": rows[0] if rows else 0,
            "row_y_max": rows[-1] + 20 if rows else 0,
        }

    def _cluster_positions(values: list[float], tolerance: float) -> list[float]:
        """Cluster nearby values into groups, return the median of each group."""
        if not values:
            return []
        sorted_vals = sorted(values)
        clusters: list[list[float]] = [[sorted_vals[0]]]
        for v in sorted_vals[1:]:
            if v - clusters[-1][-1] < tolerance:
                clusters[-1].append(v)
            else:
                clusters.append([v])
        return [
            sorted(c)[len(c) // 2]
            for c in clusters
            if len(c) >= 2
        ]




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

    @app.get("/document/page/{page_number}/analysis")
    def get_page_analysis(page_number: int):
        """Return labeled content analysis for a page.

        Tells the frontend what type of content is on this page
        (table, TOC, text, etc.) and labels header/footer elements.
        """
        from src.page_analysis import analyze_page_content

        session = state["session"]
        if not session or not session.document_path:
            raise HTTPException(404, "No document loaded")
        return analyze_page_content(session.document_path, page_number)


    @app.get("/document/requirements")
    def get_requirements():
        """Extract and return all candidate requirements from the document."""
        doc_ir = state["document_ir"]
        if not doc_ir:
            raise HTTPException(404, "No document loaded")

        from src.requirements import extract_requirements

        reqs = extract_requirements(doc_ir)
        return {
            "count": len(reqs),
            "requirements": [
                {
                    "text": r.text[:200],
                    "page": r.page,
                    "block_id": r.block_id,
                    "normative_term": r.normative_term,
                    "section": r.section,
                    "requirement_id": r.requirement_id,
                    "confidence": r.confidence,
                    "has_tbd": r.has_tbd,
                }
                for r in reqs
            ],
        }


        page = doc[page_number - 1]
        pix = page.get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        doc.close()

        return Response(content=img_bytes, media_type="image/png")

    # ─── Editing ───────────────────────────────────────────────────


    @app.put("/document/table-cell")
    def edit_table_cell(page: int, old_text: str, new_text: str):
        """Edit a table cell by finding and replacing text in the IR.

        Since table cells don't have direct block_ids, we find the block
        containing the old text and replace it.
        """
        doc_ir = state["document_ir"]
        if not doc_ir:
            raise HTTPException(404, "No document loaded")

        if page < 1 or page > doc_ir.page_count:
            raise HTTPException(400, f"Invalid page: {page}")

        page_info = doc_ir.pages[page - 1]
        for block in page_info.text_blocks:
            if old_text in block.text_verbatim:
                block.text_verbatim = block.text_verbatim.replace(old_text, new_text)

                session = state["session"]
                if session:
                    session.record(
                        ActionType.BLOCK_EDITED,
                        page=page,
                        block_id=block.id,
                        data={"old_text": old_text, "new_text": new_text},
                    )

                return {"status": "updated", "block_id": block.id}

        raise HTTPException(404, f"Text not found on page {page}")

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

        old_text = action.data.get("old_text", "")
        new_text = action.data.get("new_text", "")
        block_id = action.block_id

        # Find the block and reverse the edit
        for page in doc_ir.pages:
            for block in page.text_blocks:
                if block_id and block.id == block_id:
                    # Replace new_text back to old_text within the block
                    if new_text and new_text in block.text_verbatim:
                        block.text_verbatim = block.text_verbatim.replace(new_text, old_text)
                    else:
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
        old_text = action.data.get("old_text", "")
        new_text = action.data.get("new_text", "")
        block_id = action.block_id
        for page in doc_ir.pages:
            for block in page.text_blocks:
                if block_id and block.id == block_id:
                    if old_text and old_text in block.text_verbatim:
                        block.text_verbatim = block.text_verbatim.replace(old_text, new_text)
                    else:
                        block.text_verbatim = new_text
                    return {"status": "redone", "block_id": block_id, "applied_text": new_text}

        return {"status": "redone", "block_id": block_id}

    # ─── Export ────────────────────────────────────────────────────

    @app.post("/document/export")
    def export_pdf():
        """Export the current document state as a PDF (with edits applied)."""
        doc_ir = state["document_ir"]
        session = state["session"]
        if not doc_ir:
            raise HTTPException(404, "No document loaded")

        from src.output_dir import OutputDir
        from src.rendering.ir_renderer import render_ir_to_pdf

        out = OutputDir(
            document_name=Path(session.document_path).stem if session else "export"
        )

        result = render_ir_to_pdf(
            doc_ir, session.document_path, out.reconstructed_pdf_path
        )

        if session:
            session.record(
                ActionType.DOCUMENT_EXPORTED, data={"path": str(result)}
            )

        return {"status": "exported", "path": str(result)}

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
