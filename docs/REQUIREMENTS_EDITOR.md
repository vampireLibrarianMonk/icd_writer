# Requirements: ICD Editor User Interaction

## 1. Problem Statement

ICDs are living documents. As systems evolve, interfaces change, requirements update, and new revisions are published. Currently this means:

1. Find the original Word/PDF file
2. Manually locate the section needing change
3. Edit in Word (if you have it and the original file)
4. Re-export to PDF
5. Distribute and track which version everyone has

This process breaks when:
- The original Word file is lost (only PDF exists)
- Multiple stakeholders need to propose changes
- Changes need traceability (who changed what, when, why)
- You need to find all places affected by an interface change
- Revision comparison is needed between versions

## 2. User Roles

| Role | Needs |
|------|-------|
| **ICD Author** | Edit text, update requirements, add/remove interfaces, publish new revisions |
| **Systems Engineer** | Search requirements, trace interfaces, compare revisions, propose changes |
| **Reviewer** | View proposed changes, approve/reject edits, comment on specific sections |
| **Program Manager** | Track open TBDs/TBRs, see change history, generate status reports |

## 3. Core User Stories

### 3.1 Document Ingestion

> As an ICD Author, I want to upload a PDF and have it automatically converted into an editable form, so I can make updates without needing the original Word file.

**Acceptance:**
- Upload PDF via web UI or CLI
- Pipeline runs automatically
- User sees the document rendered in the browser alongside the editable IR
- Pipeline report (visual fidelity, text accuracy) is generated and visible

### 3.2 Text Editing

> As an ICD Author, I want to click on a text block in the document view and edit its content, then see the change reflected in a re-rendered PDF.

**Acceptance:**
- Click on any text span in the rendered view
- Edit panel shows the text with its metadata (font, size, page, section)
- Save triggers re-render of the affected page
- Diff view shows before/after

**Constraints:**
- Edits stay within the text span's allocated width (or auto-adjust positioning)
- Font style (bold, italic, size) is preserved unless explicitly changed
- Change is recorded with timestamp and user identity

### 3.3 Requirement Updates

> As a Systems Engineer, I want to update a requirement's text and have the system track that it changed, linking the new text to the old version.

**Acceptance:**
- Requirements are identified and listed (extracted from "shall" statements)
- Edit a requirement's text
- System stores: old text, new text, who changed it, when, revision tag
- Verification method and interfaces linked to this requirement are flagged for review

### 3.4 Search and Discovery

> As a Systems Engineer, I want to search across the entire ICD for all references to a specific interface, signal, or system name.

**Acceptance:**
- Full-text search across all text blocks
- Filter by: page, section, requirement type, interface
- Results show context (surrounding text) and link to page view
- Highlight matches in the document view

### 3.5 Revision Comparison

> As a Reviewer, I want to compare two revisions of an ICD and see exactly what changed — added requirements, modified text, removed sections.

**Acceptance:**
- Select two versions (by revision tag or date)
- Side-by-side view with changes highlighted
- Summary: N requirements added, M modified, K deleted
- Export change report as PDF or markdown

### 3.6 TBD/TBR Tracking

> As a Program Manager, I want to see all open TBD and TBR items across the ICD with their status and resolution target dates.

**Acceptance:**
- Automatic detection of TBD, TBR, TBC, TBS in requirement text
- Dashboard showing all open items
- Each item linked to its requirement and page
- Status tracking: open → in-progress → resolved
- Export as table (CSV/Excel)

### 3.7 Multi-User Collaboration

> As a Reviewer, I want to see proposed changes from the author, add comments, and approve or reject individual edits.

**Acceptance:**
- Change proposals are visible before being applied
- Comment threads on any text block or requirement
- Approve/reject per-change
- Approved changes automatically re-render affected pages
- Audit log of all actions

## 4. What Gets Updated in a Living ICD

Based on typical NASA ICD lifecycle:

| Category | Examples | Frequency |
|----------|----------|-----------|
| **Requirements** | "shall" text changes, new requirements added, obsolete ones removed | Every revision |
| **Interface definitions** | Protocol changes, data rate updates, new message types | Major revisions |
| **Signal/message fields** | Bit offsets change, new fields added, units corrected | Frequent |
| **Verification methods** | Test → Analysis, new verification requirements | Occasional |
| **System names** | Subsystem renamed, new component added | Rare |
| **Tables** | Packet definitions updated, timing tables changed | Every revision |
| **Diagrams** | Architecture changes, new connections, removed subsystems | Major revisions |
| **Administrative** | Revision date, author, approval signatures, change log | Every revision |
| **TBD resolution** | Placeholder values replaced with final numbers | Throughout lifecycle |
| **Acronyms/definitions** | New terms added as system evolves | Occasional |

