import unittest
from types import SimpleNamespace


class FakePage:
    def __init__(self, url="https://chatgpt.com/c/old"):
        self.url = url
        self.goto_calls = []

    def is_closed(self):
        return False

    async def goto(self, url, wait_until=None, timeout=None):
        self.goto_calls.append((url, wait_until, timeout))
        self.url = url


class FakeContext:
    def __init__(self, pages):
        self.pages = pages

    async def new_page(self):
        page = FakePage("about:blank")
        self.pages.append(page)
        return page


class FreshChatWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_open_fresh_chat_navigates_to_chatgpt_root(self):
        import tools.research_worker_windows as worker

        page = FakePage()
        notes = []
        session = SimpleNamespace(page=page, context=FakeContext([page]), _note=notes.append)

        result = await worker.open_fresh_chat(session)

        self.assertIs(result, page)
        self.assertEqual(page.url, "https://chatgpt.com/")
        self.assertEqual(len(page.goto_calls), 1)
        self.assertIn("Nuevo chat", notes[-1])

    async def test_ask_retries_once_in_second_fresh_chat(self):
        import tools.research_worker_windows as worker

        page = FakePage()
        notes = []

        class Session:
            def __init__(self):
                self.page = page
                self.context = FakeContext([page])
                self.calls = 0

            def _note(self, message):
                notes.append(message)

            async def ask(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("timeout simulado")
                return "OK"

        session = Session()
        result = await worker.ask_with_fresh_chat_retry(session, ["PROMPT"], {}, max_attempts=2)

        self.assertEqual(result, "OK")
        self.assertEqual(session.calls, 2)
        self.assertEqual(len(page.goto_calls), 2)
        self.assertTrue(any("reintentando" in note.casefold() for note in notes))

    async def test_second_failure_is_propagated(self):
        import tools.research_worker_windows as worker

        page = FakePage()

        class Session:
            def __init__(self):
                self.page = page
                self.context = FakeContext([page])
                self.calls = 0

            def _note(self, message):
                return None

            async def ask(self, *args, **kwargs):
                self.calls += 1
                raise RuntimeError(f"fallo-{self.calls}")

        session = Session()
        with self.assertRaisesRegex(RuntimeError, "fallo-2"):
            await worker.ask_with_fresh_chat_retry(session, ["PROMPT"], {}, max_attempts=2)
        self.assertEqual(session.calls, 2)


if __name__ == "__main__":
    unittest.main()
