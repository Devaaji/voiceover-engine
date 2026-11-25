"""POST /voiceover, GET /voiceover/{id}, GET /voiceover/{id}/files/{name}, GET /voice-types."""

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import FileResponse

from api.security import require_api_key
from jobs import runner, store
from jobs.models import Job, VoiceoverRequest
from voiceover.core import config
from voiceover.core.exceptions import AppError, NotFound
from voiceover.core.paths import JobPaths
from voiceover.services import voice_config

router = APIRouter(dependencies=[Depends(require_api_key)])

# The files a job may serve, and their types.
FILES = {
    "audio.mp3": "audio/mpeg",
    "audio.wav": "audio/wav",
    "transcript.json": "application/json",
    "subtitles.srt": "application/x-subrip",
    "subtitles.vtt": "text/vtt",
    "script.json": "application/json",
}


def _with_links(job: Job, request: Request) -> dict:
    data = job.model_dump(mode="json")
    data["statusUrl"] = str(request.url_for("get_voiceover", job_id=job.id))
    data["fileUrls"] = {name: str(request.url_for("get_voiceover_file", job_id=job.id, name=name)) for name in job.files}
    return data


@router.post("/voiceover", status_code=status.HTTP_202_ACCEPTED)
def create_voiceover(body: VoiceoverRequest, request: Request) -> dict:
    """Start a job. It runs in the background: poll statusUrl until status is "done" or "failed"."""
    if body.mode == "content":
        raise AppError('Mode "content" is not available yet. Send a finished script with mode "script".')
    if body.voiceType:
        voice_config.get(body.voiceType)  # an unknown voice type is refused now, not in the job
    job = store.create(body)
    runner.submit(job)
    return _with_links(job, request)


@router.get("/voiceover/{job_id}", name="get_voiceover")
def get_voiceover(job_id: str, request: Request) -> dict:
    return _with_links(store.load(job_id), request)


@router.get("/voiceover/{job_id}/files/{name}", name="get_voiceover_file")
def get_voiceover_file(job_id: str, name: str) -> FileResponse:
    store.load(job_id)
    if name not in FILES:
        raise NotFound(f'There is no file "{name}". A job has: {", ".join(FILES)}.')
    file = JobPaths(job_id).output(name)
    if not file.exists():
        raise NotFound(f'The job has no "{name}" (yet).')
    return FileResponse(file, media_type=FILES[name], filename=name)


@router.get("/voice-types")
def voice_types() -> list[dict]:
    """The voice types of config/voice.json, for a request's voiceType. `default` marks the one VOICE_TYPE in .env
    picks, the one a request without voiceType is made with."""
    return [{**choice.model_dump(), "default": choice.id == config.VOICE_TYPE} for choice in voice_config.choices()]
