# IASW Project End-to-End Functional Guide

## 1. Purpose of this document

This document is a detailed, file-by-file functional map of the IASW prototype in this repository.
It is intended to be machine-friendly and human-friendly so an AI system (or a new developer) can quickly understand:

- What the project does
- How data flows from intake to checker decision
- What each file is responsible for
- How HITL (Human-in-the-Loop) is enforced
- Which files are source code vs runtime-generated artifacts
- Where to modify behavior safely

This guide complements `README.md` and `docs/Solution_Design_and_Implementation.md`.

## 2. Project goal in one sentence

The application automates Legal Name Change request verification (digital Maker) and stages results for mandatory human Checker approval before any core banking write-call (mock RPS) is executed.

## 3. High-level end-to-end workflow

1. Staff submits intake form with customer details and an uploaded document.
2. Backend stores the file in uploads and starts the agent workflow.
3. Workflow runs sequential agent steps:
   - Validation Agent
   - Document Processor Agent
   - Confidence Scorer
   - Summary Agent
   - FileNet Mock Archiver
4. Backend writes a record to pending table with status `AI_VERIFIED_PENDING_HUMAN`.
5. Checker reviews queue and request detail screen.
6. Checker chooses `APPROVE` or `REJECT`.
7. If `APPROVE`, backend executes mock RPS write and marks record `APPROVED`.
8. If `REJECT`, backend marks record `REJECTED`.
9. Audit events are written at every critical step.

## 4. HITL control boundary (critical compliance rule)

### AI is allowed to:

- Validate and process intake
- Extract names from uploaded document
- Compute confidence and recommendation
- Generate review summary
- Archive document to FileNet mock
- Stage pending record

### AI is not allowed to:

- Finalize customer update
- Directly call RPS update
- Mark request as approved autonomously

### Enforcement in code

- The AI workflow ends before finalization.
- RPS write is only inside checker decision endpoint (`/checker/{request_id}/decision`) and only for `APPROVE`.

## 5. Runtime architecture and data movement

### Request path: Intake

- Browser submits multipart form to `POST /intake`.
- API generates `request_id` and `correlation_id`.
- Uploaded file is saved to `app/static/uploads/`.
- Audit event `intake_received` is written.
- LangGraph workflow is invoked with initial state.
- Final workflow state is used to persist DB row.
- DB row is staged as `AI_VERIFIED_PENDING_HUMAN`.
- Audit event `pending_record_created` is written.
- User is redirected to checker detail page.

### Request path: Checker decision

- Checker posts to `POST /checker/{request_id}/decision`.
- API validates request exists and is still pending.
- Decision stored in DB (`checker_decision`, `checker_comment`).
- On `APPROVE`:
  - `mock_rps_write()` runs
  - `rps_write_reference` saved
  - status changes to `APPROVED`
- On `REJECT`:
  - status changes to `REJECTED`
- Audit event `checker_decision_recorded` is written.

## 6. Code-level sequence of workflow nodes

Workflow graph order in `app/core/workflow.py`:

1. `intake_validation`
2. `document_processor`
3. `confidence_scorer`
4. `summary_agent`
5. `filenet_archiver`
6. END

Each node mutates a shared `WorkflowState` dictionary and emits an audit event.

## 7. File-by-file functional breakdown

## 7.1 Top-level files

### `README.md`

Primary quick-start and demonstration guide.
Contains:

- What prototype demonstrates
- Tech stack
- Install/run commands
- Demo scenario steps
- Important HITL rule and control boundary

### `requirements.txt`

Pinned Python dependencies used by the app:

- `fastapi`, `uvicorn`, `jinja2`, `python-multipart`
- `sqlalchemy`, `pydantic`
- `langgraph`

### `samples/marriage_certificate_demo.txt`

Deterministic sample document for demo extraction.
Contains fields parsed by document processor logic:

- `Bride Name: ...`
- `Married Name: ...`

