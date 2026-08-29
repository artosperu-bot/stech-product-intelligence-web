# Product Data Intelligence Excel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add reliable manual/automatic product identity resolution, evidence-first technical research, deterministic workbook QA, and auditable Excel output for Falabella product templates.

**Architecture:** Keep the existing remote ChatGPT worker, broker, `run_characteristics`, and legacy V30 template/research flow intact. Add a tracked backend layer around the legacy core that (1) extracts/normalizes identity candidates from the workbook, (2) validates canonical product identity and research evidence, and (3) post-processes the generated workbook to enforce STECH/Falabella identity rules and add `ESPECIFICACIONES_COMPLETAS` plus strengthened `IA_EVIDENCIA`. The LLM proposes researched facts; tracked backend code decides whether they are allowed into the workbook.

**Tech Stack:** Python 3.14-compatible code, FastAPI, openpyxl 3.1.5, existing V30 legacy core, remote ChatGPT Web worker, unittest.

**Spec:** `docs/superpowers/specs/2026-08-29-product-data-intelligence-excel-design.md`

## Global Constraints

- Preserve broker, PC020 CDP worker, ChatGPT Web, and current price/image/video behavior.
- `POST /api/run/characteristics` accepts an optional identifier; empty means automatic detection.
- `SKU del vendedor #29` must equal the confirmed manufacturer Part Number/MPN.
- `Modelo #32` must contain the confirmed commercial model, not an MPN when they differ.
- `Código de barras #56` receives only confirmed EAN/UPC/GTIN.
- Never fill business cells with sentinel/control values such as `89`.
- Correctness outranks completeness; unresolved/conflicting values remain unwritten.
- Official manufacturer PDF/datasheet/support evidence outranks retailer/secondary evidence for technical specifications.
- No file may be marked `COMPLETADO` when critical identity/workbook QA fails.
- Do not change price or video pipelines in this feature.

---

### Task 1: Identity candidate extraction and canonical identity model

**Files:**
- Create: `backend/app/product_identity.py`
- Create: `backend/tests/test_product_identity.py`

**Interfaces:**
- Produces `IdentityCandidate(value, kind, field_name, row, priority)`.
- Produces `CanonicalIdentity(brand, manufacturer_part_number, commercial_model, ean_upc_gtin, variant, color, capacity, region, aliases, confidence, sources)`.
- Produces `extract_identity_candidates(path: Path) -> list[IdentityCandidate]`.
- Produces `choose_research_identifier(manual_identifier: str | None, candidates: list[IdentityCandidate]) -> tuple[str, str, str]`, returning `(input_mode, identifier, identifier_type)`.
- Produces `canonical_identity_from_raw(raw: dict, fallback_identifier: str = '') -> CanonicalIdentity`.

- [ ] **Step 1: Write RED tests for workbook candidate detection**

Create minimal `openpyxl` workbooks with `Subir plantilla` headers. Assert that `C11CL62301` placed under `Modelo #32` is returned as a high-priority alphanumeric candidate, while a 13-digit value in `Código de barras #56` is classified as `EAN_UPC_GTIN`.

- [ ] **Step 2: Run RED**

Run: `python -m unittest backend.tests.test_product_identity -v`
Expected: import/function failures because `product_identity.py` does not exist.

- [ ] **Step 3: Implement candidate extraction and conservative heuristics**

Rules: exact 8/12/13/14 digit barcode strings are EAN/UPC/GTIN candidates; whitespace-free mixed alphanumeric codes from SKU/model/MPN-like columns are `PART_NUMBER` candidates; prose/title fields are `TEXT_ALIAS`; heuristics never constitute final confirmation.

- [ ] **Step 4: Implement manual vs automatic selection**

Manual non-empty input wins as the research seed and reports `input_mode='manual'`; otherwise choose the highest-priority workbook candidate and report `input_mode='auto'`. If no usable candidate exists, raise `IDENTITY_CANDIDATE_NOT_FOUND`.

- [ ] **Step 5: Implement canonical identity parsing from research raw JSON**

Accept common key aliases (`manufacturer_part_number`, `part_number`, `mpn`, `sku_fabricante`, `modelo`, `model`, `brand`, `marca`, `ean`, `upc`, `gtin`) without treating barcode as MPN. Normalize surrounding whitespace only; preserve manufacturer code case.

