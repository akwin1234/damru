"""Small background job runner for the local UI."""
from __future__ import annotations

import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Iterable

from .redact import redact


@dataclass
class Job:
    id: str
    name: str
    command: list[str]
    status: str = "queued"
    returncode: int | None = None
    started_at: float | None = None
    ended_at: float | None = None
    logs: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "command": [redact(part) for part in self.command],
            "status": self.status,
            "returncode": self.returncode,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "logs": self.logs[-400:],
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def list(self) -> list[dict[str, object]]:
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda item: item.started_at or 0, reverse=True)
            return [job.as_dict() for job in jobs]

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def start(self, name: str, args: Iterable[str]) -> Job:
        command = [sys.executable, "-m", "damru", *args]
        job = Job(id=uuid.uuid4().hex[:12], name=name, command=command)
        with self._lock:
            self._jobs[job.id] = job
        thread = threading.Thread(target=self._run, args=(job,), daemon=True)
        thread.start()
        return job

    def _append(self, job: Job, line: str) -> None:
        with self._lock:
            job.logs.append(redact(line.rstrip()))

    def _run(self, job: Job) -> None:
        with self._lock:
            job.status = "running"
            job.started_at = time.time()
            job.logs.append("$ " + " ".join(redact(part) for part in job.command))
        try:
            proc = subprocess.Popen(
                job.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors="replace",
                bufsize=1,
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                self._append(job, line)
            rc = proc.wait()
            with self._lock:
                job.returncode = rc
                job.status = "success" if rc == 0 else "failed"
        except Exception as exc:
            with self._lock:
                job.returncode = -1
                job.status = "failed"
                job.logs.append(redact(f"error: {exc}"))
        finally:
            with self._lock:
                job.ended_at = time.time()
