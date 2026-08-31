import unittest

from app.worker_chat_policy import prepare_chatgpt_composer


class _Element:
    def __init__(self, *, visible=True, editable=True, element_id="prompt-textarea", role="textbox"):
        self.visible = visible
        self.editable = editable
        self.element_id = element_id
        self.role = role
        self.connected = True
        self.attrs = {}
        self.clicks = 0
        self.on_probe = None

    async def is_visible(self):
        return self.visible

    async def is_editable(self):
        return self.editable

    async def click(self, **kwargs):
        self.clicks += 1
        raise AssertionError("readiness must not depend on click actionability")

    async def evaluate(self, script, arg=None):
        if "setAttribute('data-stech-composer-probe'" in script:
            self.attrs["data-stech-composer-probe"] = arg
            if self.on_probe:
                callback = self.on_probe
                self.on_probe = None
                callback()
            return True
        if "removeAttribute('data-stech-composer-probe'" in script:
            self.attrs.pop("data-stech-composer-probe", None)
            return True
        if "isConnected" in script and "id:" in script:
            return {
                "connected": self.connected,
                "id": self.element_id,
                "role": self.role,
                "contenteditable": "true" if self.editable else "false",
                "ariaHidden": self.attrs.get("aria-hidden", ""),
            }
        if "isConnected" in script:
            return self.connected
        return None

    async def get_attribute(self, name):
        if name == "id":
            return self.element_id
        if name == "role":
            return self.role
        if name == "contenteditable":
            return "true" if self.editable else "false"
        return self.attrs.get(name)


class _LocatorList:
    def __init__(self, page, selector):
        self.page = page
        self.selector = selector

    async def count(self):
        if self.selector == "#prompt-textarea":
            return 1 if self.page.current is not None else 0
        return 1 if self.page.fallback is not None else 0

    def nth(self, index):
        if self.selector == "#prompt-textarea":
            return self.page.current
        return self.page.fallback

    @property
    def first(self):
        return self.nth(0)

    async def evaluate_all(self, script):
        if self.page.fallback is not None:
            self.page.fallback.attrs["aria-hidden"] = "true"
            self.page.fallback.attrs["tabindex"] = "-1"
            self.page.fallback_hidden = True


class _RoleResult:
    def __init__(self, page):
        self.page = page

    @property
    def first(self):
        if self.page.fallback is not None and not self.page.fallback_hidden:
            return self.page.fallback
        return self.page.current


class _Page:
    def __init__(self):
        self.url = "https://chatgpt.com/"
        self.current = _Element()
        self.fallback = _Element(visible=False, editable=True, element_id="", role="textbox")
        self.fallback_hidden = False

    def locator(self, selector):
        return _LocatorList(self, selector)

    def get_by_role(self, role):
        self.last_role = role
        return _RoleResult(self)


class ComposerHydrationHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def test_ready_composer_never_uses_trial_click(self):
        page = _Page()

        composer = await prepare_chatgpt_composer(
            page,
            timeout_seconds=0.5,
            poll_seconds=0.01,
            stable_checks=2,
        )

        self.assertIs(composer, page.current)
        self.assertTrue(page.fallback_hidden)
        self.assertEqual(page.last_role, "textbox")
        self.assertEqual(page.current.clicks, 0)

    async def test_retries_when_react_replaces_composer_node_after_probe(self):
        page = _Page()
        first = page.current
        replacement = _Element()
        first.on_probe = lambda: setattr(page, "current", replacement)

        composer = await prepare_chatgpt_composer(
            page,
            timeout_seconds=0.8,
            poll_seconds=0.01,
            stable_checks=2,
        )

        self.assertIs(composer, replacement)
        self.assertEqual(first.clicks, 0)
        self.assertEqual(replacement.clicks, 0)

    async def test_accessible_textbox_must_resolve_to_real_prompt_textarea(self):
        page = _Page()
        page.fallback.visible = True

        composer = await prepare_chatgpt_composer(
            page,
            timeout_seconds=0.5,
            poll_seconds=0.01,
            stable_checks=2,
        )

        self.assertIs(composer, page.current)
        self.assertEqual(await page.get_by_role("textbox").first.get_attribute("id"), "prompt-textarea")


if __name__ == "__main__":
    unittest.main()