- [ ] **Step 6: Run GREEN**

Run: `python -m unittest backend.tests.test_product_identity -v`
Expected: PASS.

---

### Task 2: Evidence model, source ranking, and deterministic QA

**Files:**
- Create: `backend/app/product_evidence.py`
- Create: `backend/tests/test_product_evidence.py`

**Interfaces:**
- Produces `EvidenceRecord` and `MasterSpecification` dataclasses.
- Produces `source_rank(source_type: str) -> int`.
- Produces `parse_master_specifications(raw: dict, identity: CanonicalIdentity) -> list[MasterSpecification]`.
- Produces `validate_master_specifications(specs, identity, min_confidence=80) -> tuple[list[MasterSpecification], list[str]]`.

- [ ] **Step 1: Write RED tests for source precedence and conflicts**

Test that `OFFICIAL_PDF` outranks `RETAILER`; a 95-confidence retailer value cannot overwrite an exact official PDF value for the same MPN; unresolved conflicting primary values become `CONFLICT` and are not accepted.

- [ ] **Step 2: Write RED tests for exact-product enforcement**

A spec with `applies_to='JBLQ350WLBLKAM'` must be rejected when canonical MPN is `C11CL62301`. `89` must be rejected as a business value when it is used as a control sentinel.

- [ ] **Step 3: Run RED**

Run: `python -m unittest backend.tests.test_product_evidence -v`
Expected: failures because evidence module does not exist.

- [ ] **Step 4: Implement source rank and parser**

Ranking: `OFFICIAL_PDF` > `OFFICIAL_PRODUCT` > `OFFICIAL_SUPPORT` > `AUTHORIZED_DISTRIBUTOR` > `RETAILER` > `MARKETPLACE` > `SECONDARY` > unknown. Preserve URL, title, PDF page, evidence text, unit, confidence and applicability.

- [ ] **Step 5: Implement deterministic acceptance rules**

Accept only `CONFIRMED`, confidence >= configured threshold, exact product applicability (when provided), non-empty value, and no unresolved higher/equal-rank conflict. Never infer missing values.

- [ ] **Step 6: Run GREEN**

Run: `python -m unittest backend.tests.test_product_evidence -v`
Expected: PASS.

---

### Task 3: Strengthen characteristics research guidance without breaking legacy JSON

**Files:**
- Modify: `backend/app/research_prompts.py`
- Modify: `backend/tests/test_research_prompts_v3.py`

**Interfaces:**
- Existing `guidance_for('characteristics', turn)` remains the public interface.
- The legacy prompt JSON contract remains authoritative; supplemental master-spec/evidence data must be returned only in extension keys allowed by the underlying prompt/runner, otherwise evidence must be captured in the existing raw evidence structure.

- [ ] **Step 1: Add RED prompt assertions**

Assert first-pass guidance explicitly contains: `datasheet`, `specification sheet`, `brochure`, `product guide`, `user manual`, `PDF`, `página`, `manufacturer_part_number`, `commercial_model`, `SKU del vendedor #29`, and instructions not to mix variants/regions.

- [ ] **Step 2: Run RED**

Run: `python -m unittest backend.tests.test_research_prompts_v3.ResearchPromptsV3Tests.test_characteristics_research_requires_pdf_evidence_and_canonical_identity -v`
Expected: FAIL until guidance is strengthened.

- [ ] **Step 3: Strengthen `_CHARACTERISTICS_P1`**

Add an explicit identity phase distinguishing MPN, commercial model and barcode; active official PDF search; PDF-page capture when possible; wider ficha-maestra research beyond only requested template fields; source-conflict rules; `CORRECTO > COMPLETO`; and the STECH rule that seller SKU is the confirmed MPN.

- [ ] **Step 4: Strengthen follow-up guidance**

Make follow-up target unresolved/conflicting fields and missing evidence, explicitly searching official PDF/support by MPN + attribute without weakening previously confirmed primary evidence.

- [ ] **Step 5: Run GREEN + existing prompt regression**

Run: `python -m unittest backend.tests.test_research_prompts_v3 -v`
Expected: all prompt tests PASS.

---

