import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.jobs import JobStore
import app.main as main


class RetryFailedBatchTests(unittest.IsolatedAsyncioTestCase):
    async def test_retry_runner_researches_only_failed_products_and_preserves_completed_rows(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            original_store = main.STORE
            main.STORE = JobStore(root, ttl_minutes=1440)
            try:
                source = main.STORE.create('characteristics')
                main.STORE.mark_running(source.id)
                source_excel = source.directory / 'lote_NO_VALIDADO.xlsx'
                source_excel.write_bytes(b'base-partial-workbook')
                main.STORE.add_artifact(source.id, 'excel', source_excel)
                main.STORE.set_public_data(source.id, {
                    'product_count': 3,
                    'completed_count': 1,
                    'error_count': 2,
                    'partial': True,
                    'products': [
                        {'source_row': 5, 'detected_identifier': 'PN-OK', 'status': 'COMPLETED', 'preview': [{'field': 'Marca', 'value': 'JBL'}]},
                        {'source_row': 6, 'detected_identifier': 'PN-FAIL-1', 'status': 'ERROR', 'error': 'fallo 1', 'preview': []},
                        {'source_row': 7, 'detected_identifier': 'PN-FAIL-2', 'status': 'ERROR', 'error': 'fallo 2', 'preview': []},
                    ],
                    'excel_ready': True,
                    'excel_download_url': f'/api/jobs/{source.id}/excel',
                })
                main.STORE.mark_completed(source.id)

                retry_job = main.STORE.create('characteristics-retry')
                called = []

                async def fake_run_characteristics(step_job, identifier, template_path, emit):
                    called.append(identifier)
                    self.assertTrue(Path(template_path).exists())
                    output = step_job.directory / f'{identifier}_COMPLETADO.xlsx'
                    shutil.copy2(template_path, output)
                    step_job.add_artifact('excel', output)
                    return {
                        'job_id': step_job.id,
                        'product_count': 1,
                        'completed_count': 1,
                        'error_count': 0,
                        'partial': False,
                        'products': [{
                            'source_row': 6 if identifier.endswith('1') else 7,
                            'detected_identifier': identifier,
                            'status': 'COMPLETED',
                            'error': '',
                            'preview': [{'field': 'Marca', 'value': 'JBL'}],
                        }],
                        'excel_ready': True,
                        'excel_download_url': f'/api/jobs/{step_job.id}/excel',
                    }

                with patch.object(main, 'run_characteristics', side_effect=fake_run_characteristics):
                    result = await main._run_retry_failed(
                        retry_job, source.id, lambda *args, **kwargs: None
                    )

                self.assertEqual(called, ['PN-FAIL-1', 'PN-FAIL-2'])
                self.assertEqual(
                    [item['status'] for item in result['products']],
                    ['COMPLETED', 'COMPLETED', 'COMPLETED'],
                )
                self.assertEqual(result['products'][0]['detected_identifier'], 'PN-OK')
                self.assertEqual(result['products'][0]['preview'][0]['value'], 'JBL')
                self.assertEqual(result['completed_count'], 3)
                self.assertEqual(result['error_count'], 0)
                self.assertFalse(result['partial'])
                self.assertEqual(result['retry_of'], source.id)
                self.assertTrue(retry_job.artifacts['excel'].exists())
                self.assertTrue(result['excel_ready'])
            finally:
                main.STORE = original_store


if __name__ == '__main__':
    unittest.main()
