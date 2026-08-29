# Product Data Intelligence para Excel — Diseño

## Objetivo

Construir un flujo confiable para completar plantillas de producto desde Excel usando investigación web con ChatGPT Web, priorizando identidad exacta, PDFs oficiales, evidencia verificable y validación determinística antes de escribir cualquier valor.

El sistema debe soportar dos entradas:

1. **Modo manual**: el usuario sube el Excel y proporciona un Part Number/MPN explícito.
2. **Modo automático**: el usuario solo sube el Excel y el sistema detecta candidatos de identidad dentro de columnas como Modelo, SKU, nombre, código de barras u otros campos disponibles.

Ambos modos convergen en el mismo pipeline. La única diferencia es cómo se obtiene la identidad inicial.

## Problema observado

El Excel de prueba demuestra que la investigación puede identificar correctamente el producto pero aun así fallar el resultado final. En `IA_EVIDENCIA` se registró correctamente `C11CL62301` como Part Number y `L3350` como modelo comercial, mientras la hoja `Subir plantilla` seguía conteniendo valores JBL en `Modelo #32` y `SKU del vendedor #29` quedaba vacío.

Por ello se separan explícitamente las responsabilidades:

- ChatGPT investiga y devuelve evidencia estructurada.
- El backend normaliza identidad.
- El backend decide qué evidencia es aceptable.
- El backend mapea valores a la plantilla.
- El backend ejecuta QA determinístico.
- Solo después se genera el Excel final.

Un archivo no puede llamarse `COMPLETADO` si la identidad o el mapeo crítico no pasan QA.

## Principio central

**CORRECTO > COMPLETO.**

Nunca se rellenará un campo por inferencia no sustentada. Un valor vacío correctamente auditado es preferible a una especificación inventada o tomada de otra variante.

## Arquitectura del flujo

```text
Excel + identificador opcional
        ↓
1. Descubrimiento de candidatos
        ↓
2. Resolución de identidad canónica
        ↓
3. Investigación técnica profunda
        ↓
4. Ficha maestra estructurada
        ↓
5. Normalización + conflictos
        ↓
6. Mapeo a columnas de plantilla
        ↓
7. QA determinístico
        ↓
8. Excel final + hojas de auditoría
```

## 1. Entrada manual y automática

### Modo manual

El endpoint de características acepta `identifier` opcional. Si el usuario proporciona un Part Number/MPN, ese valor se considera el candidato principal y debe validarse contra fuentes reales antes de usarlo.

El valor manual no autoriza a inventar el producto: si las fuentes no confirman la correspondencia marca/modelo/MPN, el trabajo debe quedar bloqueado como identidad no resuelta.

### Modo automático

Si no se proporciona `identifier`, el sistema inspecciona el Excel y extrae candidatos de las columnas relevantes, priorizando:

1. `SKU del vendedor #29`
2. `Modelo #32`
3. Código de fabricante/Part Number/MPN explícito si existe
4. `Código de barras #56`
5. `Nombre #39`
6. otras columnas con texto alfanumérico útil

Cada candidato se clasifica como uno de:

- `PART_NUMBER`
- `MODEL`
- `EAN_UPC_GTIN`
- `SELLER_SKU`
- `TEXT_ALIAS`
- `UNKNOWN`

La clasificación inicial es heurística; la confirmación final siempre depende de evidencia web.

Ejemplo:

```text
input: C11CL62301
→ tipo confirmado: PART_NUMBER
→ marca: EPSON
→ part_number: C11CL62301
→ commercial_model: L3350
```

Ejemplo:

```text
input: JBLQ350WLBLKAM
→ tipo confirmado: PART_NUMBER
→ marca: JBL
→ part_number: JBLQ350WLBLKAM
→ commercial_model: Quantum 350 Wireless
```

## 2. Contrato de identidad canónica

Antes de investigar atributos, el sistema debe resolver:

```json
{
  "brand": "",
  "manufacturer_part_number": "",
  "commercial_model": "",
  "ean_upc_gtin": [],
  "variant": "",
  "color": "",
  "capacity": "",
  "region": "",
  "aliases": [],
  "confidence": 0,
  "sources": []
}
```

Reglas:

- `manufacturer_part_number` y `commercial_model` son conceptos distintos.
- EAN/UPC/GTIN nunca se usa como MPN salvo evidencia explícita de que el fabricante realmente los iguala.
- Un código colocado originalmente en `Modelo #32` puede terminar clasificado como Part Number.
- No se mezclan variantes, colores, capacidades o regiones diferentes.
- Si no se alcanza confianza suficiente para identidad, no se continúa al llenado masivo.

## 3. Reglas STECH/Falabella de identidad

Para este flujo:

```text
SKU del vendedor #29 = manufacturer_part_number
Modelo #32 = commercial_model
Código de barras #56 = EAN/UPC/GTIN confirmado
Marca #26 = brand confirmado
```

El backend debe imponer estas reglas incluso si el Excel de entrada trae esos valores mal ubicados.

## 4. Investigación técnica profunda

La investigación no debe limitarse a los campos visibles de la plantilla. Primero debe construir una ficha maestra del producto exacto con toda especificación verificable encontrada.

