from __future__ import annotations

import json
import os
from typing import Any

from .remote_protocol import encode_remote_value
from .research_broker import BROKER


_COMMON_SCHEMA_RULE = """
REGLA DE COMPATIBILIDAD STECH
- Conserva EXACTAMENTE el contrato JSON solicitado por el prompt original.
- No agregues Markdown ni explicaciones fuera del JSON.
- Usa estas reglas solo para investigar mejor; no cambies nombres/tipos de campos esperados por el backend.
- Nunca debilites la identidad del producto para aumentar la cantidad de resultados.
- Nunca reemplaces evidencia fuerte ya encontrada por evidencia posterior más débil.
""".strip()

_PRICE_GUIDANCE = {
    1: """
STECH PRICE INTELLIGENCE — PASADA 1/3
MISIÓN: IDENTIDAD EXACTA + MÁXIMO RECALL COMERCIAL INICIAL EN PERÚ.
- Resuelve primero MPN/Part Number/modelo/EAN/UPC/GTIN/SKU, marca, variante y aliases inequívocos.
- La página oficial del fabricante sirve para identidad, pero no es cobertura comercial suficiente por sí sola.
- Si solo encontraste fabricante/oficial/soporte o una sola tienda, CONTINÚA buscando ofertas comerciales peruanas.
- Reutiliza inmediatamente cada identificador equivalente descubierto para nuevas búsquedas.
- Busca ecommerce, retailers, distribuidores, mayoristas, tiendas especializadas, marketplaces, dominios .pe y comercios peruanos .com.
- Una ficha de marketplace no significa que el marketplace esté agotado: busca sellers/fichas alternativas cuando existan.
- No mezcles otra capacidad, generación, bundle, reacondicionado, accesorio ni otra variante cuyo PN sea distinto.
""".strip(),
    2: """
STECH PRICE INTELLIGENCE — PASADA 2/3
MISIÓN: EXPANSIÓN DESDE LO YA DESCUBIERTO, SIN EMPEZAR DE CERO.
- Usa STECH_RESEARCH_STATE como evidencia y pistas acumuladas.
- Expande por marca+modelo, aliases, EAN/UPC/GTIN/SKU, dominios, sellers, product IDs y títulos alternativos visibles en el estado.
- Por cada seller descubierto, busca el mismo producto en su web propia y en otros marketplaces/canales peruanos.
- Por cada marketplace, busca otras fichas/sellers del producto exacto; una sola oferta no agota el marketplace.
- Prioriza NUEVAS ofertas y correcciones respaldadas por evidencia más fuerte; no repitas ofertas ya correctas innecesariamente.
- Si aparece un nuevo código/seller/dominio/alias inequívoco, úsalo para ampliar esa rama antes de cerrarla.
""".strip(),
    3: """
STECH PRICE INTELLIGENCE — PASADA 3/3
MISIÓN: LONG-TAIL PERÚ + RECUPERACIÓN DE HUECOS + COBERTURA FINAL.
- Usa STECH_RESEARCH_STATE completo; no reinicies la investigación.
- Prioriza casos sin URL directa, sin precio verificable, seller desconocido, disponibilidad desconocida o evidencia débil.
- Explora site:.pe y site:.com.pe con MPN/Part Number, marca+modelo, EAN, UPC, GTIN y aliases cuando existan.
- Busca mayoristas, integradores, tiendas de cómputo/gaming, distribuidores, ecommerce pequeños y negocios regionales relevantes.
- Revisa sellers encontrados en otros marketplaces y su ecommerce propio.
- No descartes agotados: una oferta agotada sigue siendo evidencia comercial si corresponde al producto exacto.
- No concluyas que no existe oferta solo porque la búsqueda exacta por MPN no la encontró; prueba identificadores/aliases ya validados.
""".strip(),
}

_CHARACTERISTICS_GUIDANCE = """
STECH PRODUCT RESEARCH — FICHA TÉCNICA
- Resuelve la identidad exacta antes de completar campos: marca, modelo, variante, capacidad/color/región cuando cambien el producto.
- Prioriza fabricante, manual/datasheet/soporte oficial y documentación regulatoria; después distribuidores/retailers confiables.
- No infieras especificaciones no publicadas ni copies datos de un modelo parecido.
- Si existe STECH_RESEARCH_STATE, úsalo para concentrarte en campos faltantes/rechazados y no degradar datos ya validados.
""".strip()

