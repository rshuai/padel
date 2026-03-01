# Consolidation Logic Flow

## 1. Clarification Gate (Hard Stop)
System checks:
1. Reporting period start/end
2. Presentation currency
3. Intercompany method
4. Included entities and required metadata
5. Mapping file present
6. TB/GL file present for each in-scope entity

If any item missing, status remains `CLARIFICATION_PENDING` and processing is blocked.

## 2. Data Normalization
1. Parse TB/GL (CSV/XLSX)
2. Standardize signed balance format (`period_amount`)
3. Validate source balance (debit-credit / net zero)
4. Persist normalized rows with row-level provenance

## 3. Account Mapping
1. Load COA mapping file
2. Resolve entity-specific mapping first, then global mapping
3. Flag duplicates/conflicts/unmapped accounts
4. Block processing on mapping defects

## 4. FX Translation
For each mapped row:
1. Choose rate by translation policy
   - Balance sheet: closing
   - Income statement: average
   - Equity: historical
2. Apply USD translation
3. Persist FX metadata on each translated row
4. Compute CTA as balancing difference and post CTA journal

## 5. Consolidation
1. Aggregate translated balances by group account
2. Apply intercompany eliminations (account-tag or counterparty method)
3. Apply NCI allocation journals for partially owned entities
4. Persist all journals with source tag

## 6. Controls & Validation
1. Consolidated TB net to zero
2. CTA reconciliation (journal vs TB)
3. Retained earnings movement (if tagged accounts exist)
4. Unusual variance flags (median-based threshold)

Blocking control failures set engagement status to `BLOCKED`.

## 7. Outputs
Generated artifacts:
1. Consolidated trial balance (USD)
2. Consolidated income statement
3. Consolidated balance sheet
4. Consolidation journal log
5. FX translation report
6. Exception and validation report
7. Template-formatted reporting pack (XLSX) when template is uploaded
