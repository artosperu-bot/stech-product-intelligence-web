import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.marketplace_template import ProductSlot
from app.product_identity import CanonicalIdentity
from backend.tests.test_characteristics_workflow import FakeSession, isolated_workflows


class RecordingJob:
    def __init__(self, directory: Path):
        self.id = 'batch-job'
        self.directory = Path(directory)
        self.payload = {}
        self.public_data = {}
        self.public_updates = []
        self.artifacts = {}

    def set_public_data(self, data: dict) -> None:
        self.public_data = copy.deepcopy(data)
        self.public_updates.append(copy.deepcopy(data))

    def add_artifact(self, name: str, path: Path) -> None:
        self.artifacts[str(name)] = Path(path)


class CharacteristicsBatchStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_product_failure_does_not_discard_other_products(self):
        schema = SimpleNamespace(
            family='falabella', sheet_name='Subir plantilla', category='audio',
            data_start_row=5, research_fields=[],
        )

        def prepare_research(path, identifier):
            return SimpleNamespace(identifier=identifier, schema=schema, researchable_count=1)

        async def run_once(prep, *args, **kwargs):
            if prep.identifier == 'PN-ERROR':
                raise RuntimeError('fallo controlado de investigación')
            validation = SimpleNamespace(
                raw={'producto': {'marca': 'JBL', 'modelo': prep.identifier}},
                accepted=[1],
                rejected=[],
            )
            return SimpleNamespace(validation=validation, raw_paths=[], followup_performed=False)

        slots = [
            ProductSlot(5, 'PN-UNO', 'MPN', 'audio', {}, 'modelo'),
            ProductSlot(6, 'PN-ERROR', 'MPN', 'audio', {}, 'modelo'),
            ProductSlot(7, 'PN-TRES', 'MPN', 'audio', {}, 'modelo'),
        ]
        profile = SimpleNamespace(marketplace='falabella')

        def intelligence(raw, template_path, identifier, min_confidence=80):
            return SimpleNamespace(
                identity=CanonicalIdentity(
                    brand='JBL', manufacturer_part_number=identifier,
                    commercial_model=identifier, confidence=99,
                    sources=[{'url': 'https://example.test', 'source_type': 'OFFICIAL_PRODUCT'}],
                ),
                specifications=[], evidence_errors=[], critical_errors=[],
            )

        with isolated_workflows(
            prepare_research=prepare_research,
            run_research_for_preview_once=run_once,
        ) as (workflows, _):
            with tempfile.TemporaryDirectory() as td:
                template = Path(td) / 'template.xlsx'
                template.write_bytes(b'placeholder')
                job = RecordingJob(Path(td))
                artifact = Path(td) / 'resultado_COMPLETADO.xlsx'
                artifact.write_bytes(b'xlsx-placeholder')

                with (
                    patch.object(workflows, 'resolve_characteristics_slots', return_value=(profile, slots)),
                    patch.object(workflows, 'build_marketplace_prompt_contract', return_value=''),
                    patch.object(workflows, 'build_product_intelligence', side_effect=intelligence),
                    patch.object(workflows, 'chatgpt_session', return_value=FakeSession()),
                    patch.object(workflows, 'generate_excel', return_value=artifact),
                ):
                    result = await workflows.run_characteristics(
                        job, '', template, lambda *a, **k: None
                    )

        self.assertEqual(
            [item['status'] for item in result['products']],
            ['COMPLETED', 'ERROR', 'COMPLETED'],
        )
        self.assertEqual(result['completed_count'], 2)
        self.assertEqual(result['error_count'], 1)
        self.assertTrue(result['partial'])
        self.assertIn('fallo controlado', result['products'][1]['error'])

    async def test_batch_persists_live_states_and_registers_excel_automatically(self):
        schema = SimpleNamespace(
            family='falabella', sheet_name='Subir plantilla', category='audio',
            data_start_row=5, research_fields=[],
        )

        def prepare_research(path, identifier):
            return SimpleNamespace(identifier=identifier, schema=schema, researchable_count=1)

        async def run_once(prep, *args, **kwargs):
            validation = SimpleNamespace(
                raw={'producto': {'marca': 'JBL', 'modelo': prep.identifier}},
                accepted=[1], rejected=[],
            )
            return SimpleNamespace(validation=validation, raw_paths=[], followup_performed=False)

        slots = [
            ProductSlot(5, 'PN-UNO', 'MPN', 'audio', {}, 'modelo'),
            ProductSlot(6, 'PN-DOS', 'MPN', 'audio', {}, 'modelo'),
        ]
        profile = SimpleNamespace(marketplace='falabella')

        def intelligence(raw, template_path, identifier, min_confidence=80):
            return SimpleNamespace(
                identity=CanonicalIdentity(
                    brand='JBL', manufacturer_part_number=identifier,
                    commercial_model=identifier, confidence=99,
                    sources=[{'url': 'https://example.test', 'source_type': 'OFFICIAL_PRODUCT'}],
                ),
                specifications=[], evidence_errors=[], critical_errors=[],
            )

        with isolated_workflows(
            prepare_research=prepare_research,
            run_research_for_preview_once=run_once,
        ) as (workflows, _):
            with tempfile.TemporaryDirectory() as td:
                template = Path(td) / 'template.xlsx'
                template.write_bytes(b'placeholder')
                job = RecordingJob(Path(td))
                artifact = Path(td) / 'resultado_COMPLETADO.xlsx'
                artifact.write_bytes(b'xlsx-placeholder')

                with (
                    patch.object(workflows, 'resolve_characteristics_slots', return_value=(profile, slots)),
                    patch.object(workflows, 'build_marketplace_prompt_contract', return_value=''),
                    patch.object(workflows, 'build_product_intelligence', side_effect=intelligence),
                    patch.object(workflows, 'chatgpt_session', return_value=FakeSession()),
                    patch.object(workflows, 'generate_excel', return_value=artifact),
                ):
                    result = await workflows.run_characteristics(
                        job, '', template, lambda *a, **k: None
                    )

        seen_states = {
            tuple(item['status'] for item in update.get('products', []))
            for update in job.public_updates
        }
        self.assertIn(('PENDING', 'PENDING'), seen_states)
        self.assertIn(('RUNNING', 'PENDING'), seen_states)
        self.assertIn(('COMPLETED', 'RUNNING'), seen_states)
        self.assertEqual(job.artifacts['excel'], artifact)
        self.assertTrue(result['excel_ready'])
        self.assertEqual(result['excel_download_url'], '/api/jobs/batch-job/excel')


if __name__ == '__main__':
    unittest.main()
