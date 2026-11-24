"""Picks the voice provider (backend/app/providers/tts/registry.py of the Video Automation repo).

voiceover-engine: the choice comes from VoiceChoice (.env and the request) instead of the app's settings, and the
local Kokoro voice is not copied.
"""

from voiceover.providers.tts.base import TTSProvider
from voiceover.providers.tts.elevenlabs import ElevenLabsTTS
from voiceover.providers.tts.mock import MockTTS
from voiceover.providers.tts.pronunciation import PronouncingTTS
from voiceover.schemas.settings import VoiceChoice
from voiceover.services import voice_config


def get_tts_provider(settings: VoiceChoice, pronunciations: dict[str, str]) -> TTSProvider:
    """The chosen provider, with the pronunciation list applied to everything it is asked to say.

    Raises ProviderUnavailable if the provider can't be used.
    """
    return PronouncingTTS(_provider(settings), pronunciations)


def _provider(settings: VoiceChoice) -> TTSProvider:
    if settings.tts_provider == "elevenlabs":
        style = voice_config.style(settings.voice_type)
        return ElevenLabsTTS(
            settings.elevenlabs_api_key,
            settings.elevenlabs_voice_id,
            settings.elevenlabs_model_id,
            style.model_dump() if style else None,
        )
    return MockTTS()
