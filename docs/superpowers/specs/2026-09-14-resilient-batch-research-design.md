# Resilient Batch Research Design

## Goal
Prevent long marketplace research runs from being lost before Excel generation, expose all detected Part Numbers as first-class batch items, and make completed work recoverable and downloadable without requiring the user to rerun the research.

## Problem confirmed in current architecture
The current `JobStore` expires jobs based on `created_at` and stores active jobs only in process memory. Artifact generation looks up the in-memory job again. A long-running batch can therefore cross the TTL before the user clicks Generate Excel, and a process restart can invalidate the job even if temporary files remain. The characteristics workflow already researches multiple marketplace rows, but the primary preview remains focused on the first product.

## Required behavior
1. A RUNNING job must never expire because of artifact TTL.
2. Artifact retention begins only after the job reaches a terminal state.
3. Job metadata and serializable result state must be persisted to disk so the store can recover jobs after a process restart on the same filesystem.
4. Each product in a marketplace batch must have an explicit status: PENDING, RUNNING, COMPLETED, or ERROR.
5. Product progress must be persisted immediately after each product finishes, not only when the full batch finishes.
6. Successful products must remain available if a later product fails.
7. When a characteristics batch finishes, the Excel artifact must be generated automatically and registered on the job.
8. A completed job must expose a download-ready artifact endpoint and a status endpoint that can be polled after reload.
9. The batch API payload must include every detected Part Number, source row, status, preview, QA state, and any error.
10. Existing manual-identifier behavior remains: supplying an identifier intentionally selects one matching row; leaving it blank processes all detected rows.
11. Existing marketplace workbook rules remain unchanged: do not overwrite protected operational fields, preserve existing valid values, and mark QA failures instead of silently deleting rows.
12. For the uploaded Falabella acceptance workbook `CARGAR_FALABELLA_2026-09-12_172443.xlsx`, the system must expose all 11 detected product rows as batch items.

## Persistence model
Persist a small JSON manifest per job inside the job directory. The manifest stores job identity, kind, timestamps, state, serializable batch-product summaries, terminal error text, and registered artifact paths relative to the job directory. Python-only runtime objects used internally by workbook generation remain in memory while the run is active; resumable product summaries are persisted separately.

On `JobStore.get(job_id)`, if a job is not already loaded in memory, the store attempts to reconstruct it from the job directory manifest. Artifact routes therefore survive an application-process restart as long as the filesystem still contains that job directory.

This design improves process-restart recovery on the current Render filesystem but does not claim durable recovery after Render destroys/replaces the instance. True cross-instance persistence remains a later migration to Supabase/object storage.

## Lifecycle
`CREATED -> RUNNING -> COMPLETED | ERROR`.

- `created_at`: creation time.
- `updated_at`: last persisted activity.
- `finished_at`: set only on terminal state.
- TTL pruning uses `finished_at`, never `created_at` for terminal jobs, and never prunes RUNNING jobs.

## Characteristics batch flow
1. Inspect template and resolve all product slots.
2. Initialize persisted batch rows as PENDING.
3. Before a product starts, set that product to RUNNING and persist.
4. Run research and validation.
5. Persist that product as COMPLETED with serialized preview/identity/QA, or ERROR with error message.
6. Continue to later products when an individual product fails.
7. Build the final in-memory `characteristic_products` collection from successful products.
8. Generate the workbook automatically from successful product records.
9. Register the resulting workbook artifact and mark the job COMPLETED. If one or more product rows failed, retain the workbook but mark batch completion as partial in the status payload.

## API changes
- `GET /api/jobs/{job_id}` returns lifecycle state, product summaries, errors, and artifact availability.
- Existing `POST /api/jobs/{job_id}/excel` remains backward compatible. If an already-generated Excel artifact exists, it returns that file instead of regenerating.
- Characteristics stream result includes `products[]` with per-product status and `excel_ready` / `excel_download_url` when available.

## Frontend compatibility strategy
The repository currently ships a built frontend bundle rather than editable React source. The server-side compatibility injection is therefore extended only as needed to surface batch status/recovery without rebuilding an unavailable source tree. The backend API is the source of truth so a future React rebuild can consume the same endpoints directly.

## Error handling
- Individual product research errors are isolated and recorded; the remaining batch continues.
- A workbook-generation error marks the job ERROR but leaves successful product summaries persisted for diagnosis/retry.
- Missing/expired jobs return the existing 404-style user-facing message.
- A recovered job whose registered artifact file is missing reports the artifact as unavailable rather than pretending it can download.

## Testing
Add focused tests for lifecycle pruning, manifest recovery, automatic artifact reuse, per-product batch statuses, continuation after an individual product error, and the 11-row Falabella acceptance workbook behavior where practical. Existing marketplace-workbook tests remain green.
