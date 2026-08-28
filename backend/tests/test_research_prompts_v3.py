import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.peru_price_sources import peru_price_seed_guidance
from app.research_prompts import guidance_for


class ResearchPromptsV3Tests(unittest.TestCase):
    def test_price_passes_are_progressive_and_saturation_driven(self):
        p1 = guidance_for('prices', 1)
        p2 = guidance_for('prices', 2)
        p3 = guidance_for('prices', 3)
        self.assertIn('OFICIAL', p1)
        self.assertIn('EAN', p1)
        self.assertIn('MISMA CONVERSACIÓN', p2)
        self.assertIn('seller', p2.casefold())
        self.assertIn('site:.pe', p3)
        self.assertIn('SATURACIÓN', p3)
        self.assertNotEqual(p1, p2)
        self.assertNotEqual(p2, p3)

    def test_price_source_matrix_is_broad_and_not_a_whitelist(self):
        prompt = peru_price_seed_guidance()
        for domain in (
            'mercadolibre.com.pe', 'falabella.com.pe', 'simple.ripley.com.pe',
            'oechsle.pe', 'efe.com.pe', 'lacuracao.pe', 'hiraoka.com.pe',
            'coolbox.pe', 'memorykings.pe', 'impacto.com.pe', 'sercoplus.com',
            'infotec.com.pe', 'baetech.pe', 'infiniti.com.pe',
        ):
            self.assertIn(domain, prompt)
        self.assertIn('NO es una whitelist', prompt)
        self.assertIn('seller', prompt.casefold())
        self.assertIn('DESCUBRIMIENTO DINÁMICO', prompt)

    def test_video_prompt_is_multisource_and_expansive(self):
        prompt = guidance_for('videos', 1)
        for needle in ('YouTube Shorts', 'TikTok', 'VideoObject', 'embedUrl', 'DEDUPLICACIÓN', 'SATURACIÓN'):
            self.assertIn(needle, prompt)
        self.assertIn('NO termines con 2 o 3', prompt)

    def test_image_prompt_prioritizes_quality_and_original_media(self):
        prompt = guidance_for('images', 1)
        for needle in ('srcset', 'og:image', 'JSON-LD', 'CDN', 'miniaturas', 'DEDUPLICACIÓN'):
            self.assertIn(needle, prompt)

    def test_characteristics_followup_targets_only_gaps(self):
        first = guidance_for('characteristics', 1)
        followup = guidance_for('characteristics', 2)
        self.assertIn('FUENTES PRIMARIAS', first)
        self.assertIn('NO INFERENCIA', first)
        self.assertIn('MISMA CONVERSACIÓN', followup)
        self.assertIn('FALTANTES', followup)
        self.assertIn('no vuelvas a investigar', followup.casefold())

    def test_all_prompts_enforce_clean_urls_and_exact_json_contract(self):
        for kind in ('prices', 'videos', 'images', 'characteristics'):
            prompt = guidance_for(kind, 1)
            self.assertIn('https://...', prompt)
            self.assertIn('NO Markdown', prompt)
            self.assertIn('contrato JSON', prompt)
            self.assertIn('Nunca inventes', prompt)


if __name__ == '__main__':
    unittest.main()
