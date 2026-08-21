"""User Guide Regression: Undo/Redo + Session Management (Section 4.7-4.8)

Validates session management workflow described in the User Guide:
- Undo available after edit
- Redo available after undo
- Save session creates a .icd-session file
- Load session restores document + edit count
- New session resets all state

Tests use HSI_SYS_015G.pdf for editing operations.
"""

import shutil
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.app import create_app

ICDS_DIR = Path(__file__).parent.parent.parent / "icds" / "digital"
HSI_PDF = ICDS_DIR / "HSI_SYS_015G.pdf"


def _fresh_client(pdf_path: Path) -> TestClient:
    """Create a test client with an isolated copy of the PDF."""
    output_dir = Path("output")
    output_dir.mkdir(parents=True, exist_ok=True)
    test_copy = output_dir / f".test_sess_{uuid.uuid4().hex[:8]}_{pdf_path.name}"
    shutil.copy2(str(pdf_path), str(test_copy))

    app = create_app()
    client = TestClient(app)
    client.post("/session/start")
    res = client.post(f"/document/open?pdf_path={test_copy}")
    assert res.status_code == 200
    return client


def _get_first_editable_block(client: TestClient, page_num: int) -> dict | None:
    """Get the first editable block on a page."""
    res = client.get(f"/document/page/{page_num}/elements")
    assert res.status_code == 200
    elements = res.json()["elements"]
    for elem in elements:
        if elem["id"] and elem.get("type") in ("paragraph", "heading", "caption"):
            return elem
    return None


def _apply_edit(client: TestClient, page_num: int = 5, text: str = "SESSION_TEST") -> str:
    """Apply an edit and return the block ID."""
    block = _get_first_editable_block(client, page_num)
    assert block is not None, f"No editable block found on page {page_num}"
    block_id = block["id"]
    res = client.put(
        f"/document/block/{block_id}",
        json={"new_text": text},
    )
    assert res.status_code == 200
    return block_id


# ─── Undo Availability ────────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestUndoAvailableAfterEdit:
    """Verify undo becomes available after an edit."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_no_undo_before_edit(self, client):
        """Initially, undo is not available."""
        res = client.get("/session/actions")
        assert res.status_code == 200
        assert res.json()["undo_available"] is False

    def test_undo_available_after_edit(self, client):
        """After an edit, journal shows undo_available=True."""
        _apply_edit(client)

        res = client.get("/session/actions")
        assert res.status_code == 200
        assert res.json()["undo_available"] is True


# ─── Redo Availability ────────────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestRedoAvailableAfterUndo:
    """Verify redo becomes available after an undo."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_no_redo_before_undo(self, client):
        """Before any undo, redo is not available."""
        _apply_edit(client)

        res = client.get("/session/actions")
        assert res.json()["redo_available"] is False

    def test_redo_available_after_undo(self, client):
        """After undo, redo_available=True."""
        _apply_edit(client)
        client.post("/document/undo")

        res = client.get("/session/actions")
        assert res.status_code == 200
        assert res.json()["redo_available"] is True


# ─── Save Session Creates File ────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestSaveSessionCreatesFile:
    """Verify session save creates a .icd-session file."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_save_session_creates_file(self, client):
        """POST /session/save-as creates a .icd-session file on disk."""
        _apply_edit(client)

        session_name = f"test_session_{uuid.uuid4().hex[:8]}"
        res = client.post(f"/session/save-as?filename={session_name}")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "saved"
        assert session_name in data["filename"]

        # Verify file exists
        saved_path = Path(data["path"])
        assert saved_path.exists(), f"Session file not found at {saved_path}"

        # Cleanup
        saved_path.unlink(missing_ok=True)

    def test_save_session_has_correct_extension(self, client):
        """Saved session file has .icd-session extension."""
        _apply_edit(client)

        session_name = f"test_ext_{uuid.uuid4().hex[:8]}"
        res = client.post(f"/session/save-as?filename={session_name}")
        data = res.json()
        assert data["filename"].endswith(".icd-session")

        # Cleanup
        Path(data["path"]).unlink(missing_ok=True)


# ─── Load Session Restores State ──────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestLoadSessionRestoresState:
    """Verify loading a saved session restores document and edit count."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_load_session_restores_state(self, client):
        """POST /session/load restores document + edit count from saved session."""
        # Make an edit and save
        _apply_edit(client, text="LOAD_TEST_CONTENT")

        session_name = f"test_load_{uuid.uuid4().hex[:8]}"
        save_res = client.post(f"/session/save-as?filename={session_name}")
        assert save_res.status_code == 200
        saved_filename = save_res.json()["filename"]

        # Get state before reset
        session_before = client.get("/session").json()
        edit_count_before = session_before["edit_count"]

        # Start a fresh session (simulates closing and reopening)
        client.post("/session/start")

        # Load the saved session
        load_res = client.post(f"/session/load?filename={saved_filename}")
        assert load_res.status_code == 200
        load_data = load_res.json()
        assert load_data["status"] == "loaded"
        assert load_data["edit_count"] == edit_count_before

        # Cleanup
        sessions_dir = Path("sessions")
        (sessions_dir / saved_filename).unlink(missing_ok=True)

    def test_load_session_lists_available_files(self, client):
        """GET /session/files lists saved session files."""
        # Save a session first
        _apply_edit(client)
        session_name = f"test_list_{uuid.uuid4().hex[:8]}"
        save_res = client.post(f"/session/save-as?filename={session_name}")
        saved_filename = save_res.json()["filename"]

        # List sessions
        res = client.get("/session/files")
        assert res.status_code == 200
        data = res.json()
        assert "files" in data
        filenames = [f["filename"] for f in data["files"]]
        assert saved_filename in filenames

        # Cleanup
        sessions_dir = Path("sessions")
        (sessions_dir / saved_filename).unlink(missing_ok=True)


# ─── New Session Resets State ─────────────────────────────────────────


@pytest.mark.skipif(not HSI_PDF.exists(), reason="HSI PDF not found")
class TestNewSessionResetsState:
    """Verify starting a new session clears all state."""

    @pytest.fixture
    def client(self):
        return _fresh_client(HSI_PDF)

    def test_new_session_resets_state(self, client):
        """POST /session/start clears all editing state."""
        # Make some edits
        _apply_edit(client, text="RESET_TEST_1")
        _apply_edit(client, text="RESET_TEST_2")

        # Verify we have edits
        session_res = client.get("/session")
        assert session_res.json()["edit_count"] >= 2

        # Start a new session
        new_res = client.post("/session/start")
        assert new_res.status_code == 200
        assert "session_id" in new_res.json()

        # Verify state is clean
        session_res = client.get("/session")
        assert session_res.status_code == 200
        assert session_res.json()["edit_count"] == 0
        assert session_res.json()["action_count"] == 0

    def test_new_session_clears_undo_redo(self, client):
        """A new session has no undo/redo history."""
        _apply_edit(client)
        client.post("/document/undo")

        # Confirm redo is available
        actions = client.get("/session/actions").json()
        assert actions["redo_available"] is True

        # Start fresh
        client.post("/session/start")

        # After new session, no actions endpoint should show clean state
        actions = client.get("/session/actions").json()
        assert actions["undo_available"] is False
        assert actions["redo_available"] is False
