"""What the voice speaks: a script cut into segments, each with its holds.

A segment stands in for a scene of the Video Automation repo (backend/app/schemas/script.py), with the fields the
copied audio code reads (id, type, narration, holds), so services/holds.py works unchanged. Its kind says which kind
of scene it is paused like:

- "explain" is paused like a slide of points: a pause after each sentence that carries an idea (the human rhythm);
- "section" like a section card: a pause at its end;
- "plain" like a title: only the pauses the script marks.

"[pause]" in the text is a hold, as the script writer's marks were: after a question a think pause (3 s), anywhere
else a look pause (1.5 s).
"""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from voiceover.core.constants import HOLD_PAUSE_SECONDS
from voiceover.core.exceptions import AppError
from voiceover.utils.text import with_opening

Kind = Literal["explain", "section", "plain"]
KINDS: tuple[str, ...] = ("explain", "section", "plain")
# The scene type of the old pipeline each kind is paused like.
SCENE_TYPES = {"explain": "points", "section": "section", "plain": "title"}
DEFAULT_KIND: Kind = "explain"
# A blank line ends a segment.
BLANK_LINE = re.compile(r"\n\s*\n")
# ElevenLabs takes at most 10,000 characters in one request with eleven_multilingual_v2.
MAX_SEGMENT_CHARS = 9500


class Hold(BaseModel):
    """Silence put into the segment's voice, right before the words `before` (or at its end when empty).

    Copied from backend/app/schemas/script.py of the Video Automation repo.
    """

    before: str = ""
    # None: as long as its kind says (services/holds.py), which is what the writer's marks get.
    seconds: float | None = Field(default=None, gt=0, le=10)

    @field_validator("seconds")
    @classmethod
    def _kind_for_the_old_default(cls, value: float | None) -> float | None:
        # Every mark got HOLD_PAUSE_SECONDS before holds had kinds: such a hold gets its kind's length.
        return None if value == HOLD_PAUSE_SECONDS else value


class Segment(BaseModel):
    id: str
    kind: Kind = DEFAULT_KIND
    narration: str = Field(min_length=1)
    holds: list[Hold] = []

    @property
    def type(self) -> str:
        """The scene type of the old pipeline this segment is paused like."""
        return SCENE_TYPES[self.kind]

    @property
    def actions(self) -> list:
        """A segment has no clicks or typing: no hold waits for one."""
        return []


class SegmentInput(BaseModel):
    """One segment as a request sends it."""

    text: str
    kind: Kind = DEFAULT_KIND


def cut_script(script: str) -> list[SegmentInput]:
    """A script as plain text: a blank line ends a segment, and every segment is an explanation."""
    text = script.replace("\r\n", "\n").replace("\r", "\n")
    return [SegmentInput(text=part.strip()) for part in BLANK_LINE.split(text) if part.strip()]


def build(parts: list[SegmentInput], opening_line: str = "") -> list[Segment]:
    """The segments the voice speaks: each text's "[pause]" marks taken out as holds, ids s01, s02, ..., and the first
    one starting with the opening line when there is one. Raises AppError for a script the voice cannot speak."""
    from voiceover.services import holds  # holds imports this module

    segments: list[Segment] = []
    for number, part in enumerate(parts, start=1):
        text = " ".join(part.text.split())
        if number == 1 and opening_line.strip():
            text = with_opening(text, opening_line)
        narration, marks = holds.take_marks(text)
        if not narration.strip():
            continue
        if len(narration) > MAX_SEGMENT_CHARS:
            raise AppError(
                f"Segment {number} has {len(narration)} characters; one segment may have at most {MAX_SEGMENT_CHARS}. "
                "Split it with a blank line."
            )
        segments.append(Segment(id=f"s{len(segments) + 1:02d}", kind=part.kind, narration=narration, holds=[Hold(**mark) for mark in marks]))
    if not segments:
        raise AppError("The script has nothing to say.")
    return segments