### Task 4: Automatic identifier mode in API/workflow

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/workflows.py`
- Create: `backend/tests/test_characteristics_input_mode.py`

**Interfaces:**
- `inspect_template(path: Path, identifier: str | None = None) -> dict`.
- `run_characteristics(job, identifier: str | None, template_path: Path, emit)`.
- `/api/template/inspect` and `/api/run/characteristics` accept `identifier: str = Form('')`.

- [ ] **Step 1: Write RED tests for manual and automatic mode**

Use a temporary workbook where `Modelo #32=C11CL62301`. Patch the legacy `prepare_research`/runner boundary where needed. Assert manual input reports `manual` and auto input detects `C11CL62301` and reports `auto` plus identifier type.

- [ ] **Step 2: Run RED**

Run: `python -m unittest backend.tests.test_characteristics_input_mode -v`
Expected: current required Form identifier and workflow signature fail automatic mode.

- [ ] **Step 3: Integrate candidate selection before legacy prepare/research**

Resolve the seed identifier using Task 1 before calling `prepare_research`. Store `input_mode`, `detected_identifier`, and `identifier_type` in `job.payload` and result JSON.

- [ ] **Step 4: Make API form identifier optional**

Change only characteristics/inspect identifier forms; prices/images/videos remain required.

- [ ] **Step 5: Run GREEN + API regression**

Run: `python -m unittest backend.tests.test_characteristics_input_mode backend.tests.test_remote_worker_api backend.tests.test_research_broker -v`
Expected: PASS.

---

### Task 5: Deterministic workbook post-processor and audit sheets

**Files:**
- Create: `backend/app/product_workbook.py`
- Create: `backend/tests/test_product_workbook.py`
- Modify: `backend/app/workflows.py`

**Interfaces:**
- Produces `ProductWorkbookQA(ok: bool, errors: list[str], warnings: list[str])`.
- Produces `finalize_product_workbook(path: Path, identity: CanonicalIdentity, specifications: list[MasterSpecification], evidence_rows: list[dict]) -> ProductWorkbookQA`.
- Produces `assert_product_workbook_qa(qa: ProductWorkbookQA) -> None` raising `PRODUCT_WORKBOOK_QA_FAILED: ...`.

- [ ] **Step 1: Write RED workbook integration tests**

Build a minimal workbook reproducing the real failure: Epson product identity but `Modelo #32=JBLQ350WLBLKAM` and empty `SKU del vendedor #29`. After finalization assert: SKU is `C11CL62301`; Modelo is `L3350`; Marca is `EPSON`; barcode only if confirmed; no JBL identifier remains in the target row.

- [ ] **Step 2: Add RED tests for audit sheets**

Assert `ESPECIFICACIONES_COMPLETAS` exists with required columns, and `IA_EVIDENCIA` contains identity/spec rows with source URL/type/PDF page/confidence. Assert existing original sheets are preserved.

- [ ] **Step 3: Add RED tests for QA blocking**

Missing confirmed MPN/model/brand or cross-product contamination must make QA fail. A field written without evidence must be reported. The writer must not silently call such a file completed.

- [ ] **Step 4: Run RED**

Run: `python -m unittest backend.tests.test_product_workbook -v`
Expected: module/function failures.

- [ ] **Step 5: Implement header lookup and identity normalization**

Find columns by normalized header text rather than hard-coded letters. Update only the product data row(s) associated with this research job. Preserve workbook formatting/other sheets.

- [ ] **Step 6: Implement audit sheets and QA**

Recreate/replace only `ESPECIFICACIONES_COMPLETAS`; augment/rebuild `IA_EVIDENCIA` with deterministic rows. Validate exact critical identity, cross-product contamination, and evidence presence.

- [ ] **Step 7: Run GREEN**

Run: `python -m unittest backend.tests.test_product_workbook -v`
Expected: PASS.

---

### Task 6: Connect validated identity/evidence to generated Excel

**Files:**
- Modify: `backend/app/workflows.py`
- Modify: `backend/app/serializers.py`
- Create: `backend/tests/test_characteristics_product_intelligence.py`

**Interfaces:**
- `run_characteristics` stores `canonical_identity`, `master_specifications`, `qa_warnings` in job payload.
- Characteristics result includes serialized `identity`, `input_mode`, `detected_identifier`, `identifier_type`, `qa_ready`.
- `generate_excel(job)` calls the legacy writer first, then tracked finalizer, and refuses download on critical QA failure.

