import asyncio
import unittest


class RemoteResearchStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_prices_adds_pass_guidance_and_previous_response_state(self):
        from app.research_broker import BROKER
        from app.remote_browser import RemoteChatGPTBrowserSession

        worker_id = "pc-state"
        await BROKER.heartbeat(worker_id)
        session = RemoteChatGPTBrowserSession(research_kind="prices")
        await session.__aenter__()

        first = asyncio.create_task(session.ask("PROMPT BASE PRECIO"))
        await asyncio.sleep(0)
        task1 = await BROKER.claim(worker_id, wait_seconds=0.1)
        self.assertIsNotNone(task1)
        prompt1 = task1["args"][0]
        self.assertIn("STECH PRICE INTELLIGENCE — PASADA 1/3", prompt1)
        self.assertIn("no es cobertura comercial suficiente", prompt1.casefold())
        self.assertNotIn("STECH_RESEARCH_STATE", prompt1)
        response1 = '{"producto":{"marca":"Kingston"},"ofertas":[{"tienda":"Tienda A"}]}'
        await BROKER.complete(task1["task_id"], response1, worker_id)
        self.assertEqual(await first, response1)

        second = asyncio.create_task(session.ask("PROMPT BASE SEGUNDA PASADA"))
        await asyncio.sleep(0)
        task2 = await BROKER.claim(worker_id, wait_seconds=0.1)
        self.assertIsNotNone(task2)
        prompt2 = task2["args"][0]
        self.assertIn("STECH PRICE INTELLIGENCE — PASADA 2/3", prompt2)
        self.assertIn("STECH_RESEARCH_STATE", prompt2)
        self.assertIn("Tienda A", prompt2)
        self.assertIn("No cambies el contrato JSON", prompt2)
        await BROKER.complete(task2["task_id"], "{}", worker_id)
        self.assertEqual(await second, "{}")

    async def test_state_is_bounded_before_next_prompt(self):
        from app.research_broker import BROKER
        from app.remote_browser import RemoteChatGPTBrowserSession

        worker_id = "pc-bounded-state"
        await BROKER.heartbeat(worker_id)
        session = RemoteChatGPTBrowserSession(research_kind="prices")
        await session.__aenter__()

        first = asyncio.create_task(session.ask("PROMPT"))
        await asyncio.sleep(0)
        task1 = await BROKER.claim(worker_id, wait_seconds=0.1)
        huge = "X" * 100000
        await BROKER.complete(task1["task_id"], huge, worker_id)
        self.assertEqual(await first, huge)

        second = asyncio.create_task(session.ask("PROMPT 2"))
        await asyncio.sleep(0)
        task2 = await BROKER.claim(worker_id, wait_seconds=0.1)
        prompt2 = task2["args"][0]
        self.assertLess(len(prompt2), 40000)
        await BROKER.complete(task2["task_id"], "{}", worker_id)
        await second


if __name__ == "__main__":
    unittest.main()
