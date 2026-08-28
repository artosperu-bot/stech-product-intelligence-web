import unittest
from types import SimpleNamespace


class FakePage:
    def __init__(self, url, closed=False):
        self.url = url
        self._closed = closed

    def is_closed(self):
        return self._closed


class FakeContext:
    def __init__(self, pages):
        self.pages = pages

    async def new_page(self):
        page = FakePage("about:blank", closed=False)
        self.pages.append(page)
        return page


class WorkerPageRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_reuses_live_chatgpt_page_when_saved_page_is_closed(self):
        import tools.research_worker_windows as worker

        recover = getattr(worker, "recover_chatgpt_page", None)
        self.assertIsNotNone(recover, "worker must expose recover_chatgpt_page")
        if recover is None:
            return

        closed = FakePage("https://chatgpt.com/c/old", closed=True)
        live = FakePage("https://chatgpt.com/", closed=False)
        session = SimpleNamespace(
            page=closed,
            context=FakeContext([closed, live]),
            _note=lambda message: None,
        )

        page = await recover(session)

        self.assertIs(page, live)
        self.assertIs(session.page, live)


if __name__ == "__main__":
    unittest.main()