- [ ] **Step 1: Write RED orchestration test with fake validation raw JSON**

Fixture raw data identifies EPSON/C11CL62301/L3350 and contains at least one official-PDF spec. Assert payload/result preserve canonical identity and parsed master spec.

- [ ] **Step 2: Run RED**

Run: `python -m unittest backend.tests.test_characteristics_product_intelligence -v`
Expected: current workflow has no canonical/evidence payload.

- [ ] **Step 3: Parse identity/spec evidence after legacy validation**

Use Tasks 1-2 against `result.validation.raw`. Do not mutate price/image/video logic.

- [ ] **Step 4: Finalize workbook after legacy `write_validated_workbook`**

Call `finalize_product_workbook`, then `assert_product_workbook_qa`. Rename only a QA-passing artifact with `_COMPLETADO` suffix; QA-failing artifact remains non-completed and returns a 400 on download with concrete reasons.

- [ ] **Step 5: Run GREEN regression**

Run: `python -m unittest backend.tests.test_characteristics_product_intelligence backend.tests.test_product_identity backend.tests.test_product_evidence backend.tests.test_product_workbook backend.tests.test_research_prompts_v3 -v`
Expected: PASS.

---

### Task 7: Frontend manual/automatic UX through the versioned frontend bundle

**Files:**
- Update contents packaged into: `frontend_bundle/part-*.b64`
- Add/update build/repack helper if absent: `tools/repack_frontend_bundle.py`
- Test: deterministic bundle extraction/build smoke in Docker/local Node environment.

**Interfaces:**
- Characteristics form sends uploaded workbook plus optional identifier.
- Empty identifier is labeled automatic detection.
- Result shows resolved brand, Part Number, commercial model, identifier mode, and QA alerts.
- Excel download button is enabled only when backend reports `qa_ready=true`.

- [ ] **Step 1: Extract the current frontend source bundle in an isolated directory**

Decode concatenated `frontend_bundle/part-*.b64` to its tar.xz and inspect the actual React/Vite source before editing.

- [ ] **Step 2: Add the optional input UX**

Keep one characteristics screen with `Part Number / identificador (opcional)`. Add helper text: leave blank to detect automatically from the Excel.

- [ ] **Step 3: Render resolved identity/QA state**

Show canonical MPN/model/brand and manual/automatic mode. Surface backend conflicts rather than hiding them.

- [ ] **Step 4: Rebuild and repack deterministically**

Run `npm install` and `npm run build`; repack source bundle into the existing `frontend_bundle` format with stable ordering/chunking.

- [ ] **Step 5: Build smoke**

Run Docker frontend build stage or local Vite build. Expected: exit 0.

---

### Task 8: Final verification and real E2E on PC020

**Files:**
- No production changes expected unless verification finds a reproduced defect.

**Interfaces:**
- Verifies all previous tasks together.

- [ ] **Step 1: Compile tracked Python**

Run: `py -m py_compile backend/app/product_identity.py backend/app/product_evidence.py backend/app/product_workbook.py backend/app/research_prompts.py backend/app/workflows.py backend/app/main.py`
Expected: exit 0.

- [ ] **Step 2: Run focused suite**

Run all new product-data tests plus current worker/prompt/broker regression tests. Expected: all PASS.

- [ ] **Step 3: Manual-mode E2E**

With PC020 worker connected, upload the real Falabella template and run identifier `C11CL62301`. Expected identity: EPSON, MPN C11CL62301, commercial model L3350; technical research explicitly visits/uses official manufacturer/support/PDF evidence when available; generated workbook has `SKU del vendedor #29=C11CL62301`, `Modelo #32=L3350`, audit sheets, and no JBL contamination.

- [ ] **Step 4: Automatic-mode E2E**

Run the same workbook with blank identifier. Expected: automatic detection selects the correct candidate and converges to the same canonical identity/result as manual mode.

- [ ] **Step 5: Negative QA E2E/fixture**

Feed a fixture with unresolved identity/conflicting primary evidence. Expected: download is blocked or artifact remains non-`COMPLETADO`, with explicit QA reasons; no invented fallback values.

- [ ] **Step 6: Review diff and merge only after evidence**

Review changed files, run regression once more, create PR, and merge only when focused tests and both C11CL62301 E2Es are green.
