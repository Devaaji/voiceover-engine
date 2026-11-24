"""The voice a job is made with, and an ElevenLabs voice as its API lists it.

voiceover-engine: `Voice` is copied from backend/app/schemas/settings.py of the Video Automation repo
(providers/tts/elevenlabs.py lists voices with it). `VoiceChoice` takes the place of its Settings: what a job's voice
is made with, from .env and the request.
"""

from typing import Literal

from pydantic import BaseModel

from voiceover.core import config


class Voice(BaseModel):
    voice_id: str
    name: str
    category: str = ""
    preview_url: str | None = None


class VoiceChoice(BaseModel):
    tts_provider: Literal["elevenlabs", "mock"] = "elevenlabs"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model_id: str = ""
    # How the voice is made (its style, the wording of its narration, its leveler): a type from voice.json.
    voice_type: str = ""

    @classmethod
    def from_env(cls, voice_type: str = "") -> "VoiceChoice":
        provider = "mock" if config.TTS_PROVIDER == "mock" else "elevenlabs"
        return cls(
            tts_provider=provider,
            elevenlabs_api_key=config.ELEVENLABS_API_KEY,
            elevenlabs_voice_id=config.ELEVENLABS_VOICE_ID,
            elevenlabs_model_id=config.ELEVENLABS_MODEL_ID,
            voice_type=voice_type or config.VOICE_TYPE,
        )

    def public(self) -> dict:
        """What the job keeps of it: everything but the key."""
        return self.model_dump(exclude={"elevenlabs_api_key"})
