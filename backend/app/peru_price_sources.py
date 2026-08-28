from __future__ import annotations

_PERU_PRICE_SEED_GUIDANCE = r'''
============================================================
STECH PRICE INTELLIGENCE — MATRIZ SEMILLA PERÚ
============================================================

Esta matriz es un punto de partida de discovery y NO es una whitelist. No asumas que una tienda tiene el producto solo por estar listada: debes buscar y validar el SKU/modelo exacto. Tampoco termines después de revisar estas fuentes; descubre dominios y sellers adicionales.

MARKETPLACES / DEPARTAMENTALES / RETAIL MASIVO
- mercadolibre.com.pe
- falabella.com.pe
- simple.ripley.com.pe
- oechsle.pe
- efe.com.pe
- lacuracao.pe
- plazavea.com.pe
- hiraoka.com.pe
- coolbox.pe

RETAIL / ECOMMERCE TECNOLÓGICO
- memorykings.pe
- impacto.com.pe
- sercoplus.com
- infotec.com.pe
- baetech.pe
- infiniti.com.pe

OTRAS RAMAS QUE DEBES EXPLORAR CUANDO APLIQUEN
- tienda oficial peruana de la marca (.pe / .com.pe);
- sellers encontrados dentro de Mercado Libre, Falabella, Ripley, Oechsle u otros marketplaces;
- ecommerce propio de cada seller descubierto;
- distribuidores, mayoristas e integradores peruanos;
- tiendas regionales y especializadas;
- dominios nuevos .pe y .com.pe descubiertos durante la investigación;
- comercios peruanos con dominio .com cuando la página muestre operación/venta en Perú.

MÉTODO OBLIGATORIO POR DOMINIO
Para cada dominio relevante combina, según existan:
- site:DOMINIO "MPN"
- site:DOMINIO "EAN"
- site:DOMINIO "UPC"
- site:DOMINIO "GTIN"
- site:DOMINIO "MARCA MODELO"
- site:DOMINIO "ALIAS"

MARKETPLACES
No trates una página de producto como una sola oferta cuando existan múltiples sellers. Enumera sellers/publicaciones distintas del producto exacto y busca también el ecommerce propio de cada seller.

DESCUBRIMIENTO DINÁMICO
Cada seller, dominio, alias, SKU, product ID o código inequívoco nuevo debe convertirse en una nueva rama de búsqueda. La matriz anterior nunca limita el discovery.
'''.strip()


def peru_price_seed_guidance() -> str:
    return _PERU_PRICE_SEED_GUIDANCE
