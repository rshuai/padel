# Consolidation Controller (USD Group Reporting)

Secure web-based consolidation controller for multi-entity Xero exports with automated FX translation, audit trail, validation controls, and downloadable reporting pack outputs.

## What It Does
- Upload entity TB/GL files (CSV/XLSX), consolidation template, and COA mapping.
- Force a clarification stage before processing.
- Retrieve FX rates automatically (ECB reference via Frankfurter API).
- Apply translation logic:
  - Balance sheet accounts: closing rate
  - Income statement accounts: average rate
  - Equity accounts: historical rate
- Auto-calculate CTA.
- Run consolidation with intercompany elimination and NCI allocation.
- Halt finalization on blocking issues.
- Produce downloadable reports and full audit logs.

## Project Layout
- `/backend/app/main.py`: FastAPI application entrypoint
- `/backend/app/api/routes.py`: API endpoints and workflow gates
- `/backend/app/models.py`: relational schema
- `/backend/app/services/`: normalization, FX, translation, consolidation, controls, outputs
- `/frontend/`: browser UI
- `/docs/`: architecture, schema, logic flow, FX integration, MVP/enterprise specs

## Run Locally
1. Create environment and install backend deps.
2. Start server from repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

3. Open: `http://localhost:8000/`

## Environment Variables
Prefix: `CONSOL_`

- `CONSOL_ENVIRONMENT` (`dev` by default)
- `CONSOL_API_KEYS` (comma-separated keys)
- `CONSOL_ALLOW_NO_API_KEY_IN_DEV` (`true` by default)
- `CONSOL_DATABASE_URL` (`sqlite:///./data/consolidation.db`)
- `CONSOL_MAX_UPLOAD_SIZE_MB` (`50`)
- `CONSOL_CTA_ACCOUNT_CODE` (`3999-CTA`)

## Processing Controls
The engine blocks finalization when it detects any blocking exception, including:
- Missing clarification fields/files
- Unbalanced entity TB
- Mapping conflicts or unmapped accounts
- Missing FX rates
- Consolidated balance mismatch
- CTA reconciliation failure

## Output Artifacts
- Consolidated Trial Balance (USD)
- Consolidated Income Statement
- Consolidated Balance Sheet
- Consolidation Journal Log
- FX Translation Report
- Exception & Validation Report
- Template-formatted reporting pack (if XLSX template uploaded)

## Documentation
- `/docs/system-architecture.md`
- `/docs/database-schema.md`
- `/docs/fx-integration.md`
- `/docs/consolidation-logic-flow.md`
- `/docs/mvp-enterprise-spec.md`

## Katanox Basic App
- Open `http://localhost:8000/ui/katanox.html`.
- Enter your Katanox API token in the page (`raw token` or `Bearer ...` are both accepted).
- Use the built-in forms to:
  - list properties (`GET /properties`)
  - search availability (`GET /availability`)
  - fetch a booking (`GET /bookings/{booking_id}`)
  - create a booking (`POST /bookings`)

Optional settings:
- `CONSOL_KATANOX_BASE_URL` (default `https://api.katanox.com/v2`)
- `CONSOL_KATANOX_TIMEOUT_SECONDS` (default `30`)

Troubleshooting:
- If `http://localhost:8000/ui/katanox.html` does not load, make sure the backend is running on port `8000`.
- If you run with Docker, rebuild after code changes: `docker compose up --build`.
