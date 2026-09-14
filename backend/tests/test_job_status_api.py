import json
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.jobs import JobStore
import app.main as main


class JobStatusApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_store = main.STORE
        main.STORE = JobStore(Path(self.temp.name), ttl_minutes=30)
        self.client = TestClient(main.app)

    def tearDown(self):
        main.STORE = self.original_store
        self.temp.cleanup()

    def test_status_endpoint_exposes_all_products_and_excel_readiness(self):
        job = main.STORE.create('characteristics')
        main.STORE.mark_running(job.id)
        main.STORE.set_public_data(job.id, {
            'product_count': 2,
            'products': [
                {'detected_identifier': 'PN-UNO', 'status': 'COMPLETED'},
                {'detected_identifier': 'PN-DOS', 'status': 'RUNNING'},
            ],
            'excel_ready': False,
        })

        response = self.client.get(f'/api/jobs/{job.id}')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['state'], 'RUNNING')
        self.assertEqual(data['product_count'], 2)
        self.assertEqual(len(data['products']), 2)
        self.assertFalse(data['excel_ready'])

    def test_recovered_completed_job_serves_existing_excel_without_runtime_payload(self):
        root = Path(self.temp.name)
        job = main.STORE.create('characteristics')
        main.STORE.mark_running(job.id)
        artifact = job.directory / 'resultado_COMPLETADO.xlsx'
        artifact.write_bytes(b'finished-excel')
        main.STORE.add_artifact(job.id, 'excel', artifact)
        main.STORE.set_public_data(job.id, {
            'product_count': 1,
            'products': [{'detected_identifier': 'PN-UNO', 'status': 'COMPLETED'}],
            'excel_ready': True,
            'excel_download_url': f'/api/jobs/{job.id}/excel',
        })
        main.STORE.mark_completed(job.id)

        main.STORE = JobStore(root, ttl_minutes=30)

        status = self.client.get(f'/api/jobs/{job.id}')
        download = self.client.get(f'/api/jobs/{job.id}/excel')
        legacy_post = self.client.post(f'/api/jobs/{job.id}/excel')

        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()['state'], 'COMPLETED')
        self.assertTrue(status.json()['excel_ready'])
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, b'finished-excel')
        self.assertEqual(legacy_post.status_code, 200)
        self.assertEqual(legacy_post.content, b'finished-excel')


class StreamLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_stream_marks_job_running_then_completed_and_persists_result(self):
        with tempfile.TemporaryDirectory() as td:
            original_store = main.STORE
            try:
                main.STORE = JobStore(Path(td), ttl_minutes=30)
                job = main.STORE.create('characteristics')

                async def runner(active_job, emit):
                    emit(50, '1/1', 'mitad', 'TEST')
                    return {'job_id': active_job.id, 'products': [], 'product_count': 0}

                chunks = [
                    chunk async for chunk in main._stream_job(
                        'characteristics', runner, job=job
                    )
                ]

                recovered = main.STORE.get(job.id)
                self.assertEqual(recovered.state, 'COMPLETED')
                self.assertEqual(recovered.public_data['job_id'], job.id)
                events = [json.loads(chunk.decode('utf-8')) for chunk in chunks]
                self.assertEqual(events[-1]['type'], 'result')
            finally:
                main.STORE = original_store


if __name__ == '__main__':
    unittest.main()
