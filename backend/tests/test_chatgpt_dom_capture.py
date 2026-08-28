import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.chatgpt_dom_capture import extract_json_payload


class ChatGPTDomCaptureTests(unittest.TestCase):
    def test_extracts_plain_json_object(self):
        raw = '{"producto":{"marca":"JBL"},"ofertas":[{"precio_actual":399}]}'
        payload = extract_json_payload(raw)
        self.assertIsNotNone(payload)
        self.assertIn('"marca":"JBL"', payload)

    def test_extracts_fenced_json(self):
        raw = '```json\n{"ok":true,"items":[1,2]}\n```'
        payload = extract_json_payload(raw)
        self.assertEqual(payload, '{"ok":true,"items":[1,2]}')

    def test_rejects_incomplete_streaming_json(self):
        self.assertIsNone(extract_json_payload('{"ofertas":[{"tienda":"Ripley"}'))

    def test_ignores_explanation_without_complete_json(self):
        self.assertIsNone(extract_json_payload('Estoy investigando más tiendas en Perú...'))


if __name__ == '__main__':
    unittest.main()
