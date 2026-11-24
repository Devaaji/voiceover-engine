"""Silent audio with a realistic duration. Zero setup, for testing the pipeline."""

import wave
from pathlib import Path

from voiceover.core.constants import MOCK_WORDS_PER_MINUTE
from voiceover.providers.tts.base import TTSProvider
from voiceover.utils.text import count_words

SAMPLE_RATE = 48_000


class MockTTS(TTSProvider):
    extension = "wav"

    def synthesize(self, text: str, out_path: Path) -> None:
        seconds = max(1.0, count_words(text) / MOCK_WORDS_PER_MINUTE * 60)
        with wave.open(str(out_path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(b"\x00\x00" * int(seconds * SAMPLE_RATE))
