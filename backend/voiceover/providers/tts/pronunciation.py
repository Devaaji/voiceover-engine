"""Applies the pronunciation list in front of any voice provider."""

from pathlib import Path

from voiceover.providers.tts.base import Context, SpokenTimes, TTSProvider
from voiceover.utils.text import apply_pronunciations


class PronouncingTTS(TTSProvider):
    """Rewrites written terms into their spoken form, then hands the text to the real provider."""

    def __init__(self, provider: TTSProvider, pronunciations: dict[str, str]) -> None:
        self._provider = provider
        self._pronunciations = pronunciations
        self.extension = provider.extension

    @property
    def credits(self) -> int | None:
        return self._provider.credits

    def synthesize(self, text: str, out_path: Path) -> None:
        self._provider.synthesize(apply_pronunciations(text, self._pronunciations), out_path)

    def synthesize_parts(self, parts: list[str], out_path: Path, context: Context | None = None) -> SpokenTimes | None:
        # Each part on its own, so a part's place in the spoken text is known.
        spoken = [apply_pronunciations(part, self._pronunciations) for part in parts]
        if context is None:
            return self._provider.synthesize_parts(spoken, out_path)
        around = Context(*(apply_pronunciations(text, self._pronunciations) for text in (context.before, context.after)))
        return self._provider.synthesize_parts(spoken, out_path, context=around)
