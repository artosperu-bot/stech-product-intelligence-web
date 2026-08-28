import asyncio
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


if __name__ == "__main__":
    unittest.main()
