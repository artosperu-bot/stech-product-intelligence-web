import ast
import unittest
from pathlib import Path


class CharacteristicsInputModeApiTests(unittest.TestCase):
    def test_characteristics_and_inspect_identifier_form_default_to_empty(self):
        source_path = Path(__file__).resolve().parents[1] / 'app' / 'main.py'
        tree = ast.parse(source_path.read_text(encoding='utf-8'))
        funcs = {node.name: node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)}
        for name in ('template_inspect', 'run_characteristics_api'):
            fn = funcs[name]
            args = fn.args.args
            defaults = fn.args.defaults
            default_by_name = {arg.arg: default for arg, default in zip(args[-len(defaults):], defaults)}
            default = default_by_name['identifier']
            self.assertIsInstance(default, ast.Call)
            self.assertEqual(getattr(default.func, 'id', ''), 'Form')
            self.assertEqual(len(default.args), 1)
            self.assertIsInstance(default.args[0], ast.Constant)
            self.assertEqual(default.args[0].value, '')


if __name__ == '__main__':
    unittest.main()
