import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.jobs import JobStore


class JobStoreLifecycleTests(unittest.TestCase):
    def test_running_job_older_than_ttl_is_not_pruned(self):
        with tempfile.TemporaryDirectory() as td:
            store = JobStore(Path(td), ttl_minutes=1)
            job = store.create('characteristics')
            job.created_at = datetime.now(timezone.utc) - timedelta(minutes=10)
            store.mark_running(job.id)

            store.prune()

            recovered = store.get(job.id)
            self.assertEqual(recovered.state, 'RUNNING')
            self.assertTrue(recovered.directory.exists())

    def test_completed_job_expires_from_finished_at_not_created_at(self):
        with tempfile.TemporaryDirectory() as td:
            store = JobStore(Path(td), ttl_minutes=30)
            job = store.create('characteristics')
            job.created_at = datetime.now(timezone.utc) - timedelta(hours=5)
            store.mark_running(job.id)
            store.mark_completed(job.id)

            store.prune()

            recovered = store.get(job.id)
            self.assertEqual(recovered.state, 'COMPLETED')
            self.assertIsNotNone(recovered.finished_at)

    def test_manifest_allows_recovery_in_fresh_store(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            store = JobStore(root, ttl_minutes=30)
            job = store.create('characteristics')
            store.mark_running(job.id)
            store.set_public_data(job.id, {
                'products': [
                    {
                        'source_row': 5,
                        'detected_identifier': 'JBLENDURRUN3BTBAM',
                        'status': 'COMPLETED',
                    }
                ]
            })
            artifact = job.directory / 'resultado.xlsx'
            artifact.write_bytes(b'xlsx-placeholder')
            store.add_artifact(job.id, 'excel', artifact)
            store.mark_completed(job.id)

            fresh = JobStore(root, ttl_minutes=30)
            recovered = fresh.get(job.id)

            self.assertEqual(recovered.state, 'COMPLETED')
            self.assertEqual(
                recovered.public_data['products'][0]['detected_identifier'],
                'JBLENDURRUN3BTBAM',
            )
            self.assertEqual(recovered.artifacts['excel'], artifact)


if __name__ == '__main__':
    unittest.main()
