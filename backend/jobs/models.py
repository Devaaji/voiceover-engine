"""A voiceover request, and the job that makes it."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

from voiceover.segments import SegmentInput

Status = Literal["queued", "running", "done", "failed"]


class VoiceoverRequest(BaseModel):
    """POST /voiceover. Mode "script": a finished script, spoken as it is. Mode "content": raw material, written into
    a narration first (not available yet)."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["script", "content"] = "script"
    # Mode "script": the script as text (a blank line ends a segment), or its segments.
    script: str | None = None
    segments: list[SegmentInput] | None = None
    # Mode "content": the material to write the narration from.
    content: str | None = None
    title: str | None = None
    # Mode "content": false stops after the narration is written (output/script.json), without a voice.
    audio: bool = True
    # Mode "script": true puts the script in the teacher's way of talking first. False: spoken word for word.
    rewrite: bool = False
    # A voice type of config/voice.json. Empty: VOICE_TYPE from .env.
    voiceType: str | None = None
    # The opening line: off unless the request sends opening: true (the line from .env) or its own openingLine.
    opening: bool = False
    openingLine: str | None = None
    # Written term -> how the voice says it, on top of config/pronunciations.json.
    pronunciations: dict[str, str] = Field(default_factory=dict)
    format: Literal["mp3", "wav"] = "mp3"
    # Called with the job (POST, JSON) when it is done or failed.
    callbackUrl: HttpUrl | None = None

    @model_validator(mode="after")
    def _has_text(self) -> "VoiceoverRequest":
        if self.mode == "script":
            if not (self.script and self.script.strip()) and not self.segments:
                raise ValueError('Mode "script" needs "script" (text) or "segments".')
            if self.script and self.segments:
                raise ValueError('Send "script" or "segments", not both.')
        elif not (self.content and self.content.strip()):
            raise ValueError('Mode "content" needs "content".')
        return self


class Job(BaseModel):
    id: str
    status: Status = "queued"
    mode: Literal["script", "content"] = "script"
    # The step it is at: writing, voice, levelling, transcript.
    step: str | None = None
    progress: str = ""
    created_at: str
    updated_at: str
    error: str | None = None
    warnings: list[str] = []
    # The voice it is made with (no key).
    voice: dict = {}
    # ElevenLabs credits spent.
    voice_credits: int = 0
    # Claude calls and what they cost.
    claude_calls: list[dict] = []
    claude_cost_usd: float = 0.0
    loudness: dict | None = None
    # Seconds of audio.
    duration: float | None = None
    # The files in output/, for GET /voiceover/{id}/files/{name}.
    files: list[str] = []
