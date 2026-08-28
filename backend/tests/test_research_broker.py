import asyncio
import unittest

from app.research_broker import ResearchBroker


class ResearchBrokerTests(unittest.IsolatedAsyncioTestCase):
    async def test_submit_claim_complete_round_trip(self):
        broker = ResearchBroker(worker_ttl_seconds=30)
        submit_task = asyncio.create_task(
            broker.submit(args=["PROMPT PRECIOS"], kwargs={"timeout": 5}, timeout_seconds=2)
        )
        await asyncio.sleep(0)
        claimed = await broker.claim("worker-1", wait_seconds=0.1)
        self.assertIsNotNone(claimed)
        self.assertEqual(claimed["args"], ["PROMPT PRECIOS"])
        self.assertEqual(claimed["kwargs"], {"timeout": 5})
        await broker.complete(claimed["task_id"], "RESPUESTA CHATGPT", "worker-1")
        self.assertEqual(await submit_task, "RESPUESTA CHATGPT")

    async def test_worker_status_changes_after_heartbeat(self):
        broker = ResearchBroker(worker_ttl_seconds=30)
        self.assertFalse((await broker.status())["online"])
        await broker.heartbeat("pc-stech")
        status = await broker.status()
        self.assertTrue(status["online"])
        self.assertEqual(status["worker_id"], "pc-stech")

    async def test_fail_propagates_to_submitter(self):
        broker = ResearchBroker(worker_ttl_seconds=30)
        submit_task = asyncio.create_task(broker.submit(args=["x"], kwargs={}, timeout_seconds=2))
        await asyncio.sleep(0)
        claimed = await broker.claim("worker-1", wait_seconds=0.1)
        await broker.fail(claimed["task_id"], "CHATGPT_NO_COMPOSER", "worker-1")
        with self.assertRaisesRegex(RuntimeError, "CHATGPT_NO_COMPOSER"):
            await submit_task


if __name__ == "__main__":
    unittest.main()
