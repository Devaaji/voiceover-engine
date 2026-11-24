"""The interface every voice provider implements."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SpokenTimes:
    """When every character of a spoken text starts. Kept with the audio, so the text can be cut
    into parts in another way later without making the audio again."""

    text: str  # exactly what the voice was given (after the pronunciation list)
    starts: list[float]  # seconds, one per character of `text`

    def part_starts(self, parts: list[str]) -> list[float] | None:
        """When each part starts, if the parts in order make up this text. None if they don't.

        A part without text starts where the next one does.
        """
        if len(self.starts) != len(self.text) or not self.text:
            return None
        found, at = [], 0
        for part in parts:
            while at < len(self.text) and self.text[at] == " ":
                at += 1
            if part and not self.text.startswith(part, at):
                return None
            found.append(float(self.starts[min(at, len(self.starts) - 1)]))
            at += len(part)
        return found if not self.text[at:].strip() else None


class TTSProvider(ABC):
    # File extension of the audio this provider writes ("wav", "mp3").
    extension: str
    # Provider credits this instance has spent so far. None: the provider can't tell, or costs nothing.
    credits: int | None = None

    @abstractmethod
    def synthesize(self, text: str, out_path: Path) -> None:
        """Write the spoken text to out_path. The caller measures the duration."""

    def synthesize_parts(self, parts: list[str], out_path: Path, context: "Context | None" = None) -> SpokenTimes | None:
        """Speak the parts as one text, and say when each of its characters is spoken.

        One audio file, so the voice stays natural from part to part. A provider
        that can't tell the times returns None, and the caller estimates them.
        `context` is what is said around the text, for a provider that can use it.
        """
        self.synthesize(" ".join(parts), out_path)
        return None


@dataclass(frozen=True)
class Context:
    """What the voice says right before and right after a text (the scenes around it). It is not
    spoken: a provider that can use it carries the tone and the pace across, so a scene does not
    start and end as if it stood alone."""

    before: str = ""
    after: str = ""
