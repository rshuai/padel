# Database Schema

## Core Tables

| Table | Purpose | Key Columns |
|---|---|---|
| `engagements` | Consolidation run context and status | `id`, `name`, `status`, `reporting_period_start`, `reporting_period_end`, `presentation_currency` |
| `entities` | Scope entities and ownership metadata | `id`, `engagement_id`, `functional_currency`, `ownership_pct`, `has_nci`, `include_in_scope` |
| `uploaded_files` | Source/report template evidence | `id`, `engagement_id`, `entity_id`, `file_type`, `storage_path`, `checksum_sha256` |
| `clarification_items` | Required Q&A snapshot before processing | `engagement_id`, `key`, `value` |

## Processing Tables

| Table | Purpose | Key Columns |
|---|---|---|
| `coa_mappings` | Local-to-group mapping and FX policy | `engagement_id`, `entity_id`, `local_account_code`, `group_account_code`, `translation_policy` |
| `normalized_balances` | Normalized TB/GL rows | `engagement_id`, `entity_id`, `account_code`, `period_amount`, `debit`, `credit` |
| `fx_rates` | FX source audit trail and overrides | `engagement_id`, `entity_id`, `rate_type`, `rate_date`, `rate`, `source`, `is_override` |
| `translated_balances` | USD translated mapped balances | `engagement_id`, `entity_id`, `group_account_code`, `usd_amount`, `fx_rate`, `translation_policy` |
| `consolidation_journals` | CTA/NCI/elimination journals | `engagement_id`, `journal_type`, `debit_account`, `credit_account`, `amount_usd` |
| `control_exceptions` | Validation failures and warnings | `engagement_id`, `category`, `blocking`, `severity`, `message` |
| `output_artifacts` | Generated report files | `id`, `engagement_id`, `artifact_type`, `file_path` |
| `audit_events` | User/system action logs | `engagement_id`, `event_type`, `actor`, `payload_json` |

## Integrity Rules
1. One engagement has many entities/files/rates/journals/exceptions/artifacts.
2. Entity source files are mandatory for in-scope entities.
3. Mapping conflicts and unmapped accounts raise blocking exceptions.
4. Every manual FX override is persisted as a distinct row (`is_override = true`) to preserve base history.
