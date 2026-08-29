import unittest

from app.worker_chat_policy import (
    REMOTE_CONTEXT_KWARG,
    WorkerChatRouter,
    composer_has_unsent_prompt,
    pop_remote_context,
    prepare_chatgpt_composer,
)


class FakePage:
    def __init__(self, url):
        self.url = url
        self.gotos = []

    async def goto(self, url, **kwargs):
        self.gotos.append(url)
        self.url = url


class FakeSession:
    def __init__(self):
        self.page = FakePage("https://chatgpt.com/")


class WorkerChatRouterTests(unittest.IsolatedAsyncioTestCase):
    async def test_reuses_same_conversation_for_same_job_and_opens_new_for_new_job(self):
        router = WorkerChatRouter()
        session = FakeSession()
        opened = []

        async def open_new(_session):
            opened.append(True)
            _session.page = FakePage("https://chatgpt.com/")
            return _session.page

        async def recover(_session):
            return _session.page

        await router.prepare("prices-job-1", session, open_new, recover)
        self.assertEqual(len(opened), 1)

        session.page.url = "https://chatgpt.com/c/conversation-one"
        router.remember("prices-job-1", session)

        await router.prepare("prices-job-1", session, open_new, recover)
        self.assertEqual(len(opened), 1, "same job must not open another new chat")
        self.assertEqual(session.page.url, "https://chatgpt.com/c/conversation-one")

        await router.prepare("prices-job-2", session, open_new, recover)
        self.assertEqual(len(opened), 2, "different job must start a new chat")

    async def test_reset_forces_retry_into_new_chat(self):
        router = WorkerChatRouter()
        session = FakeSession()
        opened = []

        async def open_new(_session):
            opened.append(True)
            _session.page = FakePage("https://chatgpt.com/")
            return _session.page

        async def recover(_session):
            return _session.page

        await router.prepare("job", session, open_new, recover)
        session.page.url = "https://chatgpt.com/c/original"
        router.remember("job", session)
        router.reset("job")
        await router.prepare("job", session, open_new, recover)
        self.assertEqual(len(opened), 2)


class PromptDispatchTests(unittest.TestCase):
    def test_detects_full_prompt_left_in_composer(self):
        expected = "SEGUNDA PASADA OBLIGATORIA\nIdentificador: TE-2732S\nNo empieces de cero."
        composer = "SEGUNDA PASADA OBLIGATORIA  Identificador: TE-2732S  No empieces de cero."
        self.assertTrue(composer_has_unsent_prompt(expected, composer))
        self.assertFalse(composer_has_unsent_prompt(expected, ""))
        self.assertFalse(composer_has_unsent_prompt(expected, "SEGUNDA PASADA"))


class _FakeElement:
    def __init__(self, visible=True, editable=True, trial_error=None):
        self.visible = visible
        self.editable = editable
        self.trial_error = trial_error
        self.trial_clicks = 0

    async def is_visible(self):
        return self.visible

    async def is_editable(self):
        return self.editable

    async def click(self, **kwargs):
        self.trial_clicks += 1
        if self.trial_error:
            raise RuntimeError(self.trial_error)


class _FakeLocatorList:
    def __init__(self, elements, on_evaluate_all=None):
        self.elements = elements
        self.on_evaluate_all = on_evaluate_all

    async def count(self):
        return len(self.elements)

    def nth(self, index):
        return self.elements[index]

    async def evaluate_all(self, script):
        if self.on_evaluate_all:
            self.on_evaluate_all()


class _FakeRoleResult:
    def __init__(self, page):
        self.page = page

    @property
    def first(self):
        return self.page.real if self.page.fallback_hidden else self.page.fallback


class _HydratingPage:
    def __init__(self):
        self.url = "https://chatgpt.com/"
        self.real = _FakeElement(visible=True, editable=True)
        self.fallback = _FakeElement(visible=False, editable=True)
        self.fallback_hidden = False

    def locator(self, selector):
        if selector == "#prompt-textarea":
            return _FakeLocatorList([self.real])
        return _FakeLocatorList(
            [self.fallback],
            on_evaluate_all=lambda: setattr(self, "fallback_hidden", True),
        )

    def get_by_role(self, role):
        self.last_role = role
        return _FakeRoleResult(self)


class ComposerReadinessTests(unittest.IsolatedAsyncioTestCase):
    async def test_hides_fallback_textarea_before_legacy_textbox_lookup(self):
        page = _HydratingPage()

        composer = await prepare_chatgpt_composer(
            page,
            timeout_seconds=0.5,
            poll_seconds=0.01,
        )

        self.assertIs(composer, page.real)
        self.assertTrue(page.fallback_hidden)
        self.assertEqual(page.last_role, "textbox")
        self.assertGreaterEqual(page.real.trial_clicks, 2)


class RemoteContextTests(unittest.TestCase):
    def test_pop_remote_context_removes_reserved_kwarg_before_legacy_ask(self):
        kwargs = {"progress": "callback", REMOTE_CONTEXT_KWARG: {"chat_key": "abc", "turn": 2}}
        context = pop_remote_context(kwargs)
        self.assertEqual(context["chat_key"], "abc")
        self.assertEqual(context["turn"], 2)
        self.assertEqual(kwargs, {"progress": "callback"})


if __name__ == "__main__":
    unittest.main()
