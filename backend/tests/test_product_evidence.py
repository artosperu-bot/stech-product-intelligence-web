import unittest

from app.product_evidence import (
    MasterSpecification,
    parse_master_specifications,
    source_rank,
    validate_master_specifications,
)
from app.product_identity import CanonicalIdentity


class ProductEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.identity = CanonicalIdentity(
            brand='EPSON',
            manufacturer_part_number='C11CL62301',
            commercial_model='L3350',
            confidence=98,
        )

    def test_official_pdf_outranks_retailer_for_same_spec(self):
        specs = [
            MasterSpecification(
                'speed', 'Velocidad ISO negro', '15', 'ipm', 'CONFIRMED', 95,
                'https://retailer.test/p', 'RETAILER', 'Retailer', None, '15 ipm', 'C11CL62301',
            ),
            MasterSpecification(
                'speed', 'Velocidad ISO negro', '11', 'ipm', 'CONFIRMED', 92,
                'https://epson.test/datasheet.pdf', 'OFFICIAL_PDF', 'Datasheet', 2, '11 ipm', 'C11CL62301',
            ),
        ]
        accepted, errors = validate_master_specifications(specs, self.identity)
        self.assertEqual(errors, [])
        self.assertEqual(len(accepted), 1)
        self.assertEqual(accepted[0].value, '11')
        self.assertGreater(source_rank('OFFICIAL_PDF'), source_rank('RETAILER'))

    def test_conflicting_equal_primary_sources_are_blocked(self):
        specs = [
            MasterSpecification(
                'weight', 'Peso', '5.0', 'kg', 'CONFIRMED', 95,
                'https://epson.test/a.pdf', 'OFFICIAL_PDF', 'A', 3, '5.0 kg', 'C11CL62301',
            ),
            MasterSpecification(
                'weight', 'Peso', '5.5', 'kg', 'CONFIRMED', 95,
                'https://epson.test/b.pdf', 'OFFICIAL_PDF', 'B', 4, '5.5 kg', 'C11CL62301',
            ),
        ]
        accepted, errors = validate_master_specifications(specs, self.identity)
        self.assertEqual(accepted, [])
        self.assertTrue(any('CONFLICT' in error for error in errors))

    def test_rejects_cross_product_spec_and_control_sentinel(self):
        specs = [
            MasterSpecification(
                'battery', 'Batería', '5000', 'mAh', 'CONFIRMED', 99,
                'https://jbl.test/spec', 'OFFICIAL_PRODUCT', 'Other', None, '5000', 'JBLQ350WLBLKAM',
            ),
            MasterSpecification(
                '__control__', 'Sentinel', '89', '', 'CONFIRMED', 100,
                '', 'CONTROL', '', None, '', 'C11CL62301',
            ),
        ]
        accepted, errors = validate_master_specifications(specs, self.identity)
        self.assertEqual(accepted, [])
        self.assertTrue(any('CROSS_PRODUCT' in error for error in errors))
        self.assertTrue(any('CONTROL_SENTINEL' in error for error in errors))

    def test_parses_master_specs_from_spanish_extension_key(self):
        specs = parse_master_specifications({
            'especificaciones_completas': [
                {
                    'key': 'resolution',
                    'label': 'Resolución máxima',
                    'value': '5760 x 1440',
                    'unit': 'dpi',
                    'status': 'CONFIRMED',
                    'confidence': 97,
                    'source_url': 'https://epson.test/spec.pdf',
                    'source_type': 'OFFICIAL_PDF',
                    'source_title': 'Ficha técnica',
                    'pdf_page': 2,
                    'evidence': '5760 x 1440 dpi',
                    'applies_to': 'C11CL62301',
                }
            ]
        }, self.identity)
        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].pdf_page, 2)
        self.assertEqual(specs[0].source_type, 'OFFICIAL_PDF')


if __name__ == '__main__':
    unittest.main()
