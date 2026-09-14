from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import threading
from typing import Callable
import uuid


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


@dataclass
class Job:
    id: str
    kind: str
    directory: Path
    created_at: datetime
    payload: dict = field(default_factory=dict)
    artifacts: dict[str, Path] = field(default_factory=dict)
    state: str = 'CREATED'
    updated_at: datetime = field(default_factory=_utcnow)
    finished_at: datetime | None = None
    public_data: dict = field(default_factory=dict)
    error: str = ''
    _persist_callback: Callable[['Job'], None] | None = field(default=None, repr=False, compare=False)

    def persist(self) -> None:
        if self._persist_callback is not None:
            self._persist_callback(self)

    def set_public_data(self, data: dict) -> None:
        self.public_data = dict(data or {})
        self.updated_at = _utcnow()
        self.persist()

    def add_artifact(self, name: str, path: Path) -> None:
        self.artifacts[str(name)] = Path(path)
        self.updated_at = _utcnow()
        self.persist()


class JobStore:
    MANIFEST_NAME = 'job_manifest.json'
    TERMINAL_STATES = {'COMPLETED', 'ERROR'}

    def __init__(self, root: Path, ttl_minutes: int = 30):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(minutes=max(1, int(ttl_minutes)))
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()

    def _manifest_path(self, directory: Path) -> Path:
        return Path(directory) / self.MANIFEST_NAME

    def _artifact_for_manifest(self, job: Job, path: Path) -> str:
        path = Path(path)
        try:
            return str(path.relative_to(job.directory))
        except ValueError:
            return str(path)

    def _artifact_from_manifest(self, directory: Path, value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else directory / path

    def _persist_job(self, job: Job) -> None:
        manifest = self._manifest_path(job.directory)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        data = {
            'id': job.id,
            'kind': job.kind,
            'created_at': job.created_at.isoformat(),
            'updated_at': job.updated_at.isoformat(),
            'finished_at': job.finished_at.isoformat() if job.finished_at else None,
            'state': job.state,
            'error': job.error,
            'public_data': job.public_data,
            'artifacts': {
                name: self._artifact_for_manifest(job, path)
                for name, path in job.artifacts.items()
            },
        }
        temp = manifest.with_name(manifest.name + '.tmp')
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(manifest)

    def _load_job(self, job_id: str) -> Job | None:
        directory = self.root / str(job_id)
        manifest = self._manifest_path(directory)
        if not manifest.exists():
            return None
        try:
            data = json.loads(manifest.read_text(encoding='utf-8'))
            created_at = _parse_datetime(data.get('created_at')) or _utcnow()
            updated_at = _parse_datetime(data.get('updated_at')) or created_at
            finished_at = _parse_datetime(data.get('finished_at'))
            artifacts = {
                str(name): self._artifact_from_manifest(directory, str(value))
                for name, value in (data.get('artifacts') or {}).items()
            }
            return Job(
                id=str(data.get('id') or job_id),
                kind=str(data.get('kind') or ''),
                directory=directory,
                created_at=created_at,
                artifacts=artifacts,
                state=str(data.get('state') or 'CREATED'),
                updated_at=updated_at,
                finished_at=finished_at,
                public_data=dict(data.get('public_data') or {}),
                error=str(data.get('error') or ''),
                _persist_callback=self._persist_job,
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None

    def create(self, kind: str) -> Job:
        self.prune()
        jid = uuid.uuid4().hex
        directory = self.root / jid
        directory.mkdir(parents=True, exist_ok=True)
        now = _utcnow()
        job = Job(
            jid,
            str(kind),
            directory,
            now,
            updated_at=now,
            _persist_callback=self._persist_job,
        )
        with self._lock:
            self._jobs[jid] = job
            self._persist_job(job)
        return job

    def get(self, job_id: str) -> Job:
        self.prune()
        key = str(job_id)
        with self._lock:
            job = self._jobs.get(key)
            if job is None:
                job = self._load_job(key)
                if job is not None:
                    self._jobs[key] = job
        if job is None:
            raise KeyError(job_id)
        return job

    def set_payload(self, job_id: str, payload: dict) -> None:
        job = self.get(job_id)
        job.payload = payload
        job.updated_at = _utcnow()
        job.persist()

    def set_public_data(self, job_id: str, data: dict) -> None:
        self.get(job_id).set_public_data(data)

    def add_artifact(self, job_id: str, name: str, path: Path) -> None:
        self.get(job_id).add_artifact(name, path)

    def mark_running(self, job_id: str) -> Job:
        job = self.get(job_id)
        job.state = 'RUNNING'
        job.finished_at = None
        job.error = ''
        job.updated_at = _utcnow()
        job.persist()
        return job

    def mark_completed(self, job_id: str) -> Job:
        job = self.get(job_id)
        now = _utcnow()
        job.state = 'COMPLETED'
        job.updated_at = now
        job.finished_at = now
        job.error = ''
        job.persist()
        return job

    def mark_error(self, job_id: str, message: str) -> Job:
        job = self.get(job_id)
        now = _utcnow()
        job.state = 'ERROR'
        job.updated_at = now
        job.finished_at = now
        job.error = str(message or '')
        job.persist()
        return job

    def prune(self) -> None:
        cutoff = _utcnow() - self.ttl
        stale: list[tuple[str, Path]] = []
        with self._lock:
            known_ids = set(self._jobs)
            for directory in self.root.iterdir():
                if directory.is_dir():
                    known_ids.add(directory.name)

            for jid in known_ids:
                job = self._jobs.get(jid) or self._load_job(jid)
                if job is None:
                    continue
                if (
                    job.state in self.TERMINAL_STATES
                    and job.finished_at is not None
                    and job.finished_at < cutoff
                ):
                    stale.append((jid, job.directory))

            for jid, _ in stale:
                self._jobs.pop(jid, None)

        for _, directory in stale:
            shutil.rmtree(directory, ignore_errors=True)
