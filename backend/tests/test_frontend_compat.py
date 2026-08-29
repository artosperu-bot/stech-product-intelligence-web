import unittest

from app.frontend_compat import (
    AUTO_IDENTIFIER_SENTINEL,
    FRONTEND_COMPAT_JS,
    inject_frontend_compat,
    normalize_frontend_identifier,
)


class FrontendCompatTests(unittest.TestCase):
    def test_auto_sentinel_becomes_empty_identifier(self):
        self.assertEqual(normalize_frontend_identifier(AUTO_IDENTIFIER_SENTINEL), '')
        self.assertEqual(normalize_frontend_identifier('  C11CL62301  '), 'C11CL62301')

    def test_injects_script_once_before_body_close(self):
        html = '<html><body><div id="root"></div></body></html>'
        patched = inject_frontend_compat(html)
        self.assertIn('/stech-auto-identifier.js?v=1', patched)
        self.assertLess(patched.index('/stech-auto-identifier.js?v=1'), patched.index('</body>'))
        self.assertEqual(inject_frontend_compat(patched), patched)

    def test_script_is_scoped_to_characteristics_and_replays_investigate(self):
        self.assertIn("'Características'", FRONTEND_COMPAT_JS)
        self.assertIn("'INVESTIGAR'", FRONTEND_COMPAT_JS)
        self.assertIn(AUTO_IDENTIFIER_SENTINEL, FRONTEND_COMPAT_JS)
        self.assertIn("addEventListener('click'", FRONTEND_COMPAT_JS)
        self.assertIn('button.click()', FRONTEND_COMPAT_JS)
        self.assertIn('IDENTIFICADOR DEL PRODUCTO (OPCIONAL)', FRONTEND_COMPAT_JS)


if __name__ == '__main__':
    unittest.main()
