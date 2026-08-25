from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
import shutil
import threading
import uuid

@dataclass
class Job:
    id: str
    kind: str
    directory: Path
    created_at: datetime
    payload: dict = field(default_factory=dict)
    artifacts: dict[str, Path] = field(default_factory=dict)

class JobStore:
    def __init__(self, root: Path, ttl_minutes: int = 30):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(minutes=max(1, int(ttl_minutes)))
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()

    def create(self, kind: str) -> Job:
        self.prune()
        jid = uuid.uuid4().hex
        directory = self.root / jid
        directory.mkdir(parents=True, exist_ok=True)
        job = Job(jid, str(kind), directory, datetime.now(timezone.utc))
        with self._lock:
            self._jobs[jid] = job
        return job

    def get(self, job_id: str) -> Job:
        self.prune()
        with self._lock:
            job = self._jobs.get(str(job_id))
        if job is None:
            raise KeyError(job_id)
        return job

    def set_payload(self, job_id: str, payload: dict) -> None:
        self.get(job_id).payload = payload

    def add_artifact(self, job_id: str, name: str, path: Path) -> None:
        self.get(job_id).artifacts[str(name)] = Path(path)

    def prune(self) -> None:
        cutoff = datetime.now(timezone.utc) - self.ttl
        stale = []
        with self._lock:
            for jid, job in self._jobs.items():
                if job.created_at < cutoff:
                    stale.append((jid, job.directory))
            for jid, _ in stale:
                self._jobs.pop(jid, None)
        for _, directory in stale:
            shutil.rmtree(directory, ignore_errors=True)
