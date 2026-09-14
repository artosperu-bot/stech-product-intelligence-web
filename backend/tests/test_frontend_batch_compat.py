import unittest

from app.frontend_compat import FRONTEND_COMPAT_JS, FRONTEND_COMPAT_SRC


class FrontendBatchCompatTests(unittest.TestCase):
    def test_injected_script_can_recover_and_render_batch_products(self):
        self.assertIn('stech-batch-results', FRONTEND_COMPAT_JS)
        self.assertIn('stech:last-characteristics-job', FRONTEND_COMPAT_JS)
        self.assertIn('/api/jobs/', FRONTEND_COMPAT_JS)
        self.assertIn('/api/run/characteristics', FRONTEND_COMPAT_JS)
        self.assertIn('response.clone()', FRONTEND_COMPAT_JS)
        self.assertIn('data.products', FRONTEND_COMPAT_JS)
        self.assertIn('excel_ready', FRONTEND_COMPAT_JS)
        self.assertIn('PENDIENTE', FRONTEND_COMPAT_JS)
        self.assertIn('INVESTIGANDO', FRONTEND_COMPAT_JS)
        self.assertIn('COMPLETADO', FRONTEND_COMPAT_JS)
        self.assertIn('v=2', FRONTEND_COMPAT_SRC)

    def test_partial_batch_exposes_retry_failed_action_and_observes_retry_stream(self):
        self.assertIn('REINTENTAR FALLIDOS', FRONTEND_COMPAT_JS)
        self.assertIn('/retry-failed', FRONTEND_COMPAT_JS)
        self.assertIn("method: 'POST'", FRONTEND_COMPAT_JS)
        self.assertIn("url.includes('/retry-failed')", FRONTEND_COMPAT_JS)


if __name__ == '__main__':
    unittest.main()
