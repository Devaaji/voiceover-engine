"""What a pipeline step of a voiceover job works with (in place of backend/app/pipeline/context.py)."""

import logging
from dataclasses import dataclass, field
from typing import Callable

from voiceover.core.paths import JobPaths
from voiceover.schemas.settings import VoiceChoice
from voiceover.segments import Segment

log = logging.getLogger("voiceover")


@dataclass
class StepContext:
    job_id: str
    paths: JobPaths
    segments: list[Segment]
    voice: VoiceChoice
    # The pronunciation list: written term -> how the voice says it.
    terms: dict[str, str]
    # The line the first segment opens with, when the request asked for one; empty otherwise.
    opening_line: str = ""
    # Make the voice again even where a kept one fits.
    force: bool = False
    warnings: list[str] = field(default_factory=list)
    on_progress: Callable[[str], None] | None = None
    voice_credits: int = 0

    def warn(self, message: str) -> None:
        log.warning("[%s] %s", self.job_id, message)
        if message not in self.warnings:
            self.warnings.append(message)

    def progress(self, message: str) -> None:
        if self.on_progress is not None:
            self.on_progress(message)