_IMAGE_GUIDANCE = """
STECH MEDIA DISCOVERY — IMÁGENES
- Confirma variante exacta antes de aceptar imágenes.
- Prioriza fabricante/CDN/galería/soporte oficial, luego distribuidores, mayoristas, retailers y marketplaces.
- Busca diversidad real de ángulos/contenido y evita duplicados, placeholders, miniaturas cuando exista original y variantes incorrectas.
""".strip()

_VIDEO_GUIDANCE = """
STECH MEDIA DISCOVERY — VIDEOS
- Confirma el producto/modelo/generación exactos.
- Prioriza video oficial del producto, tutorial/campaña/canal oficial; después distribuidor, retailer, review y comparación relevante.
- Rechaza coincidencias solo por familia/marca, generación diferente, duplicados y contenido irrelevante.
""".strip()


class RemoteChatGPTBrowserSession:
    """ChatGPT session facade whose ask() calls are executed by a trusted Windows worker."""

    def __init__(self, progress=None, research_kind: str | None = None):
        self.progress = progress
        self.research_kind = (research_kind or "").strip().casefold() or None
        self._research_responses: list[str] = []

    def _note(self, message: str) -> None:
        if self.progress:
            self.progress(message)

    async def __aenter__(self):
        status = await BROKER.status()
        if not status.get("online"):
            raise RuntimeError(
                "RESEARCH_WORKER_OFFLINE: inicia STECH Research Worker en la PC con Chrome antes de buscar."
            )
        self._note(f"Worker Windows conectado: {status.get('worker_id') or 'STECH-PC'}.")
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def _guidance(self) -> str:
        if self.research_kind == "prices":
            pass_no = min(len(self._research_responses) + 1, 3)
            return _PRICE_GUIDANCE[pass_no]
        if self.research_kind == "characteristics":
            return _CHARACTERISTICS_GUIDANCE
        if self.research_kind == "images":
            return _IMAGE_GUIDANCE
        if self.research_kind == "videos":
            return _VIDEO_GUIDANCE
        return ""

    def _state_block(self) -> str:
        if not self._research_responses:
            return ""
        payload = {
            "research_kind": self.research_kind,
            "completed_turns": len(self._research_responses),
            "previous_responses": self._research_responses,
        }
        return (
            "STECH_RESEARCH_STATE\n"
            "Este estado viene de respuestas anteriores del MISMO trabajo/producto. Úsalo como memoria explícita.\n"
            "No cambies el contrato JSON del prompt original y no repitas investigación ya resuelta salvo para validar/mejorar evidencia.\n"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        )

    def _augment_args(self, args: tuple[Any, ...]) -> list[Any]:
        wire_args = list(args)
        if not wire_args or not isinstance(wire_args[0], str):
            return wire_args
        blocks = [wire_args[0]]
        guidance = self._guidance()
        if guidance:
            blocks.extend([guidance, _COMMON_SCHEMA_RULE])
        state = self._state_block()
        if state:
            blocks.append(state)
        wire_args[0] = "\n\n".join(block for block in blocks if block)
        return wire_args

    def _remember(self, result: Any) -> None:
        max_total = max(4000, int(os.getenv("STECH_RESEARCH_STATE_MAX_CHARS", "22000")))
        max_item = max(2000, max_total // 2)
        if isinstance(result, str):
            text = result
        else:
            try:
                text = json.dumps(result, ensure_ascii=False, separators=(",", ":"), default=str)
            except Exception:
                text = str(result)
        if len(text) > max_item:
            text = text[:max_item] + "…[TRUNCATED]"
        self._research_responses.append(text)
        while len(self._research_responses) > 1 and sum(len(item) for item in self._research_responses) > max_total:
            self._research_responses.pop(0)
        if sum(len(item) for item in self._research_responses) > max_total:
            self._research_responses[-1] = self._research_responses[-1][:max_total] + "…[TRUNCATED]"

    async def ask(self, *args, **kwargs):
        timeout = float(os.getenv("STECH_RESEARCH_WORKER_TASK_TIMEOUT", "360"))
        self._note("Enviando consulta de ChatGPT al Chrome real del worker...")
        augmented_args = self._augment_args(args)
        wire_args = encode_remote_value(augmented_args)
        wire_kwargs = encode_remote_value(dict(kwargs))
        result = await BROKER.submit(wire_args, wire_kwargs, timeout_seconds=timeout)
        self._remember(result)
        self._note("Respuesta de ChatGPT recibida desde el worker Windows.")
        return result