## 5. Data Model for Change Tracking

```yaml
changes:
  - id: CHG-001
    timestamp: "2026-08-01T14:30:00Z"
    user: "jane.engineer@nasa.gov"
    revision: "D"
    type: requirement_text_change
    target:
      requirement_id: REQ-CMD-001
      page: 12
      block_id: block-p12-b07
    before:
      text: "The flight computer shall accept command transfer frames."
    after:
      text: "The flight computer shall accept and validate command transfer frames."
    rationale: "Added validation per FT3 test findings"
    status: approved
    approved_by: "john.lead@nasa.gov"
    approved_at: "2026-08-02T09:15:00Z"
```

## 6. UI Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Navigation Bar                                              │
│  [Documents] [Search] [Changes] [TBD Tracker] [Settings]    │
├──────────────────────────┬──────────────────────────────────┤
│                          │                                   │
│  Document View           │  Edit Panel                       │
│  (PDF.js rendering of    │  - Text editor                    │
│   the current page)      │  - Metadata (font, size, type)    │
│                          │  - Requirement fields              │
│  ┌──────────────────┐    │  - Interface links                │
│  │                  │    │  - Change history                  │
│  │  [Page content]  │    │  - Comments                       │
│  │  Click to select │    │                                   │
│  │  any text block  │    │  ┌─────────────────────────┐     │
│  │                  │    │  │ "The flight computer     │     │
│  │                  │    │  │  shall accept and        │     │
│  │                  │    │  │  validate command..."     │     │
│  └──────────────────┘    │  └─────────────────────────┘     │
│                          │                                   │
│  [◀ Prev] Page 12 [▶]   │  [Save] [Revert] [Render Preview] │
├──────────────────────────┴──────────────────────────────────┤
│  Status: 3 pending changes | Last rendered: 2m ago           │
└─────────────────────────────────────────────────────────────┘
```

## 7. Technical Requirements for the Editor

### 7.1 Backend (FastAPI)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/documents` | POST | Upload and ingest a PDF |
| `/documents/{id}` | GET | Get document metadata and IR |
| `/documents/{id}/pages/{n}` | GET | Get page data (blocks, images) |
| `/documents/{id}/pages/{n}/render` | POST | Re-render a single page |
| `/documents/{id}/blocks/{id}` | PUT | Edit a text block |
| `/documents/{id}/requirements` | GET | List all requirements |
| `/documents/{id}/requirements/{id}` | PUT | Update a requirement |
| `/documents/{id}/changes` | GET | List change history |
| `/documents/{id}/changes` | POST | Propose a change |
| `/documents/{id}/changes/{id}/approve` | POST | Approve a change |
| `/documents/{id}/export` | POST | Export regenerated PDF |
| `/search` | GET | Full-text search across documents |

### 7.2 Storage

| Data | Where | Why |
|------|-------|-----|
| Original PDFs | S3 | Immutable source artifacts |
| Document IR (YAML) | S3 + Git | Version-controlled canonical source |
| Change records | PostgreSQL | Queryable, relational |
| Search index | OpenSearch | Fast full-text + semantic search |
| Rendered PDFs | S3 | Cached outputs, regenerable |
| User sessions | Redis/DynamoDB | Ephemeral |

### 7.3 Frontend (React + TypeScript)

- PDF.js for original document viewing
- Monaco editor (VS Code's editor) for text editing
- SVG overlays for bounding box visualization
- WebSocket for real-time collaboration status
- Diff rendering (similar to GitHub PR view)

## 8. MVP Scope (Phase 2 Minimum)

The minimum viable editor:

1. **Upload PDF** → pipeline ingests, produces IR
2. **View pages** in browser (rendered from IR)
3. **Click a text block** → see its content in an edit panel
4. **Edit text** → save to IR
5. **Re-render page** → see updated PDF
6. **Export** → download regenerated PDF with edits applied

What's deferred:
- Multi-user (single user first)
- Requirement extraction (manual tagging first)
- OpenSearch (simple in-memory search first)
- Bedrock integration (human-only edits first)
- Diagrams (text-only edits first)

## 9. Open Questions

1. **Git vs Database for IR storage?** Git gives version history for free but is harder for real-time collaboration. Database gives fast queries but needs explicit versioning.

2. **Selective re-rendering?** Currently the pipeline re-renders entire pages. For single-word edits, could we patch the PDF content stream directly (proven in our earlier experiment) to avoid re-rendering?

3. **Diagram editing?** When a user needs to add a new system to a block diagram, do we provide a drawing tool, or do they describe the change and we regenerate?

4. **Authority model?** Who can approve changes to normative requirements? Does this need CAC/PIV integration for NASA environments?

5. **Offline capability?** Should the editor work without network access (local mode) for classified environments?