## 7.2 Application package (`app/`)

### `app/__init__.py`

Empty package marker. No runtime logic.

### `app/main.py`

Main FastAPI application entry point.
Responsibilities:

- Create app and mount static files
- Initialize templates
- Build workflow (`build_workflow()`)
- Ensure DB tables exist (`Base.metadata.create_all`)
- Define all HTTP endpoints

Key endpoints:

- `GET /`: Intake UI
- `POST /intake`: Receives intake, saves upload, invokes workflow, creates pending DB row
- `GET /checker`: Checker queue list
- `GET /checker/{request_id}`: Checker detail view
- `POST /checker/{request_id}/decision`: Human decision endpoint; only place where RPS write can happen
- `GET /api/pending/{request_id}`: JSON representation for one request

Important behavior details:

- Request IDs are generated as `REQ-<10 hex>`.
- Correlation IDs are generated as `CORR-<10 hex>` for traceability across logs.
- Uploaded filename is normalized by replacing spaces with underscores.
- Pending row status is always initially `AI_VERIFIED_PENDING_HUMAN`.

### `app/core/__init__.py`

Empty package marker. No runtime logic.

### `app/core/config.py`

Central path configuration and directory bootstrap.
Defines:

- `BASE_DIR`
- `DATA_DIR`
- `UPLOAD_DIR`
- `FILENET_DIR`
- `DB_PATH`
- `AUDIT_LOG`

Creates directories at import time if missing:

- `data/`
- `app/static/uploads/`
- `app/static/filenet/`

### `app/core/db.py`

Database wiring (SQLAlchemy).
Responsibilities:

- Create SQLite engine with `check_same_thread=False`
- Configure session factory (`SessionLocal`)
- Declare shared ORM base class (`Base`)
- Provide dependency-injected DB session (`get_db()`)

### `app/core/models.py`

ORM data model for pending workflow records.
Defines `PendingRequest` table (`pending_requests`) with fields for:

- Request identity: `request_id`, `correlation_id`, `customer_id`, `change_type`
- Requested values: `old_name_requested`, `new_name_requested`
- Extracted values: `old_name_extracted`, `new_name_extracted`
- Scoring: `confidence_old_name`, `confidence_new_name`, `confidence_authenticity`
- Risk/recommendation: `forgery_check`, `recommended_action`
- AI output: `ai_summary`
- Workflow status: `overall_status`
- Document archive reference: `filenet_reference_id`
- Checker controls: `checker_decision`, `checker_comment`
- Core write trace: `rps_write_reference`
- Audit timestamps: `created_at`, `updated_at`

### `app/core/schemas.py`

Pydantic request schemas.

- `IntakeRequest`: shape of intake fields (`customer_id`, `old_name`, `new_name`)
- `CheckerDecision`: checker action payload (`decision`, optional `comment`)

Note: Intake endpoint currently binds form fields directly; schema exists for API contract clarity and future expansion.

### `app/core/services.py`

Service layer for reusable business logic and side-effect helpers.

Functions:

- `write_audit(event, correlation_id, payload)`
  - Appends JSON line to `data/audit.log`

- `parse_document_text(upload_path)`
  - Reads uploaded file as UTF-8 text (ignore decode errors)
  - Extracts names from lines containing `bride` / `old name` and `married` / `new name`
  - Returns extracted fields and authenticity heuristic (`PASS` if text length > 20 else `FLAG`)

- `score_fields(request_old, request_new, extracted_old, extracted_new, authenticity_flag)`
  - Produces deterministic score card:
    - old name match: 97 or 45
    - new name match: 97 or 40
    - authenticity: 85 or 55
  - Derives:
    - `forgery_check` = `PASS` if authenticity >= 80 else `FLAG`
    - `recommended_action` = `APPROVE` if name scores strong and forgery check pass else `REVIEW`

- `generate_summary(...)`
  - Builds checker-facing English summary from request, extracted values, and score card

