# System Architecture

## 1. Context
The platform is a controller-grade consolidation system designed for multi-entity upload, IFRS/UK GAAP FX translation, auditability, and controlled finalization.

## 2. Logical Components
1. **Web UI (`/frontend`)**
   - Guided workflow for engagement setup, entity definitions, file upload, clarification gate, FX transparency, override control, processing, and outputs.
2. **API Layer (`/backend/app/api/routes.py`)**
   - Validates requests, enforces security dependency, executes orchestration services.
3. **Workflow Orchestrator (`pipeline_service.py`)**
   - Enforces required clarifications/files before run.
   - Coordinates normalization, mapping, FX retrieval, translation, consolidation, controls, and report generation.
4. **Accounting Services**
   - `parser_service.py`: Xero-like TB/GL + mapping normalization.
   - `mapping_service.py`: mapping load + conflict detection.
   - `fx_service.py`: FX retrieval (Frankfurter ECB source), close/average/historical handling.
   - `translation_service.py`: policy-based translation + CTA posting.
   - `consolidation_service.py`: aggregation, intercompany eliminations, NCI journals.
   - `controls_service.py`: debit/credit, CTA, retained earnings movement, unusual variance checks.
   - `output_service.py`: output pack and artifact registration.
5. **Data Layer (SQLite for MVP)**
   - Full processing footprint persisted: source files, normalized rows, rates, translated balances, journals, exceptions, artifacts, audit events.
6. **Storage Layer**
   - Uploaded files and generated outputs stored under `data/uploads` and `data/outputs`.

## 3. Security Model (MVP)
- API-key gate via `X-API-Key` header.
- Input validation and explicit file type restrictions.
- Upload size limits (`CONSOL_MAX_UPLOAD_SIZE_MB`).
- SHA-256 checksums for uploaded files.
- SQLAlchemy ORM for query safety.
- Immutable audit events for critical actions.

## 4. Production Security (Enterprise target)
- OIDC/SAML SSO + MFA.
- RBAC (Controller, Reviewer, Preparer, Auditor roles).
- Data encryption at rest (KMS) and in transit (TLS1.2+).
- Secrets manager integration.
- WORM/object-lock retention for source files and signed reports.
- Dual-approval workflow for manual FX overrides and consolidation journals.

## 5. Processing Sequence
1. Upload files tagged by entity.
2. Submit clarification package.
3. Clarification check enforces completeness.
4. FX retrieval pre-run with audit visibility and override option.
5. Consolidation run:
   - parse + validate source data,
   - map accounts,
   - apply FX translation,
   - calculate CTA,
   - aggregate and post eliminations,
   - compute NCI,
   - execute control checks,
   - generate outputs and exceptions.
6. If blocking exceptions exist, status is `BLOCKED`; finalization halted.

## 6. Deployment Topology
- **MVP:** single container/service running FastAPI + SQLite + shared local storage.
- **Enterprise:** stateless API services behind load balancer, PostgreSQL HA, object storage, queue workers for heavy runs, and external identity provider.
