import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch


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


async def _zero_assistant_count(_session):
    return 0


async def _never_dom_result(*_args, **_kwargs):
    await asyncio.sleep(3600)


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
        from app.worker_chat_policy import WorkerChatRouter

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
        with (
            patch.object(worker, "assistant_message_count", new=_zero_assistant_count),
            patch.object(worker, "wait_for_new_assistant_json", new=_never_dom_result),
        ):
            result = await worker.ask_in_job_chat_retry(
                session,
                ["PROMPT"],
                {},
                chat_key="job-retry",
                router=WorkerChatRouter(),
                max_attempts=2,
            )

        self.assertEqual(result, "OK")
        self.assertEqual(session.calls, 2)
        self.assertEqual(len(page.goto_calls), 2)
        self.assertTrue(any("reintentando" in note.casefold() for note in notes))

    async def test_second_failure_is_propagated(self):
        import tools.research_worker_windows as worker
        from app.worker_chat_policy import WorkerChatRouter

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
        with (
            patch.object(worker, "assistant_message_count", new=_zero_assistant_count),
            patch.object(worker, "wait_for_new_assistant_json", new=_never_dom_result),
        ):
            with self.assertRaisesRegex(RuntimeError, "fallo-2"):
                await worker.ask_in_job_chat_retry(
                    session,
                    ["PROMPT"],
                    {},
                    chat_key="job-fail",
                    router=WorkerChatRouter(),
                    max_attempts=2,
                )
        self.assertEqual(session.calls, 2)
        self.assertEqual(len(page.goto_calls), 2)

    async def test_dom_fallback_can_continue_next_turn_in_same_chat(self):
        import tools.research_worker_windows as worker
        from app.worker_chat_policy import WorkerChatRouter

        page = FakePage()
        notes = []
        dom_calls = 0

        class Session:
            def __init__(self):
                self.page = page
                self.context = FakeContext([page])
                self.calls = 0
                self.cancelled_calls = 0

            def _note(self, message):
                notes.append(message)

            async def ask(self, *args, **kwargs):
                self.calls += 1
                self.page.url = "https://chatgpt.com/c/shared-price-research"
                if self.calls == 1:
                    try:
                        await asyncio.Event().wait()
                    except asyncio.CancelledError:
                        self.cancelled_calls += 1
                        raise
                return '{"turn":2}'

        session = Session()

        async def dom_fallback(*_args, **_kwargs):
            nonlocal dom_calls
            dom_calls += 1
            if dom_calls == 1:
                while session.calls < 1:
                    await asyncio.sleep(0)
                return '{"turn":1}'
            await asyncio.sleep(3600)

        router = WorkerChatRouter()
        with (
            patch.object(worker, "assistant_message_count", new=_zero_assistant_count),
            patch.object(worker, "wait_for_new_assistant_json", new=dom_fallback),
        ):
            first = await worker.ask_in_job_chat_retry(
                session,
                ["P2"],
                {},
                chat_key="same-price-job",
                router=router,
                max_attempts=1,
            )
            second = await worker.ask_in_job_chat_retry(
                session,
                ["P3"],
                {},
                chat_key="same-price-job",
                router=router,
                max_attempts=1,
            )

        self.assertEqual(first, '{"turn":1}')
        self.assertEqual(second, '{"turn":2}')
        self.assertEqual(session.calls, 2)
        self.assertEqual(session.cancelled_calls, 1)
        self.assertEqual(len(page.goto_calls), 1, "P3 must not open a second fresh chat after DOM fallback")
        self.assertEqual(page.url, "https://chatgpt.com/c/shared-price-research")
        self.assertTrue(any("JSON final detectado directamente en el DOM" in note for note in notes))


if __name__ == "__main__":
    unittest.main()