- `archive_to_filenet_mock(upload_path, correlation_id)`
  - Creates FileNet-style ID (`FN-...`)
  - Copies upload to `app/static/filenet/`
  - Writes metadata JSON in same directory
  - Returns FileNet reference ID

- `mock_rps_write(customer_id, new_name, correlation_id)`
  - Generates mock core write reference (`RPS-...`)
  - Writes `rps_write_executed` audit event
  - Returns RPS reference

### `app/core/workflow.py`

LangGraph orchestration definition.

Contains:

- `WorkflowState` typed dictionary (shared state contract between nodes)
- Node functions:
  - `intake_validation`
  - `document_processor`
  - `confidence_scorer`
  - `summary_agent`
  - `filenet_archiver`
- `build_workflow()` to construct and compile directed graph

Graph is fully linear for deterministic behavior in this prototype.

## 7.3 Templates (`app/templates/`)

### `app/templates/intake.html`

Staff intake form screen.
Includes:

- Inputs for customer ID, old name, new name
- File upload control
- Submit action to `/intake`
- Link to checker queue
- Demo tip for deterministic extraction formatting

### `app/templates/checker_list.html`

Checker queue table.
Shows all requests from DB with:

- Request ID
- Customer ID
- Current status
- AI recommendation
- Link to review detail

### `app/templates/checker_detail.html`

Detailed checker review screen for one request.
Displays:

- Requested vs extracted names
- Confidence values
- Forgery check
- Recommended action
- AI summary
- FileNet ref and RPS ref

Decision controls shown only when status is pending:

- Approve button
- Reject button
- Optional checker comment

## 7.4 Static assets (`app/static/`)

### `app/static/styles.css`

Shared styling for all pages.
Defines:

- Color variables and layout tokens
- Panel/card layout
- Form and table styles
- Approve/reject visual affordances
- Responsive adjustments for small screens

### `app/static/uploads/`

Runtime upload staging area.
Contains user-submitted documents renamed with request prefix:

- `REQ-<id>-<filename>`

These are raw intake files before/alongside archive copy.

### `app/static/filenet/`

Mock FileNet archive store.
Per request, typically contains:

- Archived file: `FN-<id>-REQ-<id>-<filename>`
- Metadata JSON: `FN-<id>.json`

Metadata includes reference ID, source filename, archived path, correlation ID, and archive timestamp.

## 7.5 Data layer (`data/`)

### `data/iasw.db`

SQLite database file.
Stores `pending_requests` table with full request lifecycle and decision state.

### `data/audit.log`

Append-only JSONL event log for observability and compliance tracing.
Typical event order per request:

1. `intake_received`
2. `validation_agent_completed`
3. `document_processor_completed`
4. `confidence_scorer_completed`
5. `summary_agent_completed`
6. `filenet_archive_completed`
7. `pending_record_created`
8. `rps_write_executed` (approve path only)
9. `checker_decision_recorded`

## 7.6 Existing documentation (`docs/`)

### `docs/Solution_Design_and_Implementation.md`

Formal challenge submission narrative.
Covers:

- Executive summary
- Architecture overview
- HITL boundary
- Trade-offs
- Production hardening roadmap

## 8. API contract reference

### `POST /intake`

Type: multipart/form-data

Required fields:

- `customer_id`
- `old_name`
- `new_name`
- `document` (uploaded file)

Response:

- HTTP 303 redirect to `/checker/{request_id}`

### `GET /checker`

Returns rendered HTML queue view.

### `GET /checker/{request_id}`

Returns rendered HTML detail view.
404 if request not found.

### `POST /checker/{request_id}/decision`

Type: form data

Fields:

- `decision`: must be `APPROVE` or `REJECT` (case normalized)
- `comment`: optional

Rules:

- Only allowed when status is `AI_VERIFIED_PENDING_HUMAN`
- Approve triggers mock RPS write and status transition to `APPROVED`
- Reject transitions to `REJECTED`

