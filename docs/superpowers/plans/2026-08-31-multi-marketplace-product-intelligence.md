# Multi-Marketplace Product Intelligence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect Falabella and Ripley workbook structures dynamically, process every real product row independently, generate richer verified content, and export one traceable workbook without deleting unrelated products.

**Architecture:** Add a marketplace-neutral template analyzer and a new multi-product workbook writer. The existing research/validation engine remains intact, but `workflows.run_characteristics` orchestrates one research run per detected product row with a fresh product conversation and `generate_excel` writes all results back to exact source rows.

**Tech Stack:** Python 3, FastAPI backend, openpyxl in application runtime, existing legacy research engine, Playwright/remote ChatGPT worker.

**Spec:** `docs/superpowers/specs/2026-08-31-multi-marketplace-product-intelligence-design.md`

## Global Constraints

- Never delete an unrelated product row.
- `IA_EVIDENCIA` cannot introduce the current product during initial row discovery.
- Preserve valid existing marketplace values; replace only blanks/documented examples unless correcting canonical identity.
- Never invent missing technical or operational data.
- Prices/images/videos workflows remain unchanged.
- Output is `COMPLETADO` only when deterministic QA passes for all detected product rows.

---

### Task 1: Marketplace template analyzer

**Files:**
- Create: `backend/app/marketplace_template.py`
- Create: `backend/tests/test_marketplace_template.py`

**Interfaces:**
- Produces: `analyze_marketplace_template(path: Path) -> MarketplaceTemplateProfile`
- Produces dataclasses: `TemplateField`, `ProductSlot`, `MarketplaceTemplateProfile`

- [ ] **Step 1: Write failing tests** for Falabella multi-row detection, Falabella example placeholders, Ripley dual headers, Ripley category-specific requirements, and ensuring `IA_EVIDENCIA` does not create product slots.
- [ ] **Step 2: Run focused tests and verify RED.**
- [ ] **Step 3: Implement analyzer** with structural detection, allowed values, example values, requirement status and per-row identity selection.
- [ ] **Step 4: Run focused tests and verify GREEN.**
- [ ] **Step 5: Commit.**

### Task 2: Multi-product workbook writer

**Files:**
- Create: `backend/app/marketplace_workbook.py`
- Create: `backend/tests/test_marketplace_workbook.py`

**Interfaces:**
- Consumes: `MarketplaceTemplateProfile`, per-product identity, preview rows, master specifications and raw payload.
- Produces: `write_marketplace_workbook(...) -> MarketplaceWorkbookQA`

- [ ] **Step 1: Write failing tests** proving two Falabella rows survive, exact rows are updated, Ripley existing offer fields are preserved, placeholders are replaceable, and IA sheets contain all products.
- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: Implement writer** with exact-row updates, deterministic category/condition fill, required-field QA, `IA_PRODUCTOS`, `ESPECIFICACIONES_COMPLETAS`, and `IA_EVIDENCIA` aggregation.
- [ ] **Step 4: Verify GREEN.**
- [ ] **Step 5: Commit.**

### Task 3: Multi-product characteristics orchestration

**Files:**
- Modify: `backend/app/product_characteristics.py`
- Modify: `backend/app/workflows.py`
- Modify: `backend/tests/test_characteristics_workflow.py`

**Interfaces:**
- `inspect_template` adds marketplace/product count/product rows while keeping old keys.
- `run_characteristics` adds `products` and `product_count`, while top-level response remains compatible with first product.
- `generate_excel` uses the generic writer for analyzed marketplace templates.

- [ ] **Step 1: Write failing workflow tests** for two identifiers causing two research runs and two product payloads, with no global evidence takeover.
- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: Implement sequential per-product orchestration**, fresh ChatGPT session per product, progress labels `Producto i/n`, and payload aggregation.
- [ ] **Step 4: Route Excel generation through multi-product writer** and keep legacy fallback when no recognized marketplace profile exists.
- [ ] **Step 5: Verify focused workflow tests GREEN.**
- [ ] **Step 6: Commit.**

### Task 4: Description/evidence quality policy

**Files:**
- Modify: `backend/app/research_prompts.py`
- Create/modify: `backend/tests/test_research_prompts_v3.py`

**Interfaces:**
- Characteristics guidance requires rich verified Spanish description when a description field exists and conservative handling of retailer-only/ambiguous dimension data.

- [ ] **Step 1: Add failing prompt assertions** for 650–1200 character target, practical/commercial structure, no invention, and unlabeled dimension tuples not being split.
- [ ] **Step 2: Verify RED.**
- [ ] **Step 3: Add prompt policy** without changing the legacy JSON contract.
- [ ] **Step 4: Verify GREEN.**
- [ ] **Step 5: Commit.**

### Task 5: Regression and integration verification

**Files:**
- Test existing identity/workbook/workflow/worker tests plus new tests.

- [ ] **Step 1: Run focused marketplace/template/writer/workflow/prompt tests.**
- [ ] **Step 2: Run existing Product Intelligence regression tests.**
- [ ] **Step 3: Inspect branch diff to ensure prices/images/videos runtime is unchanged.**
- [ ] **Step 4: Verify no configured CI exists before making CI claims.**
- [ ] **Step 5: Fast-forward `main` only after evidence is green.**
