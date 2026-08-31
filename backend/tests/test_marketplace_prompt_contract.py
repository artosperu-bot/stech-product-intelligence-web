import unittest

from app.marketplace_prompt_contract import (
    build_marketplace_prompt_contract,
    extract_character_limit,
    validate_template_value,
)
from app.marketplace_template import MarketplaceTemplateProfile, ProductSlot, TemplateField


class MarketplacePromptContractTests(unittest.TestCase):
    def _profile(self):
        return MarketplaceTemplateProfile(
            marketplace='falabella',
            sheet_name='Subir plantilla',
            header_rows=(1, 2, 3, 4),
            data_start_row=5,
            fields=[
                TemplateField(
                    column=1,
                    column_letter='A',
                    label='Nombre #39',
                    code='Nombre',
                    instruction='Título optimizado. Máximo 60 caracteres. - Value: Parlante Marca Modelo Negro',
                    example_value='Parlante Marca Modelo Negro',
                    requirements={'*': 'REQUIRED'},
                ),
                TemplateField(
                    column=2,
                    column_letter='B',
                    label='Descripción #53',
                    code='Descripción',
                    instruction='Descripción comercial con beneficios, uso y características. Máximo 3000 caracteres. Sin emojis.',
                    requirements={'*': 'REQUIRED'},
                ),
                TemplateField(
                    column=3,
                    column_letter='C',
                    label='ConectividadConexion #1651',
                    code='ConectividadConexion',
                    instruction='Selecciona una o varias opciones permitidas.',
                    requirements={'*': 'REQUIRED'},
                    valid_values=('Bluetooth', 'Wifi', 'USB'),
                ),
                TemplateField(
                    column=4,
                    column_letter='D',
                    label='QuantityFalabella #25',
                    code='QuantityFalabella',
                    instruction='Stock comercial.',
                    requirements={'*': 'REQUIRED'},
                ),
            ],
            products=[],
            category_options=('888 - Audio',),
        )

    def test_contract_includes_real_template_rules_but_not_unrelated_operational_fields(self):
        profile = self._profile()
        slot = ProductSlot(
            row=5,
            identifier='JBLCHARGE6SQUADAM',
            identifier_type='PART_NUMBER',
            category='888 - Audio',
            existing_values={'Nombre': '', 'Descripción': '', 'ConectividadConexion': 'Bluetooth'},
            identity_source='Modelo',
        )
        text = build_marketplace_prompt_contract(
            profile,
            slot,
            research_field_names=['Nombre #39', 'Descripción #53', 'ConectividadConexion #1651'],
        )
        self.assertIn('MARKETPLACE TEMPLATE CONTRACT', text)
        self.assertIn('falabella', text.lower())
        self.assertIn('Fila producto: 5', text)
        self.assertIn('JBLCHARGE6SQUADAM', text)
        self.assertIn('Máximo 3000 caracteres', text)
        self.assertIn('VALORES PERMITIDOS: Bluetooth | Wifi | USB', text)
        self.assertIn('VALOR EXISTENTE VALIDADO/PRESERVAR: Bluetooth', text)
        self.assertIn('EJEMPLO DE FORMATO — NO COPIAR COMO DATO', text)
        self.assertNotIn('QuantityFalabella #25', text)

    def test_character_limits_are_extracted_from_template_instructions(self):
        profile = self._profile()
        self.assertEqual(extract_character_limit(profile.fields[0]), 60)
        self.assertEqual(extract_character_limit(profile.fields[1]), 3000)

    def test_allowed_values_are_canonicalized_and_invalid_value_is_rejected(self):
        field = self._profile().fields[2]
        ok = validate_template_value(field, 'bluetooth|wifi')
        self.assertTrue(ok.ok)
        self.assertEqual(ok.value, 'Bluetooth|Wifi')

        bad = validate_template_value(field, 'Bluetooth|Satélite')
        self.assertFalse(bad.ok)
        self.assertIn('VALUE_NOT_ALLOWED', bad.reason)

    def test_character_limit_violation_is_rejected_deterministically(self):
        field = self._profile().fields[0]
        result = validate_template_value(field, 'X' * 61)
        self.assertFalse(result.ok)
        self.assertIn('MAX_CHARS_EXCEEDED:60', result.reason)


if __name__ == '__main__':
    unittest.main()
