# Resilient Batch Research Implementation Plan

**Goal:** Preserve long-running marketplace research, expose every detected PN, and auto-create/reuse the finished Excel.

**Spec:** `docs/superpowers/specs/2026-09-14-resilient-batch-research-design.md`

## Task 1 — Job lifecycle
- Add failing tests for RUNNING jobs surviving TTL, terminal TTL starting at `finished_at`, and manifest recovery.
- Implement lifecycle state/timestamps and JSON manifest persistence in `backend/app/jobs.py`.
- Re-run focused tests.

## Task 2 — Product-level batch state
- Add failing tests for PENDING/RUNNING/COMPLETED/ERROR and continuing after one PN fails.
- Update `backend/app/workflows.py` to persist each product immediately.
- Re-run characteristics tests.

## Task 3 — Excel auto-generation
- Add failing tests proving characteristics completion registers an Excel artifact and the download route reuses it.
- Update `backend/app/workflows.py` and `backend/app/main.py`.
- Re-run workbook tests.

## Task 4 — Recovery/status API
- Add failing API tests for active/completed/recovered jobs.
- Add `GET /api/jobs/{job_id}` with product state and artifact readiness.
- Re-run API tests.

## Task 5 — Shipped frontend compatibility
- Add a failing compatibility test requiring hooks to render all batch PNs and recovery/download state.
- Extend `backend/app/frontend_compat.py` without requiring missing React source.
- Re-run frontend compatibility tests.

## Task 6 — Regression
- Run `pytest backend/tests -q`.
- Verify the provided Falabella workbook has 11 detected product rows.
- Review branch diff before PR.
