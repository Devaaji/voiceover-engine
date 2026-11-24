"""Jobs on disk: data/jobs/<id>/job.json, and the request beside it."""

import secrets
from datetime import datetime, timezone

from jobs.models import Job, VoiceoverRequest
from voiceover.core.config import JOBS_DIR
from voiceover.core.exceptions import JobNotFound
from voiceover.core.paths import JobPaths
from voiceover.utils.files import read_json, write_json


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return f"vo-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"


def create(request: VoiceoverRequest) -> Job:
    job = Job(id=new_id(), mode=request.mode, created_at=now(), updated_at=now())
    paths = JobPaths(job.id)
    paths.ensure()
    write_json(paths.request, request.model_dump(mode="json"))
    save(job)
    return job


def save(job: Job) -> None:
    job.updated_at = now()
    write_json(JobPaths(job.id).job_file, job.model_dump(mode="json"))


def load(job_id: str) -> Job:
    paths = JobPaths(job_id)
    if not job_id.replace("-", "").isalnum() or not paths.job_file.exists():
        raise JobNotFound(f'There is no job "{job_id}".')
    return Job.model_validate(read_json(paths.job_file))


def request_of(job_id: str) -> VoiceoverRequest:
    return VoiceoverRequest.model_validate(read_json(JobPaths(job_id).request))


def all_jobs() -> list[Job]:
    if not JOBS_DIR.exists():
        return []
    found = []
    for folder in JOBS_DIR.iterdir():
        try:
            found.append(load(folder.name))
        except Exception:  # a broken or half-made folder is not a job
            continue
    return found
