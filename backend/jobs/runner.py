"""Runs voiceover jobs in the background, at most MAX_CONCURRENT_JOBS at a time, in this process.

A job that was queued or running when the server stopped is marked failed when it starts again: its thread is gone.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

import httpx

from jobs import store
from jobs.models import Job
from jobs import engine
from voiceover.core.config import MAX_CONCURRENT_JOBS

log = logging.getLogger(__name__)

_pool = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_JOBS, thread_name_prefix="voiceover")
# Saving a job's progress from its thread while the API reads it: write_json is atomic, this keeps one writer.
_lock = threading.Lock()
CALLBACK_TIMEOUT_SECONDS = 10


def recover() -> None:
    """Jobs left queued or running by a server that stopped are failed: nothing runs them any more."""
    for job in store.all_jobs():
        if job.status in ("queued", "running"):
            job.status = "failed"
            job.error = "The server restarted while this job was waiting or running. Send the request again."
            store.save(job)


def submit(job: Job) -> None:
    _pool.submit(_run, job.id)


def _run(job_id: str) -> None:
    job = store.load(job_id)
    request = store.request_of(job_id)

    def update(**changes) -> None:
        with _lock:
            for key, value in changes.items():
                setattr(job, key, value)
            store.save(job)

    update(status="running", step="starting", progress="")
    try:
        engine.run(job_id, request, update)
        update(status="done", step=None, progress="Done")
    except Exception as error:  # every failure ends the job with its reason
        log.exception("[%s] failed", job_id)
        update(status="failed", error=str(error) or error.__class__.__name__)
    if request.callbackUrl:
        _callback(str(request.callbackUrl), store.load(job_id))


def _callback(url: str, job: Job) -> None:
    try:
        httpx.post(url, json=job.model_dump(mode="json"), timeout=CALLBACK_TIMEOUT_SECONDS)
    except httpx.HTTPError as error:
        log.warning("[%s] the callback to %s failed: %s", job.id, url, error)
