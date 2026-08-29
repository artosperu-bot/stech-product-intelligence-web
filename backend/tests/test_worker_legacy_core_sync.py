import base64
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def _write_bundle(bundle_dir: Path, files: dict[str, str]) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as tf:
        for name, text in files.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(f"backend/legacy_core/{name}")
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    encoded = base64.b64encode(payload.getvalue()).decode("ascii")
    (bundle_dir / "part-01.b64").write_text(encoded, encoding="ascii")


class WorkerLegacyCoreSyncTests(unittest.TestCase):
    def test_existing_stale_core_is_replaced_from_current_bundle(self):
        import tools.research_worker_windows as worker

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            core = root / "backend" / "legacy_core"
            bundle = root / "legacy_core_bundle_v2"
            core.mkdir(parents=True)
            (core / "chatgpt_browser.py").write_text("OLD", encoding="utf-8")
            (core / "stale.py").write_text("STALE", encoding="utf-8")
            _write_bundle(
                bundle,
                {
                    "chatgpt_browser.py": "NEW",
                    "price_workflow.py": "PRICE-V2",
                },
            )

            with (
                patch.object(worker, "ROOT", root),
                patch.object(worker, "CORE_DIR", core),
                patch.object(worker, "BUNDLE_DIR", bundle),
            ):
                worker.ensure_legacy_core()

            self.assertEqual((core / "chatgpt_browser.py").read_text(encoding="utf-8"), "NEW")
            self.assertEqual((core / "price_workflow.py").read_text(encoding="utf-8"), "PRICE-V2")
            self.assertFalse((core / "stale.py").exists())


if __name__ == "__main__":
    unittest.main()