### Prioridad de fuentes

1. PDF/datasheet/specification sheet oficial del fabricante.
2. Página oficial del producto.
3. Manual, soporte o documentación oficial.
4. Web oficial regional de la marca.
5. Distribuidor autorizado o catálogo técnico confiable.
6. Retailer reconocido con MPN exacto.
7. Marketplace/seller únicamente para huecos comerciales o datos que no tengan mejor fuente.
8. Fuentes secundarias como apoyo, nunca para reemplazar evidencia primaria exacta sin justificación.

### Búsqueda de PDFs

El prompt de características debe ordenar explícitamente buscar, cuando existan:

- datasheet
- specification sheet
- ficha técnica
- brochure
- product guide
- user manual
- service/support manual
- regulatory document

Debe priorizar PDFs en dominios oficiales del fabricante.

Para cada dato tomado de PDF se debe conservar:

- URL directa del PDF
- título/documento
- página cuando sea posible
- fragmento o descripción de evidencia
- MPN/modelo al que aplica

### Investigación por hueco

Una ficha general nunca se considera suficiente para cerrar todos los campos. Para atributos faltantes se lanzan búsquedas específicas:

```text
<MPN> <atributo>
<modelo> <atributo> datasheet
<MPN> manual pdf
<MPN> specification pdf
site:<fabricante> <MPN> pdf
```

## 5. Contrato de ficha maestra

La investigación debe devolver una estructura independiente de la plantilla:

```json
{
  "identity": {},
  "specifications": [
    {
      "key": "print_speed_black_iso",
      "label": "Velocidad ISO negro",
      "value": "11",
      "unit": "ppm",
      "status": "CONFIRMED",
      "confidence": 99,
      "source_url": "https://...",
      "source_type": "OFFICIAL_PRODUCT|OFFICIAL_PDF|OFFICIAL_SUPPORT|AUTHORIZED_DISTRIBUTOR|RETAILER|SECONDARY",
      "source_title": "",
      "pdf_page": null,
      "evidence": "",
      "applies_to": "C11CL62301"
    }
  ],
  "conflicts": [],
  "unresolved": []
}
```

La ficha maestra puede contener muchas más especificaciones que las requeridas por Falabella.

## 6. Política de evidencia

Estados permitidos:

- `CONFIRMED`
- `CONFLICT`
- `NOT_FOUND`
- `NOT_APPLICABLE`
- `REJECTED`

Un campo puede escribirse a plantilla solo si:

- su estado es `CONFIRMED`;
- corresponde al producto/variante exactos;
- pasa la validación de tipo/opciones de la plantilla;
- cumple el umbral de confianza configurado;
- no existe un conflicto primario sin resolver.

Nunca se usará un sentinel como `89` como valor real. Los sentinels de control deben permanecer fuera de las celdas de negocio.

## 7. Conflictos

Cuando dos fuentes discrepan:

1. comprobar variante, región, unidad y metodología;
2. priorizar fuente oficial exacta para el MPN;
3. conservar ambas evidencias en auditoría;
4. seleccionar valor solo si el conflicto puede resolverse objetivamente;
5. si no puede resolverse, marcar `CONFLICT` y dejar el campo sin escribir.

Ejemplo: velocidad borrador no debe sustituir velocidad ISO si Falabella pide velocidad estándar/ISO.

## 8. Mapeo a plantilla

El mapeo será una etapa determinística posterior a la investigación.

Debe manejar:

- columnas de texto libre;
- opciones enumeradas de la hoja `Opciones`;
- unidades requeridas;
- campos multi-valor separados según convención de la plantilla;
- transformaciones de dimensiones/unidades solamente cuando sean matemáticamente explícitas;
- campos obligatorios y opcionales.

No se permite que el LLM decida por sí solo una opción que no exista en la lista aceptada por la plantilla.

## 9. Hojas del Excel final

### `Subir plantilla`

Debe conservar la estructura original y recibir únicamente valores que hayan pasado QA.

### `ESPECIFICACIONES_COMPLETAS`

Nueva hoja con la ficha maestra del producto, incluyendo especificaciones adicionales aunque Falabella no las solicite.

Columnas mínimas:

- Part Number
- Categoría técnica
- Especificación
- Valor
- Unidad
- Estado
- Confianza
- Fuente principal
- Tipo fuente
- Página PDF
- Observación

### `IA_EVIDENCIA`

Se conserva y fortalece como hoja de auditoría por campo de plantilla.

Columnas mínimas:

- Part Number
- Campo plantilla
- Valor propuesto
- Valor escrito
- Estado
- Confianza
- Fuente
- Tipo fuente
- Página PDF
- Evidencia
- Observación

## 10. QA determinístico obligatorio

Antes de generar el archivo final deben ejecutarse validaciones independientes del LLM.

### QA de identidad

Si existe Part Number confirmado:

```text
SKU del vendedor #29 == manufacturer_part_number
```

Si existe modelo comercial confirmado:

```text
Modelo #32 == commercial_model
```

Si `Modelo #32` contiene un valor clasificado como `PART_NUMBER`, el archivo falla QA hasta normalizarlo.