Response:

- HTTP 303 redirect back to detail page

### `GET /api/pending/{request_id}`

Returns request record as JSON, including:

- Requested and extracted values
- Confidence and recommendation
- Current status
- FileNet reference
- Checker decision
- RPS reference
- AI summary

## 9. Status model and transitions

Initial staged status:

- `AI_VERIFIED_PENDING_HUMAN`

Final statuses:

- `APPROVED`
- `REJECTED`

Valid transitions:

- `AI_VERIFIED_PENDING_HUMAN` -> `APPROVED`
- `AI_VERIFIED_PENDING_HUMAN` -> `REJECTED`

Invalid transition behavior:

- Any further decision after finalization returns HTTP 400.

## 10. Deterministic scoring logic (for repeatable demos)

For exact request/extracted name match:

- Old name confidence = 97
- New name confidence = 97

For mismatch/missing extraction:

- Old name confidence = 45
- New name confidence = 40

Authenticity heuristic:

- `PASS` and score 85 when decoded text length > 20
- `FLAG` and score 55 otherwise

Recommendation:

- `APPROVE` if both name scores >= 90 and forgery check `PASS`
- Otherwise `REVIEW`

## 11. How to run and validate quickly

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start server:

```bash
uvicorn app.main:app --reload
```

3. Open intake page:

- `http://127.0.0.1:8000/`

4. Submit sample request with `samples/marriage_certificate_demo.txt`.

5. Review checker screen and approve.

6. Verify:

- Queue/detail status changes
- `data/audit.log` has the expected event sequence
- `app/static/filenet/` has new archive + metadata files
- `GET /api/pending/{request_id}` shows final record

## 12. File ownership map (where to edit for changes)

- Routing or endpoint behavior: `app/main.py`
- Agent order and orchestration: `app/core/workflow.py`
- Extraction/scoring/summary logic: `app/core/services.py`
- Data schema changes: `app/core/models.py`
- DB connection settings: `app/core/db.py`
- Path/location settings: `app/core/config.py`
- UI layout and controls: `app/templates/*.html`
- UI styling: `app/static/styles.css`
- Dependency versions: `requirements.txt`
- Functional and design docs: `README.md`, `docs/Solution_Design_and_Implementation.md`

## 13. Known implementation limits

- OCR and LLM are mocked by deterministic text parsing and rule logic.
- Uploaded binary PDFs/images are not truly OCR-processed in this prototype.
- No enterprise authentication/authorization layer is enforced in UI/API.
- SQLite is used for local demo, not production-grade scale.
- Workflow runs synchronously inside intake request.

## 14. Safe extension strategy

To add real AI while preserving architecture:

1. Replace `parse_document_text()` with OCR + LLM extraction but keep output contract unchanged.
2. Replace rule scoring in `score_fields()` with model-based scoring while preserving score card shape.
3. Add async queue worker around workflow invocation in `POST /intake`.
4. Add identity + role enforcement around checker endpoints.
5. Replace `mock_rps_write()` with real service adapter, preserving explicit human trigger rule.

## 15. Glossary

- IASW: Intelligent Account Servicing Workflow
- HITL: Human-in-the-Loop
- RPS: Core banking update interface (mocked in this project)
- FileNet mock: Local filesystem stand-in for enterprise document management
- Pending table: DB table holding AI-verified records awaiting human checker decision
- Correlation ID: Trace ID linking all logs and actions for one request

## 16. Summary for AI ingestion

If an AI system reads only this file, the key interpretation should be:

- This is a FastAPI + LangGraph prototype implementing digital Maker + mandatory human Checker.
- Workflow is deterministic and linear for reliable demos.
- AI-generated/staged results are never final until checker decision endpoint runs.
- RPS write-call is intentionally isolated to human approval path.
- Source-of-truth state is in SQLite table `pending_requests`, with JSONL audit trail for every major action.
