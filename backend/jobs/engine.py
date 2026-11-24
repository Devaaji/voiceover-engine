"""What a job does, step by step: the script, the narration, the voice, the finished audio, the transcript."""

import json
from typing import Callable

from jobs.models import VoiceoverRequest
from voiceover.core import config
from voiceover.core.exceptions import AppError
from voiceover import ffmpeg_version
from voiceover.core.paths import JobPaths
from voiceover.pipeline import assemble, transcript, voice
from voiceover.pipeline.context import StepContext
from voiceover.schemas.settings import VoiceChoice
from voiceover.segments import SegmentInput, build, cut_script
from voiceover.services import pronunciation_service, voice_config
from voiceover.utils import ffmpeg
from voiceover.utils.text import with_opening
from writing import calls as llm_calls
from writing import restyle

Update = Callable[..., None]


def opening_line(request: VoiceoverRequest) -> str:
    """The line the voiceover opens with: the request's own, the one from .env when it sends opening: true, or none."""
    if request.openingLine and request.openingLine.strip():
        return request.openingLine.strip()
    return config.OPENING_LINE if request.opening else ""


def run(job_id: str, request: VoiceoverRequest, update: Update) -> None:
    paths = JobPaths(job_id)
    paths.ensure()
    warnings: list[str] = []
    claude_calls: list[dict] = []

    def warn(message: str) -> None:
        if message not in warnings:
            warnings.append(message)
            update(warnings=list(warnings))

    if request.mode == "content":
        raise AppError('Mode "content" is not available yet. Send a finished script with mode "script".')

    ffmpeg.require()
    # An FFmpeg too old for the pipeline's filters fails here, before anything is spent.
    ffmpeg_version.check()
    choice = VoiceChoice.from_env(request.voiceType or "")
    voice_config.get(choice.voice_type)  # an unknown voice type fails here, before anything is spent
    update(voice=choice.public())

    parts = list(request.segments) if request.segments else cut_script(request.script or "")
    line = opening_line(request)
    if line and parts:
        parts[0] = SegmentInput(text=with_opening(" ".join(parts[0].text.split()), line), kind=parts[0].kind)

    if request.rewrite:
        update(step="writing", progress="Putting the script in the teacher's way of talking")
        try:
            parts = restyle.restyle(parts, line, claude_calls, paths.llm_dir, job_id, warn)
        finally:
            update(claude_calls=list(claude_calls), claude_cost_usd=llm_calls.total(claude_calls))

    segments = build(parts, line)
    paths.segments.write_text(json.dumps([segment.model_dump() for segment in segments], indent=2, ensure_ascii=False), encoding="utf-8")

    ctx = StepContext(
        job_id=job_id,
        paths=paths,
        segments=segments,
        voice=choice,
        terms=pronunciation_service.load(request.pronunciations),
        opening_line=line,
        on_progress=lambda message: update(progress=message),
    )
    ctx.warn = warn  # type: ignore[method-assign]

    update(step="voice", progress=f"0/{len(segments)} segments")
    try:
        voice.run(ctx)
    finally:
        update(voice_credits=ctx.voice_credits)
    update(step="levelling", progress="")
    loudness = assemble.run(ctx, request.format)
    update(step="transcript", progress="", loudness=loudness, duration=loudness.get("seconds"))
    transcript.run(ctx)
    files = sorted(file.name for file in paths.output_dir.iterdir() if file.is_file())
    update(files=files)
