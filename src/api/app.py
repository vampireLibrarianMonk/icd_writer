"""FastAPI application for the ICD Editor backend.

Provides REST endpoints for document loading, editing, rendering,
and session management. WebSocket support for real-time progress.
"""

from __future__ import annotations

import os
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


class TableRebuildRequest(BaseModel):
    """Request body for rebuilding a table zone with new data."""
    y_min: float
    y_max: float
    data: list[list[str]]  # 2D array: rows x columns of cell text


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
    state = {"session": None, "document_ir": None, "config": ModelConfig(), "cost_ledger": [], "working_copy_path": None, "font_cache": None}

    def _get_source_path() -> str:
        """Return the working copy path if available, otherwise the original."""
        if state["working_copy_path"] and Path(state["working_copy_path"]).exists():
            return state["working_copy_path"]
        session = state["session"]
        if session and session.document_path:
            return session.document_path
        return ""

    def _insert_text_with_font(page, point, text: str, font_name: str, font_size: float,
                               bold: bool = False, italic: bool = False, color=(0, 0, 0)):
        """Insert text using the best available font (extracted > system > base-14).

        Uses the font cache to get the original document's font when possible.
        Falls back gracefully to system fonts then base-14.
        """
        import tempfile
        from src.rendering.font_cache import FontCache

        cache: FontCache | None = state.get("font_cache")
        if cache:
            font_obj, fontname, fontbuffer = cache.get_font(font_name, bold, italic)
        else:
            font_obj, fontname, fontbuffer = None, None, None

        if fontbuffer:
            # Write font buffer to a temp file for insert_text
            import os
            tmp_dir = Path("output")
            tmp_dir.mkdir(exist_ok=True)
            tmp_font = tmp_dir / ".tmp_font.ttf"
            tmp_font.write_bytes(fontbuffer)
            try:
                page.insert_text(point, text, fontfile=str(tmp_font),
                                 fontsize=font_size, color=color)
            except Exception:
                # If the extracted font fails (subset issue), fall back to base-14
                from src.rendering.page_patch import _get_pymupdf_fontname
                builtin = _get_pymupdf_fontname(font_name, bold, italic)
                page.insert_text(point, text, fontname=builtin,
                                 fontsize=font_size, color=color)
            finally:
                tmp_font.unlink(missing_ok=True)
        elif fontname:
            page.insert_text(point, text, fontname=fontname,
                             fontsize=font_size, color=color)
        else:
            # Ultimate fallback
            from src.rendering.page_patch import _get_pymupdf_fontname
            builtin = _get_pymupdf_fontname(font_name, bold, italic)
            page.insert_text(point, text, fontname=builtin,
                             fontsize=font_size, color=color)

    def _get_text_width(text: str, font_name: str, font_size: float,
                        bold: bool = False, italic: bool = False) -> float:
        """Calculate text width using the best available font."""
        from src.rendering.font_cache import FontCache

        cache: FontCache | None = state.get("font_cache")
        if cache:
            return cache.text_width(text, font_name, font_size, bold, italic)
        # Fallback estimate
        return len(text) * font_size * 0.5

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

    @app.post("/session/save-as")
    def save_session_as(filename: str = "session"):
        """Save the current session to a named file.

        Writes a .icd-session JSON file that can be loaded later to restore
        all edits and undo state.
        """
        session = state["session"]
        if not session:
            raise HTTPException(404, "No active session")

        sessions_dir = Path("sessions")
        sessions_dir.mkdir(exist_ok=True)

        # Ensure filename has correct extension
        if not filename.endswith(".icd-session"):
            filename = filename + ".icd-session"

        save_path = sessions_dir / filename
        session.save_journal(save_path)
        return {"status": "saved", "path": str(save_path), "filename": filename}

    @app.post("/session/load")
    def load_session(filename: str):
        """Load a previously saved session file, restoring all edits.

        Opens the referenced document and replays all BLOCK_EDITED actions
        to reconstruct the Document IR state.
        """
        from src.api.session import Session as SessionModel

        sessions_dir = Path("sessions")
        if not filename.endswith(".icd-session"):
            filename = filename + ".icd-session"

        load_path = sessions_dir / filename
        if not load_path.exists():
            raise HTTPException(404, f"Session file not found: {filename}")

        # Load the session journal
        loaded = SessionModel.load_journal(load_path)

        # Open the document referenced in the session
        doc_path = loaded.document_path
        if not doc_path or not Path(doc_path).exists():
            raise HTTPException(400, f"Document not found: {doc_path}")

        from src.pipeline import process_pdf

        document_ir = process_pdf(Path(doc_path))
        state["document_ir"] = document_ir
        state["session"] = loaded

        # Replay all BLOCK_EDITED actions to reconstruct IR state
        for action in loaded.actions:
            if action.action_type != ActionType.BLOCK_EDITED:
                continue
            block_id = action.block_id
            new_text = action.data.get("new_text", "")
            if not block_id or not new_text:
                continue

            # Find the block and apply the edit
            for page in document_ir.pages:
                for block in page.text_blocks:
                    if block.id == block_id:
                        block.text_verbatim = new_text
                        break

        return {
            "status": "loaded",
            "filename": filename,
            "document": doc_path,
            "edit_count": loaded.edit_count,
            "actions": len(loaded.actions),
        }

    @app.get("/session/journal")
    def get_session_journal():
        """Return the full session action journal for the Session tab.

        Each entry includes timestamp, action type, page, block, and a
        human-readable summary.
        """
        session = state["session"]
        if not session:
            raise HTTPException(404, "No active session")

        entries = []
        for action in session.actions:
            summary = ""
            if action.action_type == ActionType.DOCUMENT_OPENED:
                summary = f"Opened {action.data.get('path', '').split('/')[-1]}"
            elif action.action_type == ActionType.BLOCK_EDITED:
                page_str = f"page {action.page}" if action.page else ""
                block_str = action.block_id or ""
                old_text = action.data.get("old_text", "")
                new_text = action.data.get("new_text", "")
                # Show a preview of what changed
                if len(old_text) < 50 and len(new_text) < 50:
                    summary = f"Changed \"{old_text[:30]}\" → \"{new_text[:30]}\" on {page_str}"
                else:
                    summary = f"Edited {block_str} on {page_str}"
            elif action.action_type == ActionType.DOCUMENT_SAVED:
                summary = "Session saved"
            elif action.action_type == ActionType.DOCUMENT_EXPORTED:
                summary = "PDF exported"
            elif action.action_type == ActionType.UNDO:
                undone_id = action.data.get("undone_action_id", "")
                # Find the undone action to show what was undone
                undone_action = next((a for a in session.actions if a.id == undone_id), None)
                if undone_action and undone_action.block_id:
                    page_str = f"page {undone_action.page}" if undone_action.page else ""
                    summary = f"Undo edit on {page_str} ({undone_action.block_id})"
                else:
                    summary = "Undo"
            elif action.action_type == ActionType.REDO:
                redone_id = action.data.get("redone_action_id", "")
                redone_action = next((a for a in session.actions if a.id == redone_id), None)
                if redone_action and redone_action.block_id:
                    page_str = f"page {redone_action.page}" if redone_action.page else ""
                    summary = f"Redo edit on {page_str} ({redone_action.block_id})"
                else:
                    summary = "Redo"
            else:
                summary = action.action_type.value

            entries.append({
                "id": action.id,
                "timestamp": action.timestamp.isoformat(),
                "action_type": action.action_type.value,
                "page": action.page,
                "block_id": action.block_id,
                "summary": summary,
            })

        return {
            "session_id": session.session_id,
            "document": session.document_path,
            "entries": entries,
            "edit_count": session.edit_count,
            "undo_available": len(session.undo_stack) > 0,
            "redo_available": len(session.redo_stack) > 0,
        }

    @app.get("/session/files")
    def list_session_files():
        """List available session files that can be loaded."""
        sessions_dir = Path("sessions")
        if not sessions_dir.exists():
            return {"files": []}

        files = []
        for f in sorted(sessions_dir.glob("*.icd-session")):
            files.append({
                "filename": f.name,
                "size_bytes": f.stat().st_size,
                "modified": f.stat().st_mtime,
            })
        return {"files": files}

    # ─── Cost Tracking ─────────────────────────────────────────────

    @app.get("/session/costs")
    def get_session_costs():
        """Return the current cost ledger (persists across session restarts)."""
        from src.api.session import CostEntry

        ledger = state["cost_ledger"]
        total = sum(e["cost_usd"] for e in ledger)

        # Summarize by operation
        by_op: dict[str, float] = {}
        for e in ledger:
            by_op[e["operation"]] = by_op.get(e["operation"], 0.0) + e["cost_usd"]

        return {
            "total_cost_usd": round(total, 6),
            "entry_count": len(ledger),
            "entries": ledger,
            "summary": {k: round(v, 6) for k, v in by_op.items()},
        }

    @app.get("/session/costs/export")
    def export_session_costs():
        """Export the cost ledger as a downloadable CSV."""
        from fastapi.responses import Response

        ledger = state["cost_ledger"]
        session = state["session"]

        lines = [
            "timestamp,operation,description,model,tokens_in,tokens_out,chunks,cost_usd"
        ]
        for e in ledger:
            desc = e["description"].replace(",", ";")
            lines.append(
                f"{e['timestamp']},{e['operation']},{desc},{e['model']},"
                f"{e['tokens_in']},{e['tokens_out']},{e['chunks_processed']},{e['cost_usd']:.6f}"
            )
        total = sum(e["cost_usd"] for e in ledger)
        lines.append("")
        lines.append(f"# Total:,,,,,,,{total:.6f}")
        if session:
            lines.append(f"# Session:,{session.session_id}")
            lines.append(f"# Started:,{session.started_at.isoformat()}")

        csv_content = "\n".join(lines)
        filename = f"cost_receipt_{session.session_id if session else 'nosession'}.csv"
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    def _record_cost(operation: str, description: str, model: str,
                     cost_usd: float, tokens_in: int = 0, tokens_out: int = 0,
                     chunks_processed: int = 0) -> None:
        """Record a cost entry to the app-level ledger."""
        from datetime import datetime, timezone
        state["cost_ledger"].append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "description": description,
            "model": model,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "chunks_processed": chunks_processed,
            "cost_usd": cost_usd,
        })

    # ─── Document ──────────────────────────────────────────────────

    @app.post("/document/upload")
    async def upload_document(file: UploadFile):
        """Upload a PDF file from the user's machine (deduplicated)."""
        import hashlib
        import shutil

        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "File must be a PDF")

        # Read content for hashing
        content = await file.read()
        file_hash = hashlib.sha256(content).hexdigest()

        # Check if this file already exists anywhere
        for scan_dir in [Path("icds/digital"), Path("uploads")]:
            if not scan_dir.exists():
                continue
            for existing_pdf in scan_dir.glob("*.pdf"):
                existing_hash = hashlib.sha256(existing_pdf.read_bytes()).hexdigest()
                if existing_hash == file_hash:
                    # Already exists — return path to existing copy
                    return {
                        "saved_path": str(existing_pdf),
                        "filename": existing_pdf.name,
                        "duplicate": True,
                    }

        # New file — save to uploads/
        upload_dir = Path("uploads")
        upload_dir.mkdir(exist_ok=True)
        save_path = upload_dir / file.filename

        with open(save_path, "wb") as f:
            f.write(content)

        return {"saved_path": str(save_path), "filename": file.filename, "duplicate": False}

    # ─── Document Ingestion Pipeline ───────────────────────────────

    # In-memory ingestion status tracker
    ingest_status: dict[str, dict] = {}

    @app.post("/document/ingest")
    async def ingest_document(file: UploadFile):
        """Upload and fully ingest a PDF: extract → index → detect TBDs.

        Returns an ingest_id for polling progress via /document/ingest/status.
        The pipeline runs in a background thread.
        """
        import hashlib
        import uuid
        import threading

        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(400, "File must be a PDF")

        content = await file.read()
        file_hash = hashlib.sha256(content).hexdigest()
        ingest_id = str(uuid.uuid4())[:8]

        # Check for duplicate
        existing_path = None
        for scan_dir in [Path("icds/digital"), Path("uploads")]:
            if not scan_dir.exists():
                continue
            for existing_pdf in scan_dir.glob("*.pdf"):
                existing_hash = hashlib.sha256(existing_pdf.read_bytes()).hexdigest()
                if existing_hash == file_hash:
                    existing_path = existing_pdf
                    break
            if existing_path:
                break

        if existing_path:
            pdf_path = existing_path
        else:
            upload_dir = Path("uploads")
            upload_dir.mkdir(exist_ok=True)
            pdf_path = upload_dir / file.filename
            with open(pdf_path, "wb") as f:
                f.write(content)

        # Initialize status
        ingest_status[ingest_id] = {
            "ingest_id": ingest_id,
            "filename": file.filename,
            "pdf_path": str(pdf_path),
            "status": "uploading",
            "step": 1,
            "total_steps": 5,
            "message": "File received, starting extraction...",
            "progress_pct": 10,
            "pages": 0,
            "text_blocks": 0,
            "chunks_indexed": 0,
            "tbd_count": 0,
            "tbr_count": 0,
            "error": None,
            "done": False,
        }

        def run_pipeline():
            """Execute the full ingestion pipeline in background."""
            try:
                status = ingest_status[ingest_id]

                # Step 1: Extract Document IR
                status.update({"status": "extracting", "step": 2, "message": "Extracting text and structure from PDF...", "progress_pct": 20})
                from src.pipeline import process_pdf
                from src.serialization import to_yaml

                document_ir = process_pdf(pdf_path)
                ir_path = Path("output") / f"{pdf_path.stem}_document_ir.yaml"
                ir_path.parent.mkdir(parents=True, exist_ok=True)
                to_yaml(document_ir, ir_path)

                page_count = document_ir.page_count
                total_blocks = sum(len(p.text_blocks) for p in document_ir.pages)
                status.update({
                    "pages": page_count,
                    "text_blocks": total_blocks,
                    "message": f"Extracted {page_count} pages, {total_blocks} text blocks. Indexing...",
                    "progress_pct": 40,
                })

                # Step 2: Index into OpenSearch
                status.update({"status": "indexing", "step": 3, "message": "Generating embeddings and indexing into OpenSearch...", "progress_pct": 50})
                from src.search.config import SearchConfig, ALL_CONFIGS
                from src.search.pipeline import SearchPipeline

                search_config = SearchConfig(
                    opensearch_host=os.environ.get("OPENSEARCH_HOST", "localhost"),
                    opensearch_port=int(os.environ.get("OPENSEARCH_PORT", "9200")),
                    opensearch_scheme=os.environ.get("OPENSEARCH_SCHEME", "http"),
                    aws_region="us-east-1",
                )
                pipeline = SearchPipeline(config=search_config, region="us-east-1")

                # Index per-config with progress updates
                total_configs = len(ALL_CONFIGS)
                index_results = {}
                total_chunks_all_configs = 0

                for i, cfg in enumerate(ALL_CONFIGS):
                    config_base_pct = 50 + int((i / total_configs) * 25)
                    config_pct_range = 25 // total_configs  # pct allocated per config
                    status.update({
                        "message": f"Indexing config {i + 1}/{total_configs}: {cfg.name} (chunking...)",
                        "progress_pct": config_base_pct,
                    })

                    def make_progress_cb(base_pct, pct_range, config_name):
                        """Create a closure for per-chunk progress updates."""
                        def cb(embedded, total):
                            chunk_pct = base_pct + int((embedded / total) * pct_range)
                            status.update({
                                "message": f"Indexing {config_name}: embedding chunk {embedded}/{total}",
                                "progress_pct": chunk_pct,
                            })
                        return cb

                    progress_cb = make_progress_cb(config_base_pct, config_pct_range, cfg.name)
                    result = pipeline.ingest_document(ir_path, configs=[cfg], progress_callback=progress_cb)
                    index_results.update(result)
                    chunks_this_config = sum(result.values())
                    total_chunks_all_configs += chunks_this_config

                    # Record cost for this config's embedding
                    if chunks_this_config > 0:
                        est_tokens = chunks_this_config * 50
                        cost_per_1k = cfg.embedding_config.cost_per_1k_tokens
                        est_cost = (est_tokens / 1000) * cost_per_1k
                        _record_cost(
                            operation="embedding",
                            description=f"Upload & Index: {pdf_path.name} ({cfg.name})",
                            model=cfg.embedding_config.provider.value,
                            cost_usd=est_cost,
                            tokens_in=est_tokens,
                            chunks_processed=chunks_this_config,
                        )

                total_chunks = total_chunks_all_configs
                status.update({
                    "chunks_indexed": total_chunks,
                    "message": f"Indexed {total_chunks} chunks across {total_configs} configurations.",
                    "progress_pct": 75,
                })

                # Step 3: Detect TBDs/TBRs
                status.update({"status": "detecting_tbds", "step": 4, "message": "Scanning for TBD/TBR items...", "progress_pct": 85})
                from src.search.tbd_dashboard import TBDDashboard

                dashboard = TBDDashboard(search_config=search_config, region="us-east-1")
                tbd_count_new = dashboard.ingest_document(ir_path)
                dashboard.save_state()

                # Count TBDs vs TBRs from the dashboard items
                tbd_count = 0
                tbr_count = 0
                for item in dashboard._items.values():
                    doc_stem = pdf_path.stem.lower()
                    item_doc = item.document_title.lower()
                    if doc_stem in item_doc or item_doc in doc_stem or doc_stem[:10] in item_doc:
                        if item.item_type == "TBD":
                            tbd_count += 1
                        elif item.item_type == "TBR":
                            tbr_count += 1

                status.update({
                    "tbd_count": tbd_count,
                    "tbr_count": tbr_count,
                    "progress_pct": 95,
                })

                # Step 4: Done
                status.update({
                    "status": "done",
                    "step": 5,
                    "message": f"Complete! {page_count} pages, {total_chunks} chunks indexed, {tbd_count} TBDs, {tbr_count} TBRs.",
                    "progress_pct": 100,
                    "done": True,
                })

            except Exception as e:
                ingest_status[ingest_id].update({
                    "status": "error",
                    "message": f"Pipeline failed: {str(e)}",
                    "error": str(e),
                    "done": True,
                })

        # Launch pipeline in background thread
        thread = threading.Thread(target=run_pipeline, daemon=True)
        thread.start()

        return {"ingest_id": ingest_id, "status": "started", "filename": file.filename}

    @app.get("/document/ingest/status/{ingest_id}")
    def get_ingest_status(ingest_id: str):
        """Poll ingestion progress for a given ingest_id."""
        status = ingest_status.get(ingest_id)
        if not status:
            raise HTTPException(404, f"No ingestion found with id: {ingest_id}")
        return status

    @app.get("/documents")
    def list_documents():
        """List available PDF documents that have been indexed."""
        import hashlib
        from pathlib import Path

        seen_hashes: dict[str, dict] = {}  # hash -> doc info
        scan_dirs = [
            Path("icds/digital"),
            Path("uploads"),
        ]

        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue
            for pdf in sorted(scan_dir.glob("*.pdf")):
                # Only include documents that have been indexed
                ir_path = Path("output") / f"{pdf.stem}_document_ir.yaml"
                if not ir_path.exists():
                    continue

                # Compute SHA-256 for deduplication
                h = hashlib.sha256(pdf.read_bytes()).hexdigest()
                if h in seen_hashes:
                    existing = seen_hashes[h]
                    if "icds/" in existing["path"]:
                        continue

                # Get PDF title from metadata
                import fitz as _fitz
                _doc = _fitz.open(str(pdf))
                pdf_title = _doc.metadata.get("title", "") or ""
                _doc.close()

                seen_hashes[h] = {
                    "path": str(pdf),
                    "filename": pdf.name,
                    "stem": pdf.stem,
                    "title": pdf_title,
                    "indexed": True,
                    "size_bytes": pdf.stat().st_size,
                    "sha256": h,
                }

        docs = list(seen_hashes.values())
        docs.sort(key=lambda d: d["filename"])
        return {"documents": docs}

    @app.delete("/document/{doc_stem}")
    def delete_document(doc_stem: str):
        """Remove a document completely: OpenSearch indices, IR file, TBD items, and optionally the PDF.

        Args:
            doc_stem: The filename stem (e.g., '20130010957' for '20130010957.pdf')
        """
        import hashlib
        from src.search.config import SearchConfig, ALL_CONFIGS
        from src.search.indexing import IndexManager
        from src.search.tbd_dashboard import TBDDashboard

        search_config = SearchConfig(
            opensearch_host=os.environ.get("OPENSEARCH_HOST", "localhost"),
            opensearch_port=int(os.environ.get("OPENSEARCH_PORT", "9200")),
            opensearch_scheme=os.environ.get("OPENSEARCH_SCHEME", "http"),
            aws_region="us-east-1",
        )

        # Find the PDF file
        pdf_path = None
        pdf_hash = None
        for scan_dir in [Path("icds/digital"), Path("uploads")]:
            candidate = scan_dir / f"{doc_stem}.pdf"
            if candidate.exists():
                pdf_path = candidate
                pdf_hash = hashlib.sha256(candidate.read_bytes()).hexdigest()
                break

        if not pdf_path:
            raise HTTPException(404, f"Document not found: {doc_stem}")

        results = {
            "document": doc_stem,
            "indices_cleared": 0,
            "chunks_deleted": 0,
            "ir_deleted": False,
            "tbd_items_removed": 0,
            "pdf_deleted": False,
        }

        # 1. Remove from all OpenSearch indices
        if pdf_hash:
            index_manager = IndexManager(search_config)
            for config in ALL_CONFIGS:
                index_name = config.index_name
                try:
                    deleted = index_manager.delete_document(index_name, pdf_hash)
                    results["chunks_deleted"] += deleted
                    if deleted > 0:
                        results["indices_cleared"] += 1
                except Exception:
                    pass  # Index may not exist yet

        # 2. Delete the Document IR file
        ir_path = Path("output") / f"{doc_stem}_document_ir.yaml"
        if ir_path.exists():
            ir_path.unlink()
            results["ir_deleted"] = True

        # 3. Remove TBD items for this document
        try:
            dashboard = TBDDashboard(search_config=search_config, region="us-east-1")
            items_to_remove = []
            for item_id, item in dashboard._items.items():
                item_doc = item.document_title.lower()
                if doc_stem.lower() in item_doc or item_doc in doc_stem.lower():
                    items_to_remove.append(item_id)
            for item_id in items_to_remove:
                del dashboard._items[item_id]
            results["tbd_items_removed"] = len(items_to_remove)
            if items_to_remove:
                dashboard.save_state()
        except Exception:
            pass

        # 4. Delete PDF if it's in uploads/ (don't delete from icds/digital — those are source-controlled)
        if pdf_path and "uploads" in str(pdf_path):
            pdf_path.unlink()
            results["pdf_deleted"] = True

        # 5. If the currently loaded document is the one being deleted, clear state
        session = state["session"]
        if session and session.document_path and doc_stem in session.document_path:
            state["document_ir"] = None
            state["session"] = None

        return results

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

        # Create a working copy so the original is never mutated
        import shutil
        output_dir = Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)
        working_copy = output_dir / f".working_{path.name}"
        shutil.copy2(str(path), str(working_copy))
        state["working_copy_path"] = str(working_copy)

        # Build font cache from the source PDF for pixel-accurate text insertion
        from src.rendering.font_cache import FontCache
        state["font_cache"] = FontCache.from_pdf(str(path))

        # Check for related versions
        from src.version_diff import detect_families, normalize_stem
        related_versions = []
        current_stem = normalize_stem(path.name)
        families = detect_families()
        for family in families:
            if family.base_name == current_stem:
                related_versions = [
                    {"path": v.path, "filename": v.filename, "revision": v.revision, "doc_type": v.doc_type, "page_count": v.page_count}
                    for v in family.versions
                    if str(Path(v.path).resolve()) != str(path.resolve())
                ]
                break

        return {
            "status": "ready",
            "method": method,
            "pages": document_ir.page_count,
            "text_blocks": sum(len(p.text_blocks) for p in document_ir.pages),
            "related_versions": related_versions,
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

        # Create a working copy so the original is never mutated
        import shutil
        output_dir = Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)
        working_copy = output_dir / f".working_{path.name}"
        shutil.copy2(str(path), str(working_copy))
        state["working_copy_path"] = str(working_copy)

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
    def get_page_table(page_number: int, y_min: float = 0, y_max: float = 9999):
        """Detect and return table structure for a page (or zone).

        Uses raw span-level extraction. Pass y_min/y_max to filter
        to a specific table zone on pages with multiple tables.
        """
        import fitz

        session = state["session"]
        if not session or not session.document_path:
            raise HTTPException(404, "No document loaded")

        doc = fitz.open(_get_source_path())
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
                        # Filter to zone if specified
                        if y0 < y_min or y0 > y_max:
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

        # Apply any pending edits from the session to the span text
        # (so the panel shows current values, not stale PDF text)
        if session and session.undo_stack:
            from src.rendering.page_patch import get_page_edits_from_session
            doc_ir = state["document_ir"]
            if doc_ir:
                edits = get_page_edits_from_session(session, doc_ir, page_number)
                for edit in edits:
                    old_t = edit.get("old_text", "")
                    new_t = edit.get("new_text", "")
                    if old_t and new_t and old_t != new_t:
                        for s in spans:
                            if old_t in s["text"]:
                                s["text"] = s["text"].replace(old_t, new_t)

        # Merge adjacent spans on the same line (e.g., "Temperature," + "°" + "C")
        # Group spans by y-row first (5pt tolerance), then within each row
        # merge consecutive spans where x-gap < 15pt
        spans.sort(key=lambda s: (s["y0"], s["x0"]))

        # Step 1: Group into y-rows
        y_rows: list[list[dict]] = []
        for s in spans:
            placed = False
            for row in y_rows:
                if abs(s["y0"] - row[0]["y0"]) < 5:
                    row.append(s)
                    placed = True
                    break
            if not placed:
                y_rows.append([s])

        # Step 2: Within each row, sort by x and merge adjacent spans
        merged_spans = []
        for row in y_rows:
            row.sort(key=lambda s: s["x0"])
            row_merged: list[dict] = []
            for s in row:
                if row_merged:
                    prev = row_merged[-1]
                    x_gap = s["x0"] - prev["x1"]
                    if x_gap < 15:
                        prev["text"] = prev["text"] + s["text"]
                        prev["x1"] = max(prev["x1"], s["x1"])
                        prev["y1"] = max(prev["y1"], s["y1"])
                        continue
                row_merged.append(dict(s))
            merged_spans.extend(row_merged)
        spans = merged_spans

        if len(spans) < 4:
            return {"has_table": False}

        # Cluster x positions into columns (30pt tolerance)
        x_values = [s["x0"] for s in spans]
        columns = _cluster_positions(x_values, tolerance=30)

        # Cluster y positions into rows (8pt tolerance)
        y_values = [s["y0"] for s in spans]
        rows = _cluster_positions(y_values, tolerance=8)

        if len(columns) < 2 or len(rows) < 3:
            return {"has_table": False}

        # Build table grid — assign each span to its nearest column and row
        table_data = []
        for row_y in rows:
            row_cells = [{"text": "", "block_id": None} for _ in columns]
            row_spans = [s for s in spans if abs(s["y0"] - row_y) < 8]
            for s in row_spans:
                # Find nearest column
                best_col = 0
                best_dist = abs(s["x0"] - columns[0])
                for ci, col_x in enumerate(columns):
                    dist = abs(s["x0"] - col_x)
                    if dist < best_dist:
                        best_dist = dist
                        best_col = ci
                # Append text to that column cell
                if row_cells[best_col]["text"]:
                    row_cells[best_col]["text"] += " " + s["text"]
                else:
                    row_cells[best_col]["text"] = s["text"]
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

    @app.post("/document/page/{page_number}/table-rebuild")
    def rebuild_table(page_number: int, req: TableRebuildRequest):
        """Rebuild a table zone with the provided cell data.

        Redacts the entire table zone on the working copy, then redraws
        all rows, columns, borders, and text from scratch using the
        structured data provided.

        This is the atomic "Apply Table Changes" operation — the frontend
        edits the table as structured data, then sends the full table here.
        """
        import fitz

        session = state["session"]
        doc_ir = state["document_ir"]
        if not session or not session.document_path:
            raise HTTPException(404, "No document loaded")

        source_path = _get_source_path()
        doc = fitz.open(source_path)
        if page_number < 1 or page_number > len(doc):
            doc.close()
            raise HTTPException(400, f"Invalid page: {page_number}")

        page = doc[page_number - 1]

        if not req.data or len(req.data) < 1:
            doc.close()
            raise HTTPException(400, "Table data must have at least one row")

        num_cols = max(len(row) for row in req.data)
        num_rows = len(req.data)

        # Step 1: Analyze existing table geometry from HORIZONTAL borders only
        # (Vertical borders are unreliable after rebuilds — we derive columns from width)
        drawings = page.get_drawings()
        raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)

        # Find horizontal borders in the zone (these span the full table width)
        h_lines = []
        for d in drawings:
            rect = d.get("rect")
            if not rect:
                continue
            r = fitz.Rect(rect)
            if r.height < 3 and r.width > 20:
                if req.y_min - 10 <= r.y0 <= req.y_max + 10:
                    h_lines.append((r.y0, r.x0, r.x1))  # y, left-x, right-x

        if len(h_lines) < 2:
            doc.close()
            raise HTTPException(400, "Could not detect table borders in the zone")

        # Table bounds from horizontal lines
        h_ys = sorted(set(round(y, 1) for y, _, _ in h_lines))
        # Table width from the widest horizontal line
        table_x0 = min(x0 for _, x0, _ in h_lines)
        table_x1 = max(x1 for _, _, x1 in h_lines)

        # Filter out page-width lines (likely page frame, not table)
        page_width = page.rect.width
        if table_x1 - table_x0 > page_width * 0.8:
            # Too wide — use text extent instead
            text_x0, text_x1 = None, None
            for block in raw.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        bbox = span["bbox"]
                        if min(h_ys) <= bbox[1] <= max(h_ys):
                            if text_x0 is None or bbox[0] < text_x0:
                                text_x0 = bbox[0]
                            if text_x1 is None or bbox[2] > text_x1:
                                text_x1 = bbox[2]
            if text_x0 is not None:
                table_x0 = text_x0 - 6
                table_x1 = text_x1 + 6

        table_y0 = min(h_ys)
        original_table_y1 = max(h_ys)

        # Determine row height from existing table
        h_gaps = [h_ys[i+1] - h_ys[i] for i in range(len(h_ys) - 1)]
        row_height = sum(h_gaps) / len(h_gaps) if h_gaps else 14.0

        # Get font info from existing table spans
        font_name = "TimesNewRoman"
        font_size = 12.0
        text_color = (0, 0, 0)
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    bbox = span["bbox"]
                    if req.y_min <= bbox[1] <= req.y_max:
                        font_name = span.get("font", "TimesNewRoman")
                        font_size = span.get("size", 12.0)
                        # Convert integer color to RGB tuple
                        raw_color = span.get("color", 0)
                        if isinstance(raw_color, int) and raw_color > 0:
                            r = ((raw_color >> 16) & 0xFF) / 255.0
                            g = ((raw_color >> 8) & 0xFF) / 255.0
                            b = (raw_color & 0xFF) / 255.0
                            text_color = (r, g, b)
                        break

        # Step 2: Compute new table dimensions
        new_table_y1 = table_y0 + row_height * num_rows
        height_delta = new_table_y1 - original_table_y1

        # Column positions: equal-width division of the table
        # This is stable across rebuilds (no dependency on detected vertical borders)
        col_width = (table_x1 - table_x0) / num_cols
        col_xs = [table_x0 + i * col_width for i in range(num_cols + 1)]

        # Step 3: Backup the working copy before modification (for undo)
        import shutil
        backup_path = source_path + ".undo_backup"
        doc.close()
        shutil.copy2(source_path, backup_path)
        doc = fitz.open(source_path)
        page = doc[page_number - 1]

        # Step 4: Redact the table zone (text + borders inside the grid)
        # Start redaction just below the caption (which ends ~2pt above table_y0)
        # but above the first data row. This preserves the caption title.
        redact_y_start = table_y0 - 0.5  # Just above the top border line
        redact_rect = fitz.Rect(table_x0 - 2, redact_y_start, table_x1 + 2, original_table_y1 + 2)
        page.add_redact_annot(redact_rect, fill=(1, 1, 1))
        page.apply_redactions()

        # Step 5: If new table is taller/shorter, shift content below
        if height_delta > 0.5:
            _shift_below(page, raw, original_table_y1, height_delta)
        elif height_delta < -0.5:
            _shift_below(page, raw, original_table_y1, height_delta)  # negative shift = move up

        # Step 6: Draw new table borders
        border_w = 0.48

        # Horizontal borders (top of each row + bottom)
        for i in range(num_rows + 1):
            y = table_y0 + i * row_height
            page.draw_rect(
                fitz.Rect(table_x0, y, table_x1, y + border_w),
                fill=(0, 0, 0), color=None, width=0,
            )

        # Vertical borders at original column positions
        for x in col_xs:
            page.draw_rect(
                fitz.Rect(x, table_y0, x + border_w, new_table_y1),
                fill=(0, 0, 0), color=None, width=0,
            )

        # Step 7: Insert cell text (using extracted font when available)
        for row_idx, row_data in enumerate(req.data):
            for col_idx, cell_text in enumerate(row_data):
                if col_idx >= num_cols:
                    break
                if not cell_text.strip():
                    continue

                # Cell center
                cell_x0 = col_xs[col_idx]
                cell_x1 = col_xs[col_idx + 1]
                cell_center_x = (cell_x0 + cell_x1) / 2
                baseline_y = table_y0 + row_idx * row_height + row_height * 0.65

                # Center text horizontally using real font metrics
                text_width = _get_text_width(cell_text, font_name, font_size)
                insert_x = cell_center_x - text_width / 2

                _insert_text_with_font(
                    page, fitz.Point(insert_x, baseline_y),
                    cell_text, font_name, font_size, color=text_color,
                )

        # Step 7: Save
        doc.save(source_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        doc.close()

        # Step 8: Update Document IR
        if doc_ir and page_number <= len(doc_ir.pages):
            page_info = doc_ir.pages[page_number - 1]
            for block in page_info.text_blocks:
                if (block.bbox.y0 >= req.y_min - 20
                        and block.bbox.y1 <= req.y_max + 20):
                    old_text = block.text_verbatim
                    new_text = "\n".join(
                        "\t".join(row) for row in req.data
                    )
                    block.text_verbatim = new_text
                    block.bbox.y1 = new_table_y1

                    session.record(
                        ActionType.BLOCK_EDITED,
                        page=page_number,
                        block_id=block.id,
                        data={
                            "operation": "table_rebuild",
                            "old_text": old_text,
                            "new_text": new_text,
                        },
                    )
                    break

        return {
            "status": "rebuilt",
            "page": page_number,
            "rows": num_rows,
            "columns": num_cols,
            "height_delta": round(height_delta, 1),
        }

    def _shift_below(page, raw, y_threshold: float, shift_amount: float):
        """Shift text content below y_threshold by shift_amount (positive=down, negative=up)."""
        import fitz

        page_height = page.rect.height
        spans_to_shift = []

        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    bbox = span["bbox"]
                    if bbox[1] > y_threshold + 2 and bbox[1] < page_height - 55:
                        chars = span.get("chars", [])
                        text = "".join(c["c"] for c in chars).strip()
                        if text:
                            spans_to_shift.append({
                                "text": text,
                                "x0": bbox[0],
                                "y0": bbox[1],
                                "x1": bbox[2],
                                "y1": bbox[3],
                                "font": span.get("font", "TimesNewRoman"),
                                "size": span.get("size", 12.0),
                                "flags": span.get("flags", 0),
                            })

        if not spans_to_shift:
            return

        # Redact
        for span in spans_to_shift:
            r = fitz.Rect(span["x0"] - 1, span["y0"] - 1, span["x1"] + 1, span["y1"] + 1)
            page.add_redact_annot(r, fill=(1, 1, 1))
        page.apply_redactions()

        # Rewrite shifted
        for span in spans_to_shift:
            font_size = span["size"]
            baseline_y = span["y1"] - font_size * 0.18 + shift_amount
            bold = bool(span["flags"] & 2**4)
            bold = bool(span["flags"] & 2**4)
            italic = bool(span["flags"] & 2**1)

            _insert_text_with_font(
                page, fitz.Point(span["x0"], baseline_y),
                span["text"], span["font"], font_size, bold, italic,
            )


    @app.get("/document/page/{page_number}/image")
    def get_page_image(page_number: int):
        """Render a page as PNG image for the viewer.

        If the page has been edited, patches it with edits applied.
        If a previous page's edit overflows onto this page, rebuilds with
        overflow prepended (shifting original content down).
        Otherwise serves the original PDF page directly (fast).
        """
        import fitz
        from fastapi.responses import Response

        session = state["session"]
        doc_ir = state["document_ir"]
        if not session or not session.document_path:
            raise HTTPException(404, "No document loaded")

        source_path = _get_source_path()
        doc = fitz.open(source_path)
        if page_number < 1 or page_number > len(doc):
            doc.close()
            raise HTTPException(400, f"Invalid page: {page_number}")

        # Check if this page has been edited by comparing IR text to source
        # If a table rebuild was performed, the working copy already has the correct
        # content — render it directly without additional patching.
        page_edited = False
        has_table_rebuild = False
        if session:
            from src.api.session import ActionType as _AT
            for action in session.undo_stack:
                if action.page == page_number and action.data.get("operation") in (
                    "table_rebuild", "toc_add", "toc_delete", "header_footer_edit"
                ):
                    has_table_rebuild = True
                    break

        if not has_table_rebuild and doc_ir and page_number <= len(doc_ir.pages):
            page_idx = page_number - 1
            source_text = doc[page_idx].get_text("text")
            ir_text = "\n".join(
                b.text_verbatim for b in doc_ir.pages[page_idx].text_blocks
            )
            if " ".join(source_text.split()) != " ".join(ir_text.split()):
                page_edited = True

        # Check if the PREVIOUS page has edits that overflow onto this page
        overflow_from_prev = []
        if doc_ir and page_number > 1:
            from src.rendering.page_patch import (
                get_page_edits_from_session,
                _apply_edit_to_page,
            )
            prev_page_num = page_number - 1
            prev_edits = get_page_edits_from_session(session, doc_ir, prev_page_num)
            if prev_edits:
                # Apply edits to a copy of the previous page to detect overflow
                prev_page = doc[prev_page_num - 1]
                for edit in prev_edits:
                    overflow = _apply_edit_to_page(prev_page, edit["old_text"], edit["new_text"])
                    if overflow:
                        overflow_from_prev.extend(overflow)

        if overflow_from_prev:
            # Rebuild this page with overflow from previous page prepended
            doc.close()
            try:
                from src.rendering.page_rebuild import rebuild_page_with_edits

                # Build overflow span dicts
                overflow_spans = []
                for line_text in overflow_from_prev:
                    overflow_spans.append({
                        "text": line_text,
                        "font": "TimesNewRoman",
                        "size": 12.0,
                        "flags": 0,
                        "color": 0,
                        "line_height": 14.16,
                        "x": 90.0,
                    })

                # Also get any edits for THIS page
                this_page_edits = get_page_edits_from_session(session, doc_ir, page_number)
                img_bytes = rebuild_page_with_edits(
                    source_path, page_number,
                    edits=this_page_edits or [],
                    prepend_overflow=overflow_spans,
                )
                return Response(content=img_bytes, media_type="image/png",
                               headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
            except Exception:
                import traceback
                traceback.print_exc()
                doc = fitz.open(source_path)
                page = doc[page_number - 1]
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                doc.close()
                return Response(content=img_bytes, media_type="image/png",
                               headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
        elif page_edited:
            # Patch the source page in-place (redact old text, insert new)
            # This preserves all unedited content pixel-perfectly
            doc.close()
            try:
                from src.rendering.page_patch import get_page_edits_from_session, patch_page

                edits = get_page_edits_from_session(state["session"], doc_ir, page_number)
                if edits:
                    img_bytes = patch_page(source_path, page_number, edits)
                else:
                    doc = fitz.open(source_path)
                    page = doc[page_number - 1]
                    pix = page.get_pixmap(dpi=150)
                    img_bytes = pix.tobytes("png")
                    doc.close()

                return Response(content=img_bytes, media_type="image/png",
                               headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
            except Exception:
                # Fallback to source on patch failure
                import traceback
                traceback.print_exc()
                doc = fitz.open(source_path)
                page = doc[page_number - 1]
                pix = page.get_pixmap(dpi=150)
                img_bytes = pix.tobytes("png")
                doc.close()
                return Response(content=img_bytes, media_type="image/png",
                               headers={"Cache-Control": "no-store, no-cache, must-revalidate"})
        else:
            # Unedited page — serve directly from source PDF (fast)
            page = doc[page_number - 1]
            pix = page.get_pixmap(dpi=150)
            img_bytes = pix.tobytes("png")
            doc.close()
            return Response(content=img_bytes, media_type="image/png",
                           headers={"Cache-Control": "no-store, no-cache, must-revalidate"})

    @app.get("/document/page/{page_number}/analysis")
    def get_page_analysis(page_number: int):
        """Return labeled content analysis for a page.

        Tells the frontend what type of content is on this page
        (table, TOC, text, etc.) and labels header/footer elements.
        """
        from src.page_analysis import analyze_page_content

        session = state["session"]
        if not session or not session.document_path:
            raise HTTPException(400, "No document loaded")
        return analyze_page_content(session.document_path, page_number)

    @app.get("/document/download")
    def download_file(path: str):
        """Serve a generated file for browser download."""
        from fastapi.responses import FileResponse
        file_path = Path(path)
        if not file_path.exists():
            raise HTTPException(404, "File not found")
        return FileResponse(
            str(file_path),
            media_type="application/octet-stream",
            filename=file_path.name,
            headers={"Content-Disposition": f"attachment; filename={file_path.name}"},
        )

    @app.get("/document/export-download")
    def export_and_download(filename: str = "exported.pdf"):
        """Export the document and immediately return it as a download.

        Uses targeted page patching (redact + insert) to preserve pixel-perfect
        fidelity for all unedited content. Only the edited text is reflowed.
        """
        from fastapi.responses import FileResponse

        doc_ir = state["document_ir"]
        session = state["session"]
        if not doc_ir or not session:
            raise HTTPException(404, "No document loaded")

        from src.output_dir import OutputDir
        from src.rendering.page_patch import (
            get_page_edits_from_session,
            _apply_edit_to_page,
            _get_pymupdf_fontname,
        )
        import fitz

        out = OutputDir(document_name=Path(session.document_path).stem)
        output_path = out.reconstructed_pdf_path
        output_path.parent.mkdir(parents=True, exist_ok=True)

        source_path = _get_source_path()

        # Determine which pages have edits
        # Skip pages with table_rebuild (working copy already correct)
        _rebuild_pages = set()
        for _a in session.undo_stack:
            if _a.data.get("operation") in ("table_rebuild", "toc_add", "toc_delete", "header_footer_edit") and _a.page:
                _rebuild_pages.add(_a.page)

        pages_with_edits: dict[int, list[dict]] = {}
        for page_num in range(1, doc_ir.page_count + 1):
            if page_num in _rebuild_pages:
                continue
            edits = get_page_edits_from_session(session, doc_ir, page_num)
            if edits:
                pages_with_edits[page_num] = edits

        # Open source and apply edits in-place (preserves all unedited content)
        source_doc = fitz.open(str(source_path))
        all_overflow: list[str] = []

        for page_num, edits in pages_with_edits.items():
            if page_num > len(source_doc):
                continue
            page = source_doc[page_num - 1]
            for edit in edits:
                overflow = _apply_edit_to_page(
                    page, edit["old_text"], edit["new_text"],
                    inline=edit.get("inline", False),
                )
                if overflow:
                    all_overflow.extend(overflow)

        # Handle overflow: merge overflow text onto the TOP of the next page,
        # pushing existing content down. This produces natural flow where
        # Section 5 appears right below the end of Section 4's overflow.
        if all_overflow and pages_with_edits:
            last_edited_page = max(pages_with_edits.keys())
            next_page_idx = last_edited_page  # 0-based index of the next page

            if next_page_idx < len(source_doc):
                from src.rendering.page_rebuild import rebuild_page_to_doc

                # Build overflow span dicts for the rebuild function
                overflow_spans = []
                for line_text in all_overflow:
                    overflow_spans.append({
                        "text": line_text,
                        "font": "TimesNewRoman",
                        "size": 12.0,
                        "flags": 0,
                        "color": 0,
                        "line_height": 14.16,
                        "x": 90.0,
                    })

                # Rebuild the next page with overflow prepended
                # (shifts all original content down to make room)
                rebuilt_doc, further_overflow = rebuild_page_to_doc(
                    source_doc, last_edited_page + 1,
                    edits=[],  # no edits on this page
                    prepend_overflow=overflow_spans,
                )

                # Replace the next page in the source doc with the rebuilt version
                source_doc.delete_page(next_page_idx)
                source_doc.insert_pdf(rebuilt_doc, start_at=next_page_idx)
                rebuilt_doc.close()

        source_doc.save(str(output_path))
        source_doc.close()

        return FileResponse(
            str(output_path),
            media_type="application/octet-stream",
            filename=filename,
            headers={"Content-Disposition": f"attachment; filename=\"{filename}\""},
        )

    @app.get("/document/page/{page_number}/table-zones")
    def get_table_zones(page_number: int):
        """Return table bounding boxes using grid density detection.

        Counts thin rectangles (table grid lines) per vertical band.
        Bands with 3+ thin rects are table bands. Consecutive table bands
        (within 120pt gap) form a zone.
        """
        import fitz

        session = state["session"]
        if not session or not session.document_path:
            raise HTTPException(404, "No document loaded")

        doc = fitz.open(_get_source_path())
        if page_number < 1 or page_number > len(doc):
            doc.close()
            raise HTTPException(400, f"Invalid page: {page_number}")

        page = doc[page_number - 1]
        drawings = page.get_drawings()
        doc.close()

        if len(drawings) < 10:
            return {"zones": []}

        # Count thin rectangles per 15pt band
        band_size = 15
        bands: dict[int, int] = {}
        for d in drawings:
            rect = d.get("rect")
            if not rect:
                continue
            w = rect.width
            h = rect.height
            # Thin rect = grid line (thin in one dimension, substantial in other)
            is_thin = (w < 3 or h < 3) and (w > 5 or h > 5)
            if is_thin:
                band = int(rect.y0 / band_size) * band_size
                bands[band] = bands.get(band, 0) + 1

        # Find bands with table-like density
        threshold = 3
        table_bands = sorted([y for y, c in bands.items() if c >= threshold])

        if not table_bands:
            return {"zones": []}

        # Cluster into zones (allow 120pt gap between bands)
        zones_raw = [[table_bands[0]]]
        for b in table_bands[1:]:
            if b - zones_raw[-1][-1] <= 120:
                zones_raw[-1].append(b)
            else:
                zones_raw.append([b])

        zones = [
            {"y_min": min(z), "y_max": max(z) + band_size}
            for z in zones_raw
        ]

        return {"zones": zones}

    @app.get("/document/page/{page_number}/table-cells")
    def get_table_cells(page_number: int, y_min: float = 0, y_max: float = 9999):
        """Return individual table cells with bounding boxes for inline editing.

        Extracts spans from rawdict in the table zone, clusters by y (rows)
        and x (columns), returns each cell with its text and bbox.
        """
        import fitz

        session = state["session"]
        doc_ir = state["document_ir"]
        if not session or not session.document_path:
            raise HTTPException(404, "No document loaded")

        doc = fitz.open(_get_source_path())
        if page_number < 1 or page_number > len(doc):
            doc.close()
            raise HTTPException(400, f"Invalid page: {page_number}")

        page = doc[page_number - 1]
        page_height = page.rect.height
        raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        doc.close()

        # Collect spans in the table zone (skip header/footer)
        table_spans = []
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    bbox = span["bbox"]
                    y = bbox[1]
                    if y < 60 or y > page_height - 60:
                        continue
                    if y < y_min or y > y_max:
                        continue
                    chars = span.get("chars", [])
                    text = "".join(c["c"] for c in chars).strip()
                    if text:
                        table_spans.append({
                            "text": text,
                            "x0": bbox[0],
                            "y0": bbox[1],
                            "x1": bbox[2],
                            "y1": bbox[3],
                        })

        if len(table_spans) < 4:
            return {"cells": [], "rows": 0, "columns": 0}

        # Cluster by y (rows) — tolerance 5pt
        table_spans.sort(key=lambda s: (s["y0"], s["x0"]))
        rows: list[list[dict]] = []
        for span in table_spans:
            placed = False
            for row in rows:
                if abs(span["y0"] - row[0]["y0"]) < 5:
                    row.append(span)
                    placed = True
                    break
            if not placed:
                rows.append([span])

        # Need at least 2 rows and 2 columns to be a table
        if len(rows) < 2:
            return {"cells": [], "rows": 0, "columns": 0}

        max_cols = max(len(row) for row in rows)
        if max_cols < 2:
            return {"cells": [], "rows": 0, "columns": 0}

        # Build cells with row/col indices
        cells = []
        for row_idx, row in enumerate(rows):
            row.sort(key=lambda s: s["x0"])
            for col_idx, span in enumerate(row):
                cells.append({
                    "id": f"cell-p{page_number:02d}-r{row_idx}-c{col_idx}",
                    "text": span["text"],
                    "bbox": {
                        "x0": span["x0"],
                        "y0": span["y0"],
                        "x1": span["x1"],
                        "y1": span["y1"],
                    },
                    "row": row_idx,
                    "col": col_idx,
                })

        # Compute table bounding box
        all_x0 = min(s["x0"] for s in table_spans)
        all_y0 = min(s["y0"] for s in table_spans)
        all_x1 = max(s["x1"] for s in table_spans)
        all_y1 = max(s["y1"] for s in table_spans)

        return {
            "cells": cells,
            "rows": len(rows),
            "columns": max_cols,
            "table_bbox": {"x0": all_x0, "y0": all_y0, "x1": all_x1, "y1": all_y1},
        }


        """Merge body spans into paragraph groups (lines of span lists)."""
        import re
        if not spans:
            return []
        spans.sort(key=lambda s: (s["y0"], s["x0"]))
        # Group spans on the same line (same y within 3pt)
        lines_grouped: list[list] = []
        current_line = [spans[0]]
        for span in spans[1:]:
            if abs(span["y0"] - current_line[0]["y0"]) <= 3:
                current_line.append(span)
            else:
                lines_grouped.append(current_line)
                current_line = [span]
        lines_grouped.append(current_line)

        # Merge consecutive lines into paragraphs
        paragraphs = []
        current_para = [lines_grouped[0]]
        for line in lines_grouped[1:]:
            prev_line = current_para[-1]
            prev_y = prev_line[0]["y0"]
            curr_y = line[0]["y0"]
            gap = curr_y - prev_y
            curr_is_heading = line[0]["size"] > 13
            prev_is_heading = current_para[0][0]["size"] > 13
            first_text = line[0]["text"].strip()
            is_list_item = bool(re.match(r"^\d+[\.\)]\s", first_text))
            is_section = bool(re.match(r"^[1-9]\d*\.\d+", first_text))
            is_bullet = first_text.startswith("•") or first_text.startswith("‣")

            if gap > 18 or gap < 0 or curr_is_heading or prev_is_heading or is_list_item or is_section or is_bullet:
                paragraphs.append(current_para)
                current_para = [line]
            else:
                current_para.append(line)
        paragraphs.append(current_para)
        return paragraphs

    @app.get("/document/page/{page_number}/elements")
    def get_page_elements(page_number: int):
        """Return all clickable elements on a page with bboxes and labels.

        Headers/footers: individual spans.
        Body text: merged into logical paragraphs (consecutive lines
        with gap ≤ 16pt and similar left margin).

        If the page has been edited, returns text from the Document IR
        instead of from the source PDF.
        """
        import fitz

        session = state["session"]
        doc_ir = state["document_ir"]
        if not session or not session.document_path or not doc_ir:
            raise HTTPException(404, "No document loaded")

        # Check if page is edited — if so, return elements from Document IR directly
        page_idx = page_number - 1
        if page_idx < len(doc_ir.pages):
            # ALWAYS return from Document IR — it has block IDs and correct text
            page_info = doc_ir.pages[page_idx]
            elements = []
            for block in page_info.text_blocks:
                elements.append({
                    "type": block.block_type,
                    "label": block.block_type,
                    "text": block.text_verbatim,
                    "id": block.id,
                    "bbox": {
                        "x0": block.bbox.x0,
                        "y0": block.bbox.y0,
                        "x1": block.bbox.x1,
                        "y1": block.bbox.y1,
                    },
                })
            return {"page_number": page_number, "elements": elements}

        # Unedited page — extract from source PDF as before
        doc = fitz.open(session.document_path)
        if page_number < 1 or page_number > len(doc):
            doc.close()
            raise HTTPException(400, f"Invalid page: {page_number}")

        page = doc[page_number - 1]
        page_width = page.rect.width
        page_height = page.rect.height
        raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        doc.close()

        elements = []
        body_spans = []  # collect body spans for paragraph merging

        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    chars = span.get("chars", [])
                    text = "".join(c["c"] for c in chars).strip()
                    if not text:
                        continue

                    bbox = span["bbox"]
                    y = bbox[1]
                    x = bbox[0]

                    if y < 60:
                        align = "left" if x < page_width * 0.33 else "right" if x > page_width * 0.55 else "center"
                        elements.append({
                            "type": "header",
                            "label": f"Header ({align})",
                            "text": text,
                            "id": None,
                            "bbox": {"x0": bbox[0], "y0": bbox[1], "x1": bbox[2], "y1": bbox[3]},
                        })
                    elif y > page_height - 72:
                        align = "left" if x < page_width * 0.33 else "right" if x > page_width * 0.55 else "center"
                        elements.append({
                            "type": "footer",
                            "label": f"Footer ({align})",
                            "text": text,
                            "id": None,
                            "bbox": {"x0": bbox[0], "y0": bbox[1], "x1": bbox[2], "y1": bbox[3]},
                        })
                    else:
                        body_spans.append({
                            "text": text,
                            "x0": bbox[0], "y0": bbox[1],
                            "x1": bbox[2], "y1": bbox[3],
                            "size": span.get("size", 11),
                        })

        # Check if this is a TOC or table page
        from src.page_analysis import analyze_page_content
        page_analysis = analyze_page_content(session.document_path, page_number)
        is_toc_page = page_analysis.get("page_type") == "table_of_contents"
        is_table_page = page_analysis.get("page_type") == "table"

        # On TOC pages, skip body entirely (TOC editor handles)
        if is_toc_page:
            return {"page_number": page_number, "elements": elements}

        # On table pages, get table y-range to exclude table spans from merge
        table_y_min = 0
        table_y_max = 0
        if is_table_page:
            # Get table range from the table detection logic
            import fitz as fitz2
            doc2 = fitz2.open(session.document_path)
            page2 = doc2[page_number - 1]
            page_height2 = page2.rect.height
            raw2 = page2.get_text("rawdict", flags=fitz2.TEXT_PRESERVE_WHITESPACE)
            doc2.close()
            # Cluster y positions of body spans to find table rows
            table_spans = []
            for blk in raw2.get("blocks", []):
                if blk.get("type") != 0:
                    continue
                for ln in blk.get("lines", []):
                    for sp in ln.get("spans", []):
                        cs = sp.get("chars", [])
                        t = "".join(c["c"] for c in cs).strip()
                        if t and 70 < sp["bbox"][1] < page_height2 - 72:
                            table_spans.append(sp["bbox"][1])
            if table_spans:
                # Use the clustering from table endpoint logic
                sorted_ys = sorted(table_spans)
                clusters = [[sorted_ys[0]]]
                for v in sorted_ys[1:]:
                    if v - clusters[-1][-1] < 8:
                        clusters[-1].append(v)
                    else:
                        clusters.append([v])
                row_clusters = [sorted(c)[len(c)//2] for c in clusters if len(c) >= 2]
                if len(row_clusters) >= 3:
                    table_y_min = row_clusters[0]
                    table_y_max = row_clusters[-1] + 20

            # Don't filter body_spans — show all elements, let frontend handle visibility
            pass

        if not body_spans:
            return {"page_number": page_number, "elements": elements}

        # Detect columns by x-position clustering
        x_positions = [s["x0"] for s in body_spans]
        left_margin = min(x_positions)
        right_spans = [s for s in body_spans if s["x0"] > page_width * 0.45]
        left_spans = [s for s in body_spans if s["x0"] <= page_width * 0.45]

        # If significant content in right half, treat as two-column
        is_two_column = len(right_spans) > 3 and len(left_spans) > 3

        if is_two_column:
            # Process each column separately, then combine
            all_paragraphs = []
            all_paragraphs.extend(_merge_spans_to_paragraphs(left_spans))
            all_paragraphs.extend(_merge_spans_to_paragraphs(right_spans))
            paragraphs = all_paragraphs
        else:
            paragraphs = _merge_spans_to_paragraphs(body_spans)

        # Post-process: if a paragraph starts with a section number,
        # separate it as its own element (don't merge with following text)
        import re

        # Post-process: if a paragraph starts with a section number,
        # separate it as its own element (don't merge with following text)
        final_paragraphs = []
        for para in paragraphs:
            if len(para) > 1:
                first_text = para[0][0]["text"].strip()
                if re.match(r"^\d+[\.\)]\s*$", first_text) or re.match(r"^[1-9]\d*\.\d+", first_text):
                    # Section header line is standalone
                    final_paragraphs.append([para[0]])
                    if len(para) > 1:
                        final_paragraphs.append(para[1:])
                else:
                    final_paragraphs.append(para)
            else:
                final_paragraphs.append(para)
        paragraphs = final_paragraphs

        # Convert merged paragraphs to elements
        page_ir = doc_ir.pages[page_number - 1]
        for para_lines in paragraphs:
            # Flatten all spans in this paragraph
            all_spans = [s for line in para_lines for s in line]
            text = " ".join(s["text"] for s in all_spans)
            x0 = min(s["x0"] for s in all_spans)
            y0 = min(s["y0"] for s in all_spans)
            x1 = max(s["x1"] for s in all_spans)
            y1 = max(s["y1"] for s in all_spans)
            size = para_lines[0][0]["size"]

            label = "Heading" if size > 13 else "Paragraph"

            # Section numbers are headings regardless of size
            first_text = all_spans[0]["text"].strip()
            if re.match(r"^\d+[\.\)]\s", first_text) or re.match(r"^[1-9]\d*\.\d+", first_text):
                label = "Heading"

            # Find matching IR block
            block_id = None
            for ir_block in page_ir.text_blocks:
                if (abs(ir_block.bbox.y0 - y0) < 10 and
                        all_spans[0]["text"][:15] in ir_block.text_verbatim):
                    block_id = ir_block.id
                    break

            elements.append({
                "type": "text_block",
                "label": label,
                "text": text,
                "id": block_id,
                "bbox": {"x0": x0, "y0": y0, "x1": x1, "y1": y1},
            })

        return {"page_number": page_number, "elements": elements}

    @app.get("/document/page/{page_number}/toc")
    def get_toc(page_number: int):
        """Parse a Table of Contents page into title/page-number pairs.

        Strips leader dots and separates section titles from page numbers.
        """
        import fitz
        import re

        session = state["session"]
        if not session or not session.document_path:
            raise HTTPException(404, "No document loaded")

        doc = fitz.open(_get_source_path())
        if page_number < 1 or page_number > len(doc):
            doc.close()
            raise HTTPException(400, f"Invalid page: {page_number}")

        page = doc[page_number - 1]
        raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        doc.close()

        entries = []
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    chars = span.get("chars", [])
                    text = "".join(c["c"] for c in chars).strip()
                    if not text:
                        continue

                    y = span["bbox"][1]
                    if y < 60 or y > 700:
                        continue

                    # Skip the "Table of Contents" title itself
                    if "table of contents" in text.lower():
                        continue

                    # Check if this span has leader dots
                    if text.count(".") > 5:
                        # Parse: "Section Title.............page_ref"
                        # Page ref can be digits or Roman numerals (i, ii, iii, iv)
                        match = re.match(r"^(.+?)\.{3,}\s*([ivxlcdmIVXLCDM\d]+)?\s*$", text)
                        if match:
                            title = match.group(1).strip()
                            page_num = match.group(2) or ""
                            entries.append({
                                "title": title,
                                "page_ref": page_num,
                                "y": y,
                                "indent": span["bbox"][0] - 90,  # indent level
                            })
                        else:
                            # Dots but no page ref parse — strip all trailing dots
                            title = re.sub(r"\.{3,}.*$", "", text).strip()
                            if title:
                                entries.append({
                                    "title": title,
                                    "page_ref": "",
                                    "y": y,
                                    "indent": span["bbox"][0] - 90,
                                })
                    else:
                        # Non-dot span — could be section number or standalone page ref
                        # Check if it's just a number (page reference at end of line)
                        if re.match(r"^\d+$", text):
                            # Page number — attach to previous entry
                            if entries:
                                entries[-1]["page_ref"] = text
                        elif re.match(r"^\d+\.", text):
                            # Section number like "1." or "3." — attach to next
                            entries.append({
                                "title": text,
                                "page_ref": "",
                                "y": y,
                                "indent": span["bbox"][0] - 90,
                                "is_number_prefix": True,
                            })
                        elif len(text) > 3:
                            entries.append({
                                "title": text,
                                "page_ref": "",
                                "y": y,
                                "indent": span["bbox"][0] - 90,
                            })

        # Merge section number prefixes with their following title
        merged = []
        skip_next = False
        for i, entry in enumerate(entries):
            if skip_next:
                skip_next = False
                continue
            if entry.get("is_number_prefix") and i + 1 < len(entries):
                next_entry = entries[i + 1]
                merged.append({
                    "title": entry["title"] + " " + next_entry["title"],
                    "page_ref": next_entry["page_ref"] or entry["page_ref"],
                    "y": entry["y"],
                    "indent": entry["indent"],
                })
                skip_next = True
            else:
                if "is_number_prefix" in entry:
                    del entry["is_number_prefix"]
                merged.append(entry)

        return {"is_toc": len(merged) >= 3, "entries": merged}

    @app.put("/document/page/{page_number}/toc")
    def edit_toc_entry(page_number: int, index: int, title: str = "", page_ref: str = ""):
        """Edit a TOC entry (title and/or page number).

        Stores the edit in the session so it can be applied on export/preview.
        The edit is recorded as a BLOCK_EDITED action on the TOC page.
        """
        import fitz

        session = state["session"]
        doc_ir = state["document_ir"]
        if not session or not session.document_path:
            raise HTTPException(404, "No document loaded")

        # Get the current TOC entries to find what we're replacing
        toc_res = get_toc(page_number)
        if not toc_res["is_toc"]:
            raise HTTPException(400, f"Page {page_number} is not a TOC page")

        entries = toc_res["entries"]
        if index < 0 or index >= len(entries):
            raise HTTPException(400, f"Invalid entry index: {index}")

        old_entry = entries[index]
        old_title = old_entry["title"]
        old_page_ref = old_entry["page_ref"]

        new_title = title if title else old_title
        new_page_ref = page_ref if page_ref else old_page_ref

        if new_title == old_title and new_page_ref == old_page_ref:
            return {"status": "unchanged"}

        # Find the old text on the PDF page to construct the patch
        # TOC lines have the format: "Title ...dots... page_number"
        # We need to find what's searchable on the page for this entry
        doc = fitz.open(session.document_path)
        page = doc[page_number - 1]

        # Strategy: search for the title text (without dots/page num)
        # The rawdict shows the line as "Title ...dots...N" in one span
        old_search = old_title.strip()
        instances = page.search_for(old_search)
        doc.close()

        if not instances:
            raise HTTPException(404, f"Could not find '{old_search}' on page {page_number}")

        # Build the old and new full-line representations
        # For the IR block, store the edit as title replacement
        # Find the IR block that contains this TOC entry and record
        # a targeted edit that _apply_edit_to_page can find uniquely.
        if doc_ir and page_number <= len(doc_ir.pages):
            page_info = doc_ir.pages[page_number - 1]
            import re as _re
            # Strip leading section number pattern like "4." or "3.2.1."
            title_without_num = _re.sub(r"^\d+[\.\d]*\.?\s*", "", old_title).strip()
            new_title_without_num = _re.sub(r"^\d+[\.\d]*\.?\s*", "", new_title).strip()
            search_key = title_without_num if title_without_num else old_title

            for block in page_info.text_blocks:
                if search_key in block.text_verbatim:
                    old_ir_text = block.text_verbatim
                    new_ir_text = old_ir_text.replace(title_without_num, new_title_without_num, 1)

                    if old_page_ref and new_page_ref != old_page_ref:
                        new_ir_text = _re.sub(
                            rf"(\.{{3,}}\s*){_re.escape(old_page_ref)}(\s|$)",
                            rf"\g<1>{new_page_ref}\2",
                            new_ir_text,
                            count=1,
                        )

                    block.text_verbatim = new_ir_text

                    # Record the edit. The undo system uses old_text/new_text to
                    # reverse the IR change. For PDF patching, get_page_edits_from_session
                    # uses old_text to search on the page. Store the IR-level
                    # texts so undo works, and add a "patch_old"/"patch_new" for
                    # the PDF-level search.
                    session.record(
                        ActionType.BLOCK_EDITED,
                        page=page_number,
                        block_id=block.id,
                        data={
                            "old_text": old_ir_text,
                            "new_text": new_ir_text,
                            "patch_old": old_title,
                            "patch_new": new_title,
                        },
                    )
                    break

        return {
            "status": "updated",
            "old_title": old_title,
            "new_title": new_title,
            "old_page_ref": old_page_ref,
            "new_page_ref": new_page_ref,
        }

    @app.post("/document/page/{page_number}/toc")
    def add_toc_entry(page_number: int, title: str = "New Section", page_ref: str = "", after_index: int = -1):
        """Add a new TOC entry to the page.

        Inserts the entry text (with leader dots and page number) onto the PDF
        working copy at the appropriate y-position.
        """
        import fitz

        session = state["session"]
        doc_ir = state["document_ir"]
        if not session or not session.document_path:
            raise HTTPException(404, "No document loaded")

        # Get current TOC to determine insertion position
        toc_res = get_toc(page_number)
        if not toc_res["is_toc"]:
            raise HTTPException(400, f"Page {page_number} is not a TOC page")

        entries = toc_res["entries"]

        # Determine y-position for new entry
        if after_index >= 0 and after_index < len(entries):
            # Insert after specified entry
            insert_y = entries[after_index]["y"] + 14.0
        elif entries:
            # Append at the end
            insert_y = entries[-1]["y"] + 14.0
        else:
            insert_y = 80.0  # Default start

        # Build the TOC line text: "Title...........page_ref"
        dots_needed = 60 - len(title) - len(page_ref)
        dots = "." * max(dots_needed, 3)
        full_line = f"{title}{dots}{page_ref}" if page_ref else title

        # Backup the working copy before modification (for undo)
        import shutil as _shutil
        source_path = _get_source_path()
        backup_path = source_path + ".undo_backup"
        _shutil.copy2(source_path, backup_path)

        # Write to the working copy
        doc = fitz.open(source_path)
        page = doc[page_number - 1]

        # Get font info from existing TOC entries
        raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        font_name = "TimesNewRoman"
        font_size = 12.0
        insert_x = 90.0
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if 60 < span["bbox"][1] < 700 and span.get("size", 0) <= 13:
                        font_name = span.get("font", "TimesNewRoman")
                        font_size = span.get("size", 12.0)
                        insert_x = span["bbox"][0]
                        break

        from src.rendering.page_patch import _get_pymupdf_fontname
        baseline_y = insert_y + font_size * 0.8

        _insert_text_with_font(
            page, fitz.Point(insert_x, baseline_y),
            full_line, font_name, font_size,
        )

        doc.save(source_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        doc.close()

        # Record in session
        if session:
            session.record(
                ActionType.BLOCK_EDITED,
                page=page_number,
                block_id=None,
                data={
                    "operation": "toc_add",
                    "title": title,
                    "page_ref": page_ref,
                    "y": insert_y,
                },
            )

        return {"status": "added", "title": title, "page_ref": page_ref, "y": insert_y}

    @app.delete("/document/page/{page_number}/toc")
    def delete_toc_entry(page_number: int, index: int):
        """Delete a TOC entry by redacting its text from the page."""
        import fitz

        session = state["session"]
        if not session or not session.document_path:
            raise HTTPException(404, "No document loaded")

        # Get current entries to find the one to delete
        toc_res = get_toc(page_number)
        if not toc_res["is_toc"]:
            raise HTTPException(400, f"Page {page_number} is not a TOC page")

        entries = toc_res["entries"]
        if index < 0 or index >= len(entries):
            raise HTTPException(400, f"Invalid index: {index}")

        entry = entries[index]
        old_title = entry["title"]

        # Backup the working copy before modification (for undo)
        import shutil as _shutil
        source_path = _get_source_path()
        backup_path = source_path + ".undo_backup"
        _shutil.copy2(source_path, backup_path)

        # Find and redact the entry on the working copy
        doc = fitz.open(source_path)
        page = doc[page_number - 1]

        # Search for the title text on the page
        instances = page.search_for(old_title)
        if instances:
            # Redact the found rect (covers title + dots + page number)
            rect = instances[0]
            # Expand rect to cover the full line width
            redact_rect = fitz.Rect(rect.x0 - 2, rect.y0 - 1, 530, rect.y1 + 1)
            page.add_redact_annot(redact_rect, fill=(1, 1, 1))
            page.apply_redactions()

        doc.save(source_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        doc.close()

        # Record in session
        if session:
            session.record(
                ActionType.BLOCK_EDITED,
                page=page_number,
                block_id=None,
                data={
                    "operation": "toc_delete",
                    "title": old_title,
                    "page_ref": entry.get("page_ref", ""),
                    "index": index,
                },
            )

        return {"status": "deleted", "title": old_title}


    @app.get("/document/page/{page_number}/header-footer")
    def get_header_footer(page_number: int):
        """Return individual header and footer elements for editing.

        Unlike the block-level view, this returns each header/footer
        span separately with position labels (left/center/right).
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
        page_width = page.rect.width
        raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        doc.close()

        headers = []
        footers = []

        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    chars = span.get("chars", [])
                    text = "".join(c["c"] for c in chars).strip()
                    if not text:
                        continue

                    y = span["bbox"][1]
                    x = span["bbox"][0]

                    if x < page_width * 0.33:
                        alignment = "left"
                    elif x > page_width * 0.55:
                        alignment = "right"
                    else:
                        alignment = "center"

                    entry = {
                        "text": text,
                        "alignment": alignment,
                        "x": span["bbox"][0],
                        "y": span["bbox"][1],
                        "font": span["font"],
                        "size": span["size"],
                    }

                    if y < 60:
                        headers.append(entry)
                    elif y > 700:
                        footers.append(entry)

        return {
            "page_number": page_number,
            "header": headers,
            "footer": footers,
        }

    @app.put("/document/page/{page_number}/header-footer")
    def edit_header_footer(page_number: int, section: str, alignment: str, new_text: str):
        """Edit a header or footer span on the working copy.

        Args:
            section: "header" or "footer"
            alignment: "left", "center", or "right"
            new_text: replacement text
        """
        import fitz

        session = state["session"]
        if not session or not session.document_path:
            raise HTTPException(404, "No document loaded")

        if section not in ("header", "footer"):
            raise HTTPException(400, "section must be 'header' or 'footer'")
        if alignment not in ("left", "center", "right"):
            raise HTTPException(400, "alignment must be 'left', 'center', or 'right'")

        # Get the current entry to find old text
        hf_data = get_header_footer(page_number)
        entries = hf_data[section]
        old_entry = next((e for e in entries if e["alignment"] == alignment), None)
        if not old_entry:
            raise HTTPException(404, f"No {alignment} {section} found on page {page_number}")

        old_text = old_entry["text"]
        if old_text == new_text:
            return {"status": "unchanged"}

        # Backup for undo
        import shutil as _shutil
        source_path = _get_source_path()
        backup_path = source_path + ".undo_backup"
        _shutil.copy2(source_path, backup_path)

        # Patch the working copy: find old text, redact, insert new
        doc = fitz.open(source_path)
        page = doc[page_number - 1]

        instances = page.search_for(old_text)
        if not instances:
            doc.close()
            raise HTTPException(404, f"Could not find '{old_text}' on page")

        rect = instances[0]

        # Get font info from the original span
        raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE)
        font_name = "TimesNewRoman"
        font_size = 12.0
        for block in raw.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    chars = span.get("chars", [])
                    span_text = "".join(c["c"] for c in chars).strip()
                    if span_text == old_text:
                        font_name = span.get("font", "TimesNewRoman")
                        font_size = span.get("size", 12.0)
                        break

        # Redact old text
        page.add_redact_annot(rect, fill=(1, 1, 1))
        page.apply_redactions()

        # Insert new text at same position using extracted font
        baseline_y = rect.y1 - font_size * 0.18

        # Preserve alignment: left stays at x0, center/right need calculation
        if alignment == "left":
            insert_x = rect.x0
        elif alignment == "center":
            text_width = _get_text_width(new_text, font_name, font_size)
            original_center = (rect.x0 + rect.x1) / 2
            insert_x = original_center - text_width / 2
        else:  # right
            text_width = _get_text_width(new_text, font_name, font_size)
            insert_x = rect.x1 - text_width

        _insert_text_with_font(
            page, fitz.Point(insert_x, baseline_y),
            new_text, font_name, font_size,
        )

        doc.save(source_path, incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
        doc.close()

        # Record session action
        session.record(
            ActionType.BLOCK_EDITED,
            page=page_number,
            block_id=None,
            data={
                "operation": "header_footer_edit",
                "section": section,
                "alignment": alignment,
                "old_text": old_text,
                "new_text": new_text,
            },
        )

        return {"status": "updated", "old_text": old_text, "new_text": new_text}


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

    # ─── Editing ───────────────────────────────────────────────────

    @app.get("/document/tbd-items")
    def get_tbd_items():
        """Return all TBD/TBR/TBC/TBS items in the document."""
        doc_ir = state["document_ir"]
        if not doc_ir:
            raise HTTPException(404, "No document loaded")

        from src.tbd_tracker import scan_document

        items = scan_document(doc_ir)
        return {
            "count": len(items),
            "open": sum(1 for i in items if i.status == "open"),
            "items": [
                {
                    "id": i.id,
                    "type": i.item_type,
                    "status": i.status,
                    "page": i.page,
                    "owner": i.owner,
                    "context": i.context[:80],
                }
                for i in items
            ],
        }

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
                        data={
                            "old_text": old_text,
                            "new_text": new_text,
                            "patch_old": old_text,
                            "patch_new": new_text,
                            "inline": True,
                        },
                    )

                return {"status": "updated", "block_id": block.id}

        raise HTTPException(404, f"Text not found on page {page}")

    @app.put("/document/block/{block_id}")
    def edit_block(block_id: str, req: EditRequest):
        """Edit a text block's content, reflow the page, and split if overflow."""
        from src.reflow import reflow_and_split

        doc_ir = state["document_ir"]
        if not doc_ir:
            raise HTTPException(404, "No document loaded")

        # Find the block
        for page in doc_ir.pages:
            for block in page.text_blocks:
                if block.id == block_id:
                    old_text = block.text_verbatim
                    block.text_verbatim = req.new_text

                    # Run reflow + page split if needed
                    reflow_result = reflow_and_split(doc_ir, page.page_number, block_id)

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
                        "total_pages": doc_ir.page_count,
                        "old_text": old_text,
                        "new_text": req.new_text,
                        "reflow": {
                            "height_delta_pt": round(reflow_result.height_delta_pt, 1),
                            "blocks_shifted": reflow_result.blocks_shifted,
                            "overflow_pt": round(reflow_result.overflow_pt, 1),
                            "overflowing_blocks": reflow_result.overflowing_blocks,
                            "page_added": reflow_result.page_added,
                            "new_page_number": reflow_result.new_page_number,
                        },
                    }

        raise HTTPException(404, f"Block not found: {block_id}")

    @app.post("/document/undo")
    def undo():
        """Undo the last edit."""
        import shutil

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

        # If this was a table rebuild or TOC modification, restore the PDF backup
        if action.data.get("operation") in ("table_rebuild", "toc_add", "toc_delete", "header_footer_edit"):
            source_path = _get_source_path()
            backup_path = source_path + ".undo_backup"
            if Path(backup_path).exists():
                shutil.copy2(backup_path, source_path)
            # For operations without a block_id, the PDF restore IS the undo
            if not block_id:
                return {
                    "status": "undone",
                    "block_id": None,
                    "page": action.page,
                    "restored_text": f"Reverted {action.data.get('operation')}",
                }

        # Find the block and reverse the edit
        for page in doc_ir.pages:
            for block in page.text_blocks:
                if block_id and block.id == block_id:
                    # Replace new_text back to old_text within the block
                    if new_text and new_text in block.text_verbatim:
                        block.text_verbatim = block.text_verbatim.replace(new_text, old_text)
                    else:
                        block.text_verbatim = old_text
                    return {
                        "status": "undone",
                        "block_id": block_id,
                        "page": page.page_number,
                        "restored_text": old_text[:50],
                    }

        return {"status": "undone", "block_id": block_id, "page": None}

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
                    return {
                        "status": "redone",
                        "block_id": block_id,
                        "page": page.page_number,
                        "applied_text": new_text[:50],
                    }

        return {"status": "redone", "block_id": block_id, "page": None}

    # ─── Save ─────────────────────────────────────────────────────

    @app.post("/document/save")
    def save_document():
        """Save the working copy back to the original file.

        This is the explicit "File > Save" action. Until this is called,
        the original PDF on disk is untouched. All edits (table rows,
        text patches) live only in the working copy.
        """
        import shutil

        session = state["session"]
        if not session or not session.document_path:
            raise HTTPException(404, "No document loaded")

        working_copy = state.get("working_copy_path")
        if not working_copy or not Path(working_copy).exists():
            raise HTTPException(400, "No working copy to save")

        original_path = Path(session.document_path)

        # Copy working copy over the original
        shutil.copy2(working_copy, str(original_path))

        # Record the save action
        session.record(
            ActionType.DOCUMENT_SAVED,
            data={"path": str(original_path)},
        )

        return {
            "status": "saved",
            "path": str(original_path),
            "message": f"Saved to {original_path.name}",
        }

    # ─── Export ────────────────────────────────────────────────────

    @app.post("/document/export")
    def export_pdf():
        """Export the current document state as a PDF (with edits applied).

        Uses 1:1 page patching: copies the source PDF and applies text
        redaction/insertion only for edited values. Unedited pages and
        all non-edited content remains pixel-identical to the source.
        """
        doc_ir = state["document_ir"]
        session = state["session"]
        if not doc_ir or not session:
            raise HTTPException(404, "No document loaded — open a document first")

        from src.output_dir import OutputDir
        from src.rendering.page_patch import get_page_edits_from_session, _apply_edit_to_page

        import fitz

        out = OutputDir(
            document_name=Path(session.document_path).stem if session else "export"
        )
        output_path = out.reconstructed_pdf_path
        output_path.parent.mkdir(parents=True, exist_ok=True)

        source_path = _get_source_path()

        # Determine which pages have edits
        # Skip pages with table_rebuild (working copy already correct)
        _rebuild_pages = set()
        for _a in session.undo_stack:
            if _a.data.get("operation") in ("table_rebuild", "toc_add", "toc_delete", "header_footer_edit") and _a.page:
                _rebuild_pages.add(_a.page)

        pages_with_edits: dict[int, list[dict]] = {}
        for page_num in range(1, doc_ir.page_count + 1):
            if page_num in _rebuild_pages:
                continue
            edits = get_page_edits_from_session(session, doc_ir, page_num)
            if edits:
                pages_with_edits[page_num] = edits

        # Build the output PDF with pages in correct order.
        # The IR may have more pages than the source (from page splits).
        # Pages that exist in source get patched; new pages get rendered from IR.
        from src.rendering.ir_renderer import _ir_blocks_to_elements
        from src.rendering.renderer import render_page_to_html

        source_doc = fitz.open(str(source_path))
        source_page_count = len(source_doc)

        # First, apply edits to the source document
        for page_num, edits in pages_with_edits.items():
            if page_num > source_page_count:
                continue
            page = source_doc[page_num - 1]
            for edit in edits:
                _apply_edit_to_page(page, edit["old_text"], edit["new_text"])

        # If overflow occurred, redact moved content from the source page
        if doc_ir.page_count > source_page_count:
            for action in session.actions:
                if action.action_type == ActionType.BLOCK_EDITED and action.page:
                    edited_page_num = action.page
                    if edited_page_num > source_page_count:
                        continue
                    overflow_ir_idx = edited_page_num
                    if overflow_ir_idx < len(doc_ir.pages):
                        overflow_page_info = doc_ir.pages[overflow_ir_idx]
                        source_page = source_doc[edited_page_num - 1]
                        for block in overflow_page_info.text_blocks:
                            search_text = block.text_verbatim[:50].split("\n")[0].strip()
                            if len(search_text) < 5:
                                continue
                            instances = source_page.search_for(search_text)
                            if instances:
                                source_page.add_redact_annot(instances[0], fill=(1, 1, 1))
                        source_page.apply_redactions()
                    break

        if doc_ir.page_count <= source_page_count:
            # No new pages — just save the patched source
            source_doc.save(str(output_path))
            source_doc.close()
        else:
            # New pages were created by page splits.
            # The split inserts new pages in the middle, pushing later pages down.
            # Strategy: find the insertion point by checking which IR page was
            # reported as "new_page_number" in the session's reflow actions.
            # Then: source pages before the insertion come first, then new page(s),
            # then remaining source pages.

            # Find where new pages were inserted
            insert_after = source_page_count  # default: append at end
            for action in session.actions:
                if action.action_type == ActionType.BLOCK_EDITED:
                    # The edit was on this page — the new page goes after it
                    if action.page:
                        insert_after = action.page
                        break

            num_new_pages = doc_ir.page_count - source_page_count

            output_doc = fitz.open()

            # Pages before the insertion point (from source, already patched)
            if insert_after > 0:
                output_doc.insert_pdf(source_doc, from_page=0, to_page=insert_after - 1)

            # New pages (rendered from IR)
            for i in range(num_new_pages):
                ir_idx = insert_after + i  # 0-based index in IR for new pages
                page_info = doc_ir.pages[ir_idx]
                try:
                    from weasyprint import HTML
                    elements = _ir_blocks_to_elements(page_info)
                    html = render_page_to_html(page_info.width_pt, page_info.height_pt, elements)
                    pdf_bytes = HTML(string=html).write_pdf()
                    rendered = fitz.open(stream=pdf_bytes, filetype="pdf")
                    output_doc.insert_pdf(rendered)
                    rendered.close()
                except Exception:
                    new_page = output_doc.new_page(
                        width=page_info.width_pt, height=page_info.height_pt
                    )
                    y = 72.0
                    for block in page_info.text_blocks:
                        new_page.insert_text(
                            fitz.Point(block.bbox.x0, y + 12),
                            block.text_verbatim[:200],
                            fontname="tiro", fontsize=10, color=(0, 0, 0),
                        )
                        y += max(14, block.bbox.height)

            # Remaining source pages (after the insertion point)
            if insert_after < source_page_count:
                output_doc.insert_pdf(source_doc, from_page=insert_after, to_page=source_page_count - 1)

            output_doc.save(str(output_path))
            output_doc.close()
            source_doc.close()

        if session:
            session.record(
                ActionType.DOCUMENT_EXPORTED, data={"path": str(output_path)}
            )

        return {"status": "exported", "path": str(output_path)}

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

    # ─── Search & RAG ────────────────────────────────────────────────

    @app.get("/search/models")
    def get_search_models():
        """Return available search models with descriptions and benchmark scores."""
        from src.search.config import ALL_CONFIGS

        models = []
        for cfg in ALL_CONFIGS:
            provider = cfg.embedding_config.provider.value
            cost = cfg.embedding_config.cost_per_1k_tokens
            strategy = cfg.chunk_config.strategy.value

            # Friendly descriptions
            if "titan" in provider and "v2" in provider:
                desc = "Best balance of quality and cost"
            elif "titan" in provider and "v1" in provider:
                desc = "Cheapest option, slightly lower accuracy"
            elif "cohere" in provider and "english" in provider:
                desc = "Strong on synonyms and paraphrasing"
            elif "cohere" in provider and "multilingual" in provider:
                desc = "Best for non-English content"
            else:
                desc = "Standard embedding model"

            models.append({
                "id": cfg.name,
                "provider": provider,
                "strategy": strategy,
                "description": desc,
                "cost_per_1k_tokens": cost,
                "dimensions": cfg.embedding_config.dimensions,
            })

        return {"models": models, "default": "titan-v2-sliding"}

    @app.get("/search/evaluation-suite")
    def get_evaluation_suite():
        """Return the ground truth evaluation queries organized by document."""
        from src.search.ground_truth import ALL_GROUND_TRUTH, EXPANDED_QUERIES

        result = {}
        for doc_key, judgments in ALL_GROUND_TRUTH.items():
            result[doc_key] = [
                {
                    "query_id": j.query_id,
                    "query": j.query,
                    "expected_terms": j.relevant_texts,
                    "expected_pages": j.relevant_pages,
                    "category": j.category,
                }
                for j in judgments
            ]

        # Group expanded queries by document prefix (e.g., "lvc-006" → "20150010976")
        prefix_to_doc = {
            "lvc": "20150010976",
            "hsi": "HSI_SYS_015G",
            "tsafe": "20130010957",
            "ice": "ICESat2_ATL03",
            "idss": "IDSS_IDD_RevF",
            "nds": "NDS_IDD_RevC",
        }
        for j in EXPANDED_QUERIES:
            # Handle both "lvc-006" and "batch2_lvc_001" formats
            qid = j.query_id
            matched = False
            for prefix, doc_key in prefix_to_doc.items():
                if prefix in qid:
                    if doc_key not in result:
                        result[doc_key] = []
                    result[doc_key].append({
                        "query_id": j.query_id,
                        "query": j.query,
                        "expected_terms": j.relevant_texts,
                        "expected_pages": j.relevant_pages,
                        "category": j.category,
                    })
                    matched = True
                    break
            if not matched:
                if "_other" not in result:
                    result["_other"] = []
                result["_other"].append({
                    "query_id": j.query_id,
                    "query": j.query,
                    "expected_terms": j.relevant_texts,
                    "expected_pages": j.relevant_pages,
                    "category": j.category,
                })

        return {
            "documents": result,
            "total_queries": sum(len(v) for v in result.values()),
            "metrics_measured": [
                "Recall@5 — Of correct results, how many appear in top 5?",
                "Recall@10 — Of correct results, how many appear in top 10?",
                "Mean Reciprocal Rank (MRR) — On average, how high is the first correct result?",
                "Precision@5 — Of the top 5 results, how many are actually relevant?",
                "Hit Rate — Percentage of queries with at least one relevant result in top 10",
            ],
        }

    @app.get("/search/evaluation-results")
    def get_evaluation_results():
        """Return the latest benchmark results if available."""
        import json
        results_dir = Path("tests/results/search_eval")

        # Load the latest eval run
        eval_files = sorted(results_dir.glob("eval_*.json"), reverse=True)
        benchmark_files = sorted(results_dir.glob("benchmark_*.json"), reverse=True)

        latest_eval = None
        if eval_files:
            with open(eval_files[0], encoding="utf-8") as f:
                latest_eval = json.load(f)

        latest_benchmark = None
        if benchmark_files:
            with open(benchmark_files[0], encoding="utf-8") as f:
                latest_benchmark = json.load(f)

        # Read the markdown summary
        summary_path = results_dir / "BENCHMARK_RESULTS.md"
        summary_md = ""
        if summary_path.exists():
            summary_md = summary_path.read_text(encoding="utf-8")

        return {
            "has_results": latest_eval is not None or latest_benchmark is not None,
            "latest_eval": latest_eval,
            "latest_benchmark": latest_benchmark,
            "summary_markdown": summary_md,
            "rankings": _extract_rankings(summary_md),
            "key_findings": _extract_findings(summary_md),
        }


    def _extract_rankings(md: str) -> list[dict]:
        """Parse the rankings table from the benchmark markdown."""
        import re
        rankings = []
        in_rankings = False
        for line in md.split("\n"):
            if "| Rank |" in line:
                in_rankings = True
                continue
            if in_rankings and line.startswith("|"):
                if "---" in line:
                    continue
                parts = [p.strip().strip("*") for p in line.split("|")[1:-1]]
                if len(parts) >= 5:
                    try:
                        rankings.append({
                            "rank": int(parts[0]),
                            "configuration": parts[1],
                            "recall_at_10": parts[2],
                            "mrr": parts[3],
                            "hit_rate": parts[4],
                            "latency": parts[5] if len(parts) > 5 else "",
                        })
                    except (ValueError, IndexError):
                        pass
            elif in_rankings and not line.startswith("|"):
                break
        return rankings

    def _extract_findings(md: str) -> list[str]:
        """Extract key finding headings from the benchmark markdown."""
        import re
        findings = []
        for line in md.split("\n"):
            match = re.match(r"^### \d+\.\s+(.+)", line)
            if match:
                findings.append(match.group(1))
        return findings

    @app.post("/search")
    def search_documents(query: str, k: int = 10, mode: str = "rrf", rag: bool = False, model: str = ""):
        """Search across indexed ICD documents, optionally with RAG.

        model: optional config name (e.g. "titan-v2-sliding", "cohere-en-paragraph").
               Empty string = use best config from evaluation.
        """
        from src.search.config import SearchConfig, ALL_CONFIGS, TITAN_V2_SLIDING
        from src.search.retrieval import RetrievalMode

        mode_map = {
            "keyword": RetrievalMode.KEYWORD_ONLY,
            "vector": RetrievalMode.VECTOR_ONLY,
            "hybrid": RetrievalMode.HYBRID,
            "rrf": RetrievalMode.HYBRID_RRF,
        }
        retrieval_mode = mode_map.get(mode, RetrievalMode.HYBRID_RRF)

        # Select the index config based on model parameter
        selected_config = TITAN_V2_SLIDING  # default
        if model:
            for cfg in ALL_CONFIGS:
                if cfg.name == model:
                    selected_config = cfg
                    break

        search_config = SearchConfig(
            opensearch_host=os.environ.get("OPENSEARCH_HOST", "localhost"),
            opensearch_port=int(os.environ.get("OPENSEARCH_PORT", "9200")),
            opensearch_scheme=os.environ.get("OPENSEARCH_SCHEME", "http"),
            aws_region="us-east-1",
        )

        if rag:
            from src.search.rag import RAGPipeline
            pipeline = RAGPipeline(search_config=search_config, region="us-east-1")
            answer = pipeline.ask(query, k=k, mode=retrieval_mode)

            # Record RAG cost
            if answer.cost_usd > 0:
                _record_cost(
                    operation="rag_generation",
                    description=f"Search (RAG): \"{query[:60]}\"",
                    model=answer.model_id or "us.amazon.nova-pro-v1:0",
                    cost_usd=answer.cost_usd,
                    tokens_in=answer.tokens_in,
                    tokens_out=answer.tokens_out,
                    chunks_processed=answer.chunks_used,
                )

            return {
                "type": "rag",
                "query": query,
                "answer": answer.answer,
                "confidence": answer.confidence,
                "citations": [
                    {
                        "label": c.label,
                        "document_title": c.document_title,
                        "page_number": c.page_number,
                        "section_heading": c.section_heading,
                        "chunk_text": c.chunk_text,
                    }
                    for c in answer.citations
                ],
                "warnings": answer.warnings,
                "cost_usd": answer.cost_usd,
                "time_ms": answer.total_time_ms,
            }
        else:
            from src.search.pipeline import SearchPipeline
            pipeline = SearchPipeline(config=search_config, region="us-east-1")
            result = pipeline.search(query, k=k, mode=retrieval_mode)
            return {
                "type": "search",
                "query": query,
                "total_hits": result.total_hits,
                "took_ms": result.took_ms,
                "hits": [
                    {
                        "chunk_id": h.chunk_id,
                        "text": h.text,
                        "score": h.score,
                        "document_title": h.document_title,
                        "page_number": h.page_number,
                        "section_heading": h.section_heading,
                        "content_type": h.content_type,
                    }
                    for h in result.hits
                ],
            }

    # ─── TBD Dashboard ───────────────────────────────────────────────

    @app.get("/tbd-dashboard")
    def get_tbd_dashboard(status: str | None = None, item_type: str | None = None,
                          document: str | None = None):
        """Get TBD dashboard data with optional filters."""
        from src.search.config import SearchConfig
        from src.search.tbd_dashboard import TBDDashboard

        search_config = SearchConfig(
            opensearch_host=os.environ.get("OPENSEARCH_HOST", "localhost"),
            opensearch_port=int(os.environ.get("OPENSEARCH_PORT", "9200")),
            opensearch_scheme=os.environ.get("OPENSEARCH_SCHEME", "http"),
            aws_region="us-east-1",
        )
        dashboard = TBDDashboard(search_config=search_config, region="us-east-1")

        items = dashboard.filter_items(
            status=status,
            item_type=item_type,
            document=document,
        )
        stats = dashboard.get_stats()

        return {
            "stats": {
                "total_items": stats.total_items,
                "open_count": stats.open_count,
                "assigned_count": stats.assigned_count,
                "resolved_count": stats.resolved_count,
                "verified_count": stats.verified_count,
                "tbd_count": stats.tbd_count,
                "tbr_count": stats.tbr_count,
                "in_shall_statements": stats.in_shall_statements,
                "correlated_pairs": stats.correlated_pairs,
                "conflicts": stats.conflicts,
                "documents_count": stats.documents_count,
            },
            "items": [
                {
                    "item_id": item.item_id,
                    "item_type": item.item_type,
                    "status": item.status,
                    "document_title": item.document_title,
                    "page_number": item.page_number,
                    "section_heading": item.section_heading,
                    "context": item.context,
                    "owner": item.owner,
                    "in_shall_statement": item.in_shall_statement,
                    "correlated_items": item.correlated_items,
                    "resolution_value": item.resolution_value,
                }
                for item in items
            ],
            "correlations": [
                {
                    "item_a_id": c.item_a_id,
                    "item_b_id": c.item_b_id,
                    "confidence": c.confidence,
                    "conflict": c.conflict,
                    "conflict_detail": c.conflict_detail,
                }
                for c in dashboard._correlations
            ],
        }

    @app.post("/tbd-dashboard/ingest")
    def ingest_tbd_documents():
        """Ingest TBDs from all Document IR files in output/."""
        from pathlib import Path
        from src.search.config import SearchConfig
        from src.search.tbd_dashboard import TBDDashboard

        search_config = SearchConfig(
            opensearch_host=os.environ.get("OPENSEARCH_HOST", "localhost"),
            opensearch_port=int(os.environ.get("OPENSEARCH_PORT", "9200")),
            opensearch_scheme=os.environ.get("OPENSEARCH_SCHEME", "http"),
            aws_region="us-east-1",
        )
        dashboard = TBDDashboard(search_config=search_config, region="us-east-1")

        output_dir = Path("output")
        ir_files = list(output_dir.glob("*_document_ir.yaml"))
        total = 0
        for ir_path in ir_files:
            count = dashboard.ingest_document(ir_path)
            total += count
        dashboard.save_state()

        return {"status": "ingested", "new_items": total, "total_files": len(ir_files)}

    @app.put("/tbd-dashboard/item/{item_id}")
    def update_tbd_item(item_id: str, status: str | None = None,
                        owner: str | None = None,
                        resolution_value: str | None = None):
        """Update a TBD item's status/owner."""
        from src.search.config import SearchConfig
        from src.search.tbd_dashboard import TBDDashboard

        search_config = SearchConfig(
            opensearch_host=os.environ.get("OPENSEARCH_HOST", "localhost"),
            opensearch_port=int(os.environ.get("OPENSEARCH_PORT", "9200")),
            opensearch_scheme=os.environ.get("OPENSEARCH_SCHEME", "http"),
            aws_region="us-east-1",
        )
        dashboard = TBDDashboard(search_config=search_config, region="us-east-1")

        if status:
            success = dashboard.update_status(item_id, status=status, owner=owner,
                                              resolution_value=resolution_value)
            if not success:
                raise HTTPException(404, f"TBD item {item_id} not found")
        return {"status": "updated", "item_id": item_id}

    # ─── Version Detection & Diff ────────────────────────────────

    @app.get("/documents/families")
    def get_document_families():
        """Detect document version families in the corpus."""
        from src.version_diff import detect_families
        families = detect_families()
        return {
            "families": [
                {
                    "base_name": f.base_name,
                    "status": f.status,
                    "versions": [
                        {
                            "path": v.path,
                            "filename": v.filename,
                            "page_count": v.page_count,
                            "revision": v.revision,
                            "date": v.date,
                            "doc_type": v.doc_type,
                        }
                        for v in f.versions
                    ],
                }
                for f in families
            ]
        }

    @app.get("/documents/related")
    def get_related_versions(pdf_path: str):
        """Check if a specific document has related versions.

        Called when a document is opened — returns related versions if any.
        """
        from pathlib import Path
        from src.version_diff import detect_families, normalize_stem

        current_stem = normalize_stem(Path(pdf_path).name)
        families = detect_families()

        for family in families:
            if family.base_name == current_stem:
                other_versions = [
                    {
                        "path": v.path,
                        "filename": v.filename,
                        "page_count": v.page_count,
                        "revision": v.revision,
                        "doc_type": v.doc_type,
                    }
                    for v in family.versions
                    if str(Path(v.path).resolve()) != str(Path(pdf_path).resolve())
                ]
                if other_versions:
                    return {
                        "has_related": True,
                        "family_name": family.base_name,
                        "status": family.status,
                        "other_versions": other_versions,
                    }

        return {"has_related": False}

    @app.post("/documents/diff")
    def run_version_diff(version_a: str, version_b: str,
                         format: str = "markdown"):
        """Run differential analysis between two document versions.

        Returns structured diff report with progressive disclosure:
        - Level 1: Summary (always free)
        - Level 2: Per-section details (always free)
        - Level 3: AI summaries (on demand via /documents/diff/summarize)
        """
        from pathlib import Path
        from src.version_diff import full_diff, generate_report, quick_compare

        path_a = Path(version_a)
        path_b = Path(version_b)

        if not path_a.exists():
            raise HTTPException(404, f"File not found: {version_a}")
        if not path_b.exists():
            raise HTTPException(404, f"File not found: {version_b}")

        # Quick compare first
        quick = quick_compare(path_a, path_b)

        # Full diff
        report = full_diff(path_a, path_b)

        # Generate formatted report
        formatted = generate_report(report, format=format)

        return {
            "quick_compare": quick,
            "summary": {
                "sections_modified": report.sections_modified,
                "sections_added": report.sections_added,
                "sections_removed": report.sections_removed,
                "requirement_changes": report.requirement_changes,
                "tbd_changes": report.tbd_changes,
                "editorial_changes": report.editorial_changes,
                "text_overlap": report.text_overlap,
                "total_diff_tokens": report.total_diff_tokens,
                "estimated_llm_cost": round(report.total_diff_tokens * 0.00006 / 1000, 5),
            },
            "diffs": [
                {
                    "section_heading": d.section_heading,
                    "change_type": d.change_type,
                    "classification": d.classification,
                    "has_requirement_change": d.has_requirement_change,
                    "has_tbd_change": d.has_tbd_change,
                    "page_old": d.page_old,
                    "page_new": d.page_new,
                    "old_text": d.old_text[:300],
                    "new_text": d.new_text[:300],
                    "ai_summary": d.ai_summary,
                }
                for d in report.diffs
            ],
            "tbd_sections": [
                {
                    "section_heading": d.section_heading,
                    "change_type": d.change_type,
                    "new_text": d.new_text[:200],
                }
                for d in report.diffs if d.has_tbd_change
            ],
            "formatted_report": formatted,
        }

    @app.post("/documents/diff/summarize")
    def summarize_diff_section(version_a: str, version_b: str,
                               section_heading: str):
        """AI-summarize a single diff section (on-demand, shows cost).

        Progressive disclosure Level 3: only called when user clicks
        'Summarize with AI' on a specific section.
        """
        import json
        import boto3
        from pathlib import Path
        from src.version_diff import full_diff

        path_a = Path(version_a)
        path_b = Path(version_b)
        if not path_a.exists() or not path_b.exists():
            raise HTTPException(404, "File not found")

        report = full_diff(path_a, path_b)

        # Find the requested section
        target_diff = None
        for d in report.diffs:
            if d.section_heading.lower().strip() == section_heading.lower().strip():
                target_diff = d
                break

        if not target_diff:
            raise HTTPException(404, f"Section not found: {section_heading}")

        # Build LLM prompt (minimal — just the diff hunk)
        prompt = (
            f"Section: {target_diff.section_heading}\n"
            f"Change type: {target_diff.change_type}\n"
        )
        if target_diff.old_text:
            prompt += f"Old text: {target_diff.old_text[:500]}\n"
        if target_diff.new_text:
            prompt += f"New text: {target_diff.new_text[:500]}\n"
        prompt += "\nClassify this change (editorial/technical/structural) and explain its impact in 2-3 sentences."

        # Call Bedrock (Nova Lite for cheapest option)
        try:
            bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
            body = {
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {"maxTokens": 256, "temperature": 0.1},
            }
            resp = bedrock.invoke_model(
                modelId="us.amazon.nova-lite-v1:0",
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
            result = json.loads(resp["body"].read())
            summary = ""
            for block in result.get("output", {}).get("message", {}).get("content", []):
                if "text" in block:
                    summary += block["text"]

            usage = result.get("usage", {})
            cost = (usage.get("inputTokens", 0) * 0.00006 + usage.get("outputTokens", 0) * 0.00025) / 1000

            return {
                "section_heading": section_heading,
                "ai_summary": summary,
                "cost_usd": round(cost, 6),
                "tokens_in": usage.get("inputTokens", 0),
                "tokens_out": usage.get("outputTokens", 0),
            }
        except Exception as e:
            return {
                "section_heading": section_heading,
                "ai_summary": None,
                "error": str(e),
                "cost_usd": 0,
            }

    return app


# Entry point for running directly
app = create_app()
