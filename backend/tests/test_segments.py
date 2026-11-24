"""A script becomes segments: a blank line ends one, "[pause]" becomes a hold, and the opening line only when asked."""

import pytest

from jobs.engine import opening_line
from jobs.models import VoiceoverRequest
from voiceover.core import config
from voiceover.core.exceptions import AppError
from voiceover.segments import SegmentInput, build, cut_script


def test_a_blank_line_ends_a_segment_and_every_segment_is_an_explanation() -> None:
    parts = cut_script("First part.\nStill the first part.\n\n\n  Second part.  \r\n\r\nThird.")
    assert [part.text for part in parts] == ["First part.\nStill the first part.", "Second part.", "Third."]
    assert {part.kind for part in parts} == {"explain"}


def test_pause_marks_become_holds_and_ids_are_numbered() -> None:
    segments = build([SegmentInput(text="Can you guess? [pause] It is one."), SegmentInput(text="Next.", kind="section")])
    assert [segment.id for segment in segments] == ["s01", "s02"]
    assert segments[0].narration == "Can you guess? It is one."
    assert segments[0].holds[0].before == "It is one."
    assert segments[0].type == "points" and segments[1].type == "section"


def test_the_opening_line_is_added_only_when_given() -> None:
    assert build([SegmentInput(text="Today, robots.")])[0].narration == "Today, robots."
    opened = build([SegmentInput(text="Today, robots.")], "Hey guys! This is Ed Roh.")
    assert opened[0].narration == "Hey guys! This is Ed Roh. Today, robots."
    # A script that already opens with it keeps it once.
    again = build([SegmentInput(text="Hey guys! This is Ed Roh. Today, robots.")], "Hey guys! This is Ed Roh.")
    assert again[0].narration == "Hey guys! This is Ed Roh. Today, robots."


def test_the_opening_is_off_unless_the_request_asks_for_it() -> None:
    assert opening_line(VoiceoverRequest(script="Hi.")) == ""
    assert opening_line(VoiceoverRequest(script="Hi.", opening=True)) == config.OPENING_LINE
    assert opening_line(VoiceoverRequest(script="Hi.", openingLine=" Welcome back! ")) == "Welcome back!"


def test_a_script_with_nothing_to_say_is_refused() -> None:
    with pytest.raises(AppError):
        build([SegmentInput(text="[pause]")])


def test_requests_need_their_text() -> None:
    with pytest.raises(ValueError):
        VoiceoverRequest(mode="script")
    with pytest.raises(ValueError):
        VoiceoverRequest(mode="script", script="a", segments=[SegmentInput(text="b")])
    with pytest.raises(ValueError):
        VoiceoverRequest(mode="content")
    assert VoiceoverRequest(script="Hi.").rewrite is False