### QA de contaminación cruzada

No puede quedar en la fila final un identificador que pertenezca a otra marca/producto investigado.

Ejemplo: una investigación Epson C11CL62301 no puede conservar un Part Number JBL en `Modelo #32`.

### QA de evidencia

Todo campo escrito debe tener un registro correspondiente de evidencia aceptada.

### QA de enumeraciones

Todo valor que dependa de `Opciones` debe existir exactamente en el conjunto permitido o pasar por un mapeo explícito probado.

### QA de campos críticos

El archivo no recibe sufijo `COMPLETADO` si falla cualquiera de:

- identidad exacta;
- SKU/Part Number;
- modelo comercial;
- marca;
- categoría primaria cuando sea obligatoria;
- contaminación cruzada;
- estructura de workbook.

## 11. Cambios de API/UI

`POST /api/run/characteristics` debe aceptar `identifier` opcional.

- con identifier: modo manual;
- sin identifier: modo automático.

La respuesta inicial debe indicar:

```json
{
  "input_mode": "manual|auto",
  "detected_identifier": "",
  "identifier_type": "PART_NUMBER|MODEL|EAN_UPC_GTIN|UNKNOWN"
}
```

El frontend debe permitir:

- subir Excel;
- campo opcional `Part Number / identificador`;
- botón de investigar con cualquiera de los dos modos;
- mostrar identidad resuelta antes/como parte del resultado;
- mostrar alertas de conflicto o identidad no confirmada;
- descargar Excel solo tras validación.

## 12. Prompt de características

El prompt V3 actual ya prioriza fabricante, manual, datasheet, soporte y PDFs; se reforzará para exigir salida de ficha maestra, identidad canónica, búsqueda activa de PDFs y evidencia por especificación.

El prompt no será la única barrera de calidad. El backend debe validar la respuesta y rechazar resultados no demostrables.

## 13. Integración con infraestructura existente

Se conserva:

- broker remoto;
- PC020 worker;
- ChatGPT Web por CDP;
- continuidad de conversación y `STECH_RESEARCH_STATE`;
- flujo `run_characteristics`;
- generación de artefacto desde job.

No se mezclan en este cambio los bugs pendientes de precios/videos.

La nueva lógica de Product Data Intelligence se conecta al flujo de características y debe ser testeable sin navegador mediante fixtures JSON y workbooks mínimos.

## 14. Estrategia de pruebas

### Unitarias

- clasificación de candidatos de identidad;
- resolución manual vs automática;
- separación MPN/modelo/EAN;
- prioridad de fuentes;
- conflicto entre fuente oficial y retailer;
- bloqueo de inferencias;
- mapeo a opciones Falabella;
- `SKU #29 = MPN`;
- rechazo de Part Number en `Modelo #32`;
- contaminación cruzada;
- prohibición de sentinels `89` como valor de negocio.

### Workbook fixtures

Crear fixtures pequeños que reproduzcan:

1. C11CL62301 escrito en Modelo.
2. Part Number manual y Modelo vacío.
3. EAN en campo de código de barras.
4. dos productos/filas sin mezclar identidad.
5. fuente conflictiva.

### Integración

Con fixture de investigación ya validada:

- generar Excel;
- abrirlo nuevamente;
- confirmar `SKU del vendedor #29`;
- confirmar `Modelo #32`;
- confirmar hojas `ESPECIFICACIONES_COMPLETAS` e `IA_EVIDENCIA`;
- confirmar que ningún campo escrito carece de evidencia.

### E2E real

Con PC020 worker activo:

1. subir plantilla Falabella;
2. ejecutar modo manual con `C11CL62301`;
3. verificar identidad Epson L3350;
4. verificar búsqueda de fuentes oficiales/PDF cuando existan;
5. generar Excel;
6. confirmar SKU #29 = C11CL62301 y Modelo #32 = L3350;
7. repetir sin identifier usando detección automática;
8. comparar que ambos modos resuelvan la misma identidad.

## 15. Criterios de aceptación

El cambio se considera aceptado solo cuando:

- manual y automático funcionan con el mismo pipeline;
- un Part Number colocado en Modelo puede ser detectado y normalizado;
- `SKU del vendedor #29` contiene el MPN confirmado;
- `Modelo #32` contiene el modelo comercial;
- PDFs oficiales se buscan activamente y sus páginas se registran cuando sea posible;
- existe una ficha maestra más amplia que los campos de la plantilla;
- `IA_EVIDENCIA` permite auditar cada campo escrito;
- no se escriben datos sin evidencia suficiente;
- conflictos no resueltos quedan bloqueados, no inventados;
- el Excel final no contiene contaminación de otro producto;
- no se marca `COMPLETADO` cuando falla QA crítico;
- las pruebas unitarias/integración pasan;
- el E2E C11CL62301 pasa en ambos modos.

## 16. No objetivos de este cambio

- corregir el pipeline de precios;
- corregir el stall de validación de videos;
- automatizar publicación final en Falabella;
- inventar valores obligatorios que no puedan verificarse;
- sustituir la plantilla original por un formato propio.
