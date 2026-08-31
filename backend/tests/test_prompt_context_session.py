import unittest

from app.browser_selector import PromptContextSession


class _Inner:
    def __init__(self):
        self.calls = []
        self.entered = False

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.entered = False
        return False

    async def ask(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return 'ok'


class PromptContextSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_appends_marketplace_contract_to_every_string_prompt(self):
        inner = _Inner()
        wrapped = PromptContextSession(inner, 'MARKETPLACE CONTRACT')
        async with wrapped as session:
            result = await session.ask('PROMPT ORIGINAL', answer_format='json')
        self.assertEqual(result, 'ok')
        args, kwargs = inner.calls[0]
        self.assertTrue(args[0].startswith('PROMPT ORIGINAL'))
        self.assertIn('MARKETPLACE CONTRACT', args[0])
        self.assertEqual(kwargs['answer_format'], 'json')

    async def test_does_not_corrupt_non_string_first_argument(self):
        inner = _Inner()
        wrapped = PromptContextSession(inner, 'MARKETPLACE CONTRACT')
        await wrapped.ask({'prompt': 'x'})
        args, _ = inner.calls[0]
        self.assertEqual(args[0], {'prompt': 'x'})


if __name__ == '__main__':
    unittest.main()
