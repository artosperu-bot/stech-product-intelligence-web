import unittest

from app.characteristics_quality_guidance import CHARACTERISTICS_QUALITY_GUIDANCE
from app.remote_browser import RemoteChatGPTBrowserSession


class CharacteristicsQualityGuidanceTests(unittest.TestCase):
    def test_characteristics_guidance_requires_rich_description_and_no_dimension_guessing(self):
        session = RemoteChatGPTBrowserSession(research_kind='characteristics')
        text = session._guidance()
        self.assertIn('DESCRIPCIÓN COMERCIAL', text)
        self.assertIn('44 x 24 x 41 cm', text)
        self.assertIn('CORRECTO > COMPLETO', text)
        self.assertIn(CHARACTERISTICS_QUALITY_GUIDANCE, text)

    def test_other_research_kinds_do_not_receive_characteristics_quality_block(self):
        session = RemoteChatGPTBrowserSession(research_kind='videos')
        self.assertNotIn('STECH CHARACTERISTICS QUALITY GATE', session._guidance())


if __name__ == '__main__':
    unittest.main()
