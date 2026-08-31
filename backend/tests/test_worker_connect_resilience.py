import unittest

import httpx

from app.remote_browser import wait_for_worker_online
from app.worker_runtime import register_worker_with_retry


class _Response:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://example.test/heartbeat")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("status error", request=request, response=response)


class _TransientHeartbeatClient:
    def __init__(self):
        self.calls = 0
        self.timeouts = []

    async def post(self, url, **kwargs):
        self.calls += 1
        self.timeouts.append(kwargs.get("timeout"))
        if self.calls == 1:
            raise httpx.ReadTimeout("Render heartbeat tardó demasiado")
        return _Response(200)


class WorkerRegistrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_transient_read_timeout_retries_instead_of_killing_worker(self):
        client = _TransientHeartbeatClient()
        sleeps = []
        logs = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        response = await register_worker_with_retry(
            client,
            "https://render.test",
            "PC020",
            retry_delay_seconds=0.01,
            heartbeat_timeout_seconds=60.0,
            sleep=fake_sleep,
            log=logs.append,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(client.calls, 2)
        self.assertEqual(sleeps, [0.01])
        self.assertEqual(client.timeouts, [60.0, 60.0])
        self.assertTrue(any("ReadTimeout" in message for message in logs))


class WorkerOnlineGraceTests(unittest.IsolatedAsyncioTestCase):
    async def test_waits_for_worker_that_becomes_online_during_grace_window(self):
        statuses = [
            {"online": False, "worker_id": None},
            {"online": False, "worker_id": None},
            {"online": True, "worker_id": "PC020"},
        ]
        sleeps = []

        async def status_provider():
            return statuses.pop(0)

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        status = await wait_for_worker_online(
            status_provider,
            grace_seconds=2.0,
            poll_seconds=0.5,
            sleep=fake_sleep,
        )

        self.assertTrue(status["online"])
        self.assertEqual(status["worker_id"], "PC020")
        self.assertEqual(sleeps, [0.5, 0.5])


if __name__ == "__main__":
    unittest.main()
