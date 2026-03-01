# MVP vs Enterprise Specification

## MVP (Delivered Here)
1. Web UI + API workflow with mandatory clarification stage.
2. Multi-entity file upload (TB/GL/template/mapping).
3. Automated FX retrieval (ECB source via Frankfurter).
4. FX transparency table + manual override endpoint/UI.
5. Parsing and normalization of Xero-like exports.
6. Mapping validation with blocking exceptions.
7. Policy-based translation + CTA posting.
8. Consolidation with intercompany elimination + NCI allocation logic.
9. Control checks and status gating (`BLOCKED` vs `PROCESSED`).
10. Downloadable output artifacts and full audit trail.

## Enterprise-Scale Roadmap
1. **Security & Identity**
   - OIDC/SAML, MFA, SCIM provisioning, fine-grained RBAC.
2. **Workflow Governance**
   - Four-eyes approval for FX overrides and manual journals.
   - Locked period management and close checklist orchestration.
3. **Data & Performance**
   - PostgreSQL + partitioning + object storage.
   - Queue-driven processing for large group datasets.
   - Scenario versions and restatement support.
4. **Accounting Capabilities**
   - Full acquisition accounting and step-acquisition handling.
   - Elimination rule engine by partner/entity/document tags.
   - Multi-GAAP reporting views and dual-book logic.
5. **Monitoring & Compliance**
   - SIEM hooks, immutable audit export, SOC2 controls.
   - Data lineage catalog and signed output bundles.
6. **Template Intelligence**
   - Configurable template mappers and named-range binding.
   - Cell-level reconciliations back to journal and source rows.
