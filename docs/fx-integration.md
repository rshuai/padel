# FX API Integration Approach

## Source
- Provider: `Frankfurter` API (ECB reference rate feed).
- Endpoint pattern:
  - Range: `/YYYY-MM-DD..YYYY-MM-DD?from=XXX&to=USD`
  - Historical lookup: range ending at historical date.

## Rate Determination
1. **Closing rate**
   - Latest available quote on or before reporting end date.
   - Missing-day count = days between reporting end and quote date.
2. **Average rate**
   - Day-weighted average across full reporting period.
   - Non-quote days forward-filled from latest prior quote.
   - Missing-day count tracked for transparency.
3. **Historical rate**
   - Derived using account-level historical rate date from mapping.
   - Falls back to latest available prior quote if date is non-business day.

## Auditability
Each rate stored in `fx_rates` with:
- source,
- base/quote currency,
- rate type,
- effective date,
- methodology text,
- missing days,
- override flag and note.

## Manual Override Control
- Overrides inserted as additional rows (`is_override = true`).
- Retrieval logic prioritizes override over auto-fetched values.
- Original fetched values remain untouched for forensic trace.

## Failure Handling
- Any retrieval failure raises `FX_RETRIEVAL_FAILED` blocking exception.
- Processing halts if required FX rates are missing.
