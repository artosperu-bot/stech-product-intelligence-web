from __future__ import annotations

CHARACTERISTICS_QUALITY_GUIDANCE = r'''
============================================================
STECH CHARACTERISTICS QUALITY GATE
DESCRIPCIÓN COMERCIAL + DATOS AMBIGUOS
============================================================

DESCRIPCIÓN COMERCIAL
Cuando el contrato original incluya un campo de descripción, redacta una descripción ecommerce rica, natural y útil para venta, basada SOLO en datos validados del producto exacto. Evita una descripción mínima de una o dos frases si existe evidencia suficiente para explicar mejor el producto.

Prioriza, cuando apliquen y estén confirmados: qué es el producto y para qué sirve; funciones principales; 3 a 6 prestaciones diferenciadoras; rendimiento/capacidades; conectividad/compatibilidad; autonomía/rendimiento de consumibles; uso recomendado; diseño/color; y MPN al final cuando sea útil. No hagas keyword stuffing, no agregues promociones, precio, stock, garantía comercial no confirmada ni afirmaciones superlativas sin evidencia. No repitas mecánicamente la misma especificación.

La descripción debe sonar comercial pero técnica y precisa. Si la plantilla impone un máximo de caracteres, respétalo. Si no hay evidencia suficiente para un detalle, omítelo en vez de rellenar.

DIMENSIONES Y DATOS ESTRUCTURADOS
Nunca repartas una secuencia sin etiquetas como "44 x 24 x 41 cm" entre ancho/largo/alto/profundidad por suposición. Solo escribe cada dimensión individual cuando la fuente identifique inequívocamente qué número corresponde a cada eje o cuando una documentación oficial establezca explícitamente el orden de las dimensiones.

La misma regla aplica a valores estructurados ambiguos: peso neto vs peso con empaque, cable incluido vs longitud de cable, potencia de adaptador vs consumo del equipo, rendimiento borrador vs ISO, resolución interpolada vs óptica, autonomía con/sin función activa, o cualquier dato cuyo significado no esté etiquetado claramente. Si la fuente no permite mapearlo sin inferencia, conserva el dato adicional en evidencia/especificaciones completas si resulta útil, pero deja vacío el campo estructurado específico.

FUENTES COMERCIALES
Retailers y marketplaces pueden cubrir huecos, pero un dato ambiguo de retailer no debe convertirse en campo estructurado solo para aumentar cobertura. Para atributos técnicos sensibles, prioriza fabricante/manual/datasheet exactos. CORRECTO > COMPLETO.
'''.strip()
