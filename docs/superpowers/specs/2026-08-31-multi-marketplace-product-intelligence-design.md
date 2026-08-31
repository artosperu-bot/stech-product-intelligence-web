# Multi-Marketplace Product Intelligence Design

## Goal

Make the Characteristics workflow understand the uploaded workbook before researching products, support Falabella and Ripley templates with different categories/columns, process every real product row independently, never delete unrelated rows, and write a traceable completed workbook with richer verified descriptions plus additional technical data/evidence.

## Observed workbook families

### Falabella

Observed files include printers, speakers, headphones, phones and generic electronics templates. They share these structural rules:

- Main editable sheet: `Subir plantilla`.
- Row 1 groups columns (`Principales`, `Variaciones`, `Precio`, `Especificaciones`, etc.).
- Row 2 contains field instructions and example values.
- Row 3 indicates requirement status: blank/space means required and `( Optional )` means optional.
- Row 4 contains mapped headers such as `Modelo #32`, `SKU del vendedor #29`, `Código de barras #56`.
- Data begins on row 5 and can contain one or many products/variants.
- `Categorías` contains the allowed primary category for the template.
- `Opciones` contains valid enum/list values keyed by attribute name.
- Templates may contain example values in the first data row; those examples must be treated as placeholders, not trusted business data.

### Ripley

Observed files include security cameras, monitors and mice. They share these structural rules:

- Main editable sheet: `Data`.
- Row 1 contains human labels (`Nombre`, `EAN/UPC`, `Modelo`, etc.).
- Row 2 contains internal codes (`nombre`, `ean`, `modelo`, etc.).
- Data begins on row 3 and can contain many products/variants.
- `Columns` maps internal code, label, description, example value and category-specific requirement (`REQUIRED`, `RECOMMENDED`, `OPTIONAL`).
- `ReferenceData` contains allowed values keyed by internal code.
- Requiredness must be resolved per product category, because one workbook can expose more than one category status column.

## Product-row detection

The workbook itself is authoritative for determining the current products. `IA_EVIDENCIA` is never allowed to introduce or replace a product row during initial discovery.

A `ProductSlot` is created for every real data row that contains at least one usable identity signal. Empty rows and pure example rows are ignored.

Identity signals are marketplace-specific:

- Falabella: `SKU del vendedor #29`, code-like `Modelo #32`, barcode, then name/context.
- Ripley: code-like `modelo`, barcode, `sku_seller` only as a lower-priority seller identifier, then name/context.

A code in a `Modelo` column that looks like an MPN/Part Number is classified as a Part Number candidate and researched as such. Canonical identity later separates manufacturer Part Number from commercial model.

Each row remains independent. Different rows are never purged because they belong to other products. Identical research identifiers may reuse the same research result only when they are genuinely the same product identity; variant-specific values such as color/EAN/SKU remain row-specific.

## Unified template profile

Introduce a marketplace-neutral analyzer that produces:

- marketplace (`falabella` or `ripley`),
- editable sheet name,
- header/data rows,
- detected product slots,
- field definitions,
- requirement status,
- example/placeholder values,
- allowed values,
- category information.

Downstream research and workbook writing consume this profile instead of hard-coding `Subir plantilla` or fixed column positions.

## Research orchestration

Characteristics research runs once per detected product row (or per reusable exact identity group). Every product starts a fresh ChatGPT conversation to prevent cross-product contamination, while follow-up turns for the same product remain in the same conversation.

The existing `prepare_research`/validation engine remains the source for template-aware research fields. The new orchestrator calls it with each row's detected identifier and stores a per-product result containing:

- source row,
- resolved identity,
- accepted/rejected mapped fields,
- raw research payload,
- master specifications,
- QA warnings.

The API remains backward compatible by exposing the first product in the current top-level fields while adding a `products` array and `product_count`.

## Writing rules

The generated workbook starts from a copy of the original upload. It is opened once and all product rows are updated in place.

Rules:

1. Never delete another product row.
2. Preserve valid non-placeholder user values.
3. Replace documented example placeholders when the row is a real product row.
4. Canonical identity may correct brand/model/MPN/barcode only on the row being processed.
5. Fill accepted researched values only when the destination is blank/placeholder, unless the field is an identity correction.
6. Never invent price, stock, image, seller offer IDs or other operational fields.
7. Deterministic template data may be filled without research when safe: the single allowed Falabella category and `Nuevo` when the field is required/blank and `Nuevo` is an allowed condition.
8. Ambiguous retailer data is not promoted to a mapped field. Example: unlabeled `44 x 24 x 41 cm` cannot be split into width/height/length unless the source labels the dimensions.

## Description quality

When the template requests a description, research should produce a natural Spanish commercial description based only on verified facts. Target roughly 650–1200 characters for normal ecommerce product descriptions unless the template's own constraints require otherwise.

The description should normally cover:

- what the product is and its main use,
- principal benefits,
- several important verified technical characteristics,
- connectivity/compatibility when relevant,
- practical use context,
- verified MPN at the end when useful.

Avoid keyword stuffing, unsupported superlatives and invented claims. A very short description is flagged for QA instead of silently accepted as high quality.

## Traceability sheets

The output workbook contains three IA sheets:

### `IA_PRODUCTOS`

One row per detected product with marketplace, source sheet/row, input identifier/type, canonical MPN, commercial model, brand, barcode, status, accepted field count, missing required fields and warnings.

### `ESPECIFICACIONES_COMPLETAS`

Contains both mapped accepted fields and additional technical specifications discovered during research. Extra specifications are retained even when no marketplace column exists for them. Rows include product identity, label, value, unit, status, confidence, source and PDF page when available.

### `IA_EVIDENCIA`

Contains identity evidence, accepted/rejected mapped field evidence and master-spec evidence. Prior evidence can be preserved but is associated with its Part Number and never allowed to switch the current product identity.

## QA and completion status

QA is per product row and then aggregated for the workbook.

A workbook cannot be named `COMPLETADO` if:

- a detected product row was not processed,
- canonical identity is incomplete enough to risk cross-product contamination,
- a required field that this workflow is responsible for remains blank/placeholder,
- a cross-product write is detected.

Unavailable facts remain blank with a warning instead of being invented. Operational required fields outside Characteristics (for example price/images in a new Ripley offer) can keep the workbook `NO_VALIDADO` without fabricating values.

## Compatibility

Prices, images and videos workflows are unchanged. Existing single-product Characteristics requests continue to expose their current response fields. Manual identifier mode remains supported and targets the matching row when possible.
