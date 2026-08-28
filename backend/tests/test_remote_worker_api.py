import asyncio
import json
import os
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient


class RemoteWorkerApiTests(unittest.TestCase):
    def test_heartbeat_requires_bearer_token(self):
        from app.worker_api import router
        app = FastAPI()
        app.include_router(router)
        with patch.dict(os.environ, {"STECH_RESEARCH_WORKER_TOKEN": "secret"}, clear=False):
            client = TestClient(app)
            unauth = client.post("/api/research-worker/heartbeat", json={"worker_id": "pc"})
            self.assertEqual(unauth.status_code, 401)
            ok = client.post(
                "/api/research-worker/heartbeat",
                headers={"Authorization": "Bearer secret"},
                json={"worker_id": "pc"},
            )
            self.assertEqual(ok.status_code, 200)
            self.assertEqual(ok.json()["worker_id"], "pc")


class RemoteBrowserSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_remote_session_round_trip_uses_broker(self):
        from app.research_broker import BROKER
        from app.remote_browser import RemoteChatGPTBrowserSession

        await BROKER.heartbeat("pc-test")
        session = RemoteChatGPTBrowserSession()
        await session.__aenter__()
        asking = asyncio.create_task(session.ask("PROMPT"))
        await asyncio.sleep(0)
        task = await BROKER.claim("pc-test", wait_seconds=0.1)
        self.assertEqual(task["args"], ["PROMPT"])
        await BROKER.complete(task["task_id"], "RESPUESTA", "pc-test")
        self.assertEqual(await asking, "RESPUESTA")

    async def test_remote_session_encodes_callable_arguments_for_json_transport(self):
        from app.research_broker import BROKER
        from app.remote_browser import RemoteChatGPTBrowserSession

        await BROKER.heartbeat("pc-callable")
        session = RemoteChatGPTBrowserSession()
        await session.__aenter__()

        def progress(message):
            return None

        asking = asyncio.create_task(session.ask("PROMPT", progress=progress))
        await asyncio.sleep(0)
        task = await BROKER.claim("pc-callable", wait_seconds=0.1)
        self.assertIsNotNone(task)
        json.dumps(task)
        marker = task["kwargs"]["progress"]
        self.assertEqual(marker["__stech_remote_type__"], "callable")
        self.assertEqual(marker["name"], "progress")
        await BROKER.complete(task["task_id"], "RESPUESTA", "pc-callable")
        self.assertEqual(await asking, "RESPUESTA")

    async def test_same_session_keeps_chat_key_and_increments_turn(self):
        from app.research_broker import BROKER
        from app.remote_browser import RemoteChatGPTBrowserSession
        from app.worker_chat_policy import REMOTE_CONTEXT_KWARG

        await BROKER.heartbeat("pc-chat-key")
        session = RemoteChatGPTBrowserSession(research_kind="prices")
        await session.__aenter__()

        asking1 = asyncio.create_task(session.ask("PROMPT 1"))
        await asyncio.sleep(0)
        task1 = await BROKER.claim("pc-chat-key", wait_seconds=0.1)
        context1 = task1["kwargs"][REMOTE_CONTEXT_KWARG]
        self.assertEqual(context1["research_kind"], "prices")
        self.assertEqual(context1["turn"], 1)
        await BROKER.complete(task1["task_id"], '{"offers":[]}', "pc-chat-key")
        await asking1

        asking2 = asyncio.create_task(session.ask("PROMPT 2"))
        await asyncio.sleep(0)
        task2 = await BROKER.claim("pc-chat-key", wait_seconds=0.1)
        context2 = task2["kwargs"][REMOTE_CONTEXT_KWARG]
        self.assertEqual(context2["chat_key"], context1["chat_key"])
        self.assertEqual(context2["turn"], 2)
        await BROKER.complete(task2["task_id"], '{"offers":[]}', "pc-chat-key")
        await asking2


if __name__ == "__main__":
    unittest.main()
