"""The copied code answers as the Video Automation repo's own code does, for the same input.

Runs only when OLD_REPO names that repo's folder (with its backend/.venv): the old code is run there, in its own
Python, on the same cases (old_side.py), and both answers must be equal. Without the old repo (on Railway, say)
these tests are skipped and the golden tests still run.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from voiceover.pipeline.voice import context_of
from voiceover.providers.tts.base import Context, SpokenTimes
from voiceover.providers.tts.elevenlabs import ElevenLabsTTS
from voiceover.segments import Segment
from voiceover.services import holds, narration_style, opening_take, pronunciation_service, voice_config, voice_leveler
from voiceover.utils import ffmpeg, srt
from voiceover.utils.text import apply_pronunciations, split_sentences, with_opening

OLD_REPO = os.getenv("OLD_REPO", "").strip()
FIXTURES = Path(__file__).parents[1] / "golden" / "fixtures"
pytestmark = pytest.mark.skipif(not OLD_REPO, reason="OLD_REPO is not set: the old repo's code is not here to compare with")

TEXTS = [
    "So I'm gonna import useState and useRef from React, and run npx create-next-app.",
    "Next.js renders page.tsx. The ref.current value? It's 3! And JSX shows it.",
    "Hey guys! This is Ed Roh. Today we look at useActionState.",
    "Plain text with an emoji 👋 and a question? Then an answer.",
]
MARKED = [
    "Can you guess what it shows? [pause] It shows one. Watch the list. [pause] There it is.",
    "Pause the video and say it in your own words. [PAUSE] When the form is sent, the save runs.",
    "[pause] Starts with a pause. And ends with one. [pause]",
]
SCENES = [
    {"id": "s01", "type": "points", "narration": "When you tap like, the app waits for the server before anything happens. With this hook the heart turns red at once. So why does it matter? Because people notice the wait.", "holds": []},
    {"id": "s02", "type": "section", "narration": "So the old page works. Now let's see the new way.", "holds": []},
    {"id": "s03", "type": "title", "narration": "Hey guys! This is Ed Roh. Today we look at forms that wait.", "holds": []},
    {"id": "s04", "type": "points", "narration": "Can you say in one sentence what happens when the form is sent? Pause the video and say it in your own words. When the form is sent, the save runs. That is the whole idea, and it is worth saying twice.", "holds": [{"before": "When the form is sent, the"}, {"before": ""}]},
]
BEATS = [
    ("This sentence carries an idea that takes a moment to land.", "So the next one carries on."),
    ("Why does the page wait for the server here?", "Because nothing tells it not to."),
    ("A short one.", "Then another."),
]


def old_answer(cases: dict) -> dict:
    python = Path(OLD_REPO) / "backend" / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    proc = subprocess.run(
        [str(python), str(Path(__file__).with_name("old_side.py")), str(Path(OLD_REPO) / "backend")],
        input=json.dumps(cases), capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(proc.stdout)


def roundtrip(value):
    """As JSON would carry it: tuples become lists."""
    return json.loads(json.dumps(value))


@pytest.fixture(scope="module")
def cases() -> dict:
    terms = pronunciation_service.load()
    leveler = voice_leveler.load_config("teacher")
    audio = []
    for fixture in sorted(FIXTURES.iterdir()):
        expected = json.loads((fixture / "expected.json").read_text(encoding="utf-8"))
        voiced = json.loads((fixture / "voice.json").read_text(encoding="utf-8"))
        voice = fixture / "voice.mp3"
        segment = expected["segment"]
        audio.append({
            "scene": {"id": segment["id"], "type": Segment(**segment).type, "narration": segment["narration"], "holds": segment["holds"]},
            "levels": ffmpeg.rms_levels(voice, holds.LEVEL_FRAME_SECONDS),
            "leveler_levels": ffmpeg.rms_levels(voice, leveler.frame_ms / 1000),
            "voiced": voiced,
            "seconds": ffmpeg.probe_duration(voice),
            "gain_db": 26.5,
            "fills": [[0.0, 0.3], [2.0, 2.6]],
        })
    style_script = {"scenes": [{"id": "s01", "type": "points", "narration": TEXTS[0]}, {"id": "s02", "type": "title", "narration": TEXTS[2]}]}
    return {
        "terms": terms,
        "texts": TEXTS,
        "opening_line": "Hey guys! This is Ed Roh.",
        "marked": MARKED,
        "scenes": SCENES,
        "beats": BEATS,
        "contexts": [[SCENES[0], SCENES[1]], [None, SCENES[2]], [SCENES[3], None]],
        "requests": [[TEXTS[0], "", ""], [TEXTS[1], "Before this. And this.", "After this."]],
        "audio": audio,
        "style_scripts": [[style_script, "Hey guys! This is Ed Roh."], [style_script, ""]],
        "style_problems": [
            [TEXTS[0], TEXTS[0].replace("useRef", "the ref"), [], []],
            [TEXTS[0], "So I'm gonna bring in useState and useRef from React, and then run npx create-next-app.", [], []],
            [MARKED[0], MARKED[0].replace("[pause] ", ""), [], []],
            ["Hey guys! This is Ed Roh. So.", "So. Hey guys!", ["Hey guys! This is Ed Roh."], ["Hey guys! This is Ed Roh."]],
            [TEXTS[1], TEXTS[1] + " " + TEXTS[1], [], []],
        ],
        "cues": [[0.0, 1.25, "One."], [1.25, 3.5, "Two, and more."], [61.0, 3661.789, "Later."]],
    }


@pytest.fixture(scope="module")
def old(cases: dict) -> dict:
    return old_answer(cases)


def scene(case: dict | None):
    if case is None:
        return None
    kind = {"points": "explain", "section": "section", "title": "plain"}[case["type"]]
    return Segment(id=case["id"], kind=kind, narration=case["narration"], holds=case.get("holds") or [])


def test_text(cases: dict, old: dict) -> None:
    assert [apply_pronunciations(text, cases["terms"]) for text in TEXTS] == old["pronounced"]
    assert [split_sentences(text) for text in TEXTS] == old["sentences"]
    assert [with_opening(text, cases["opening_line"]) for text in TEXTS] == old["opened"]


def test_holds(cases: dict, old: dict) -> None:
    assert roundtrip([list(holds.take_marks(text)) for text in MARKED]) == old["marks"]
    assert roundtrip([holds.kinds_of(scene(case)) for case in SCENES]) == old["kinds"]
    assert [holds.sentence_beat(a, b) for a, b in BEATS] == old["beats"]


def test_context_and_the_request_to_elevenlabs(cases: dict, old: dict) -> None:
    contexts = [list(context_of((scene(a), scene(b))).__dict__.values()) for a, b in cases["contexts"]]
    assert contexts == old["contexts"]
    style = voice_config.style("teacher")
    tts = ElevenLabsTTS("key", "voice", "", style.model_dump() if style else None)
    requests = [tts._request(text, Context(before, after)) for text, before, after in cases["requests"]]
    assert requests == old["requests"]


def test_audio_measurements(cases: dict, old: dict) -> None:
    leveler = voice_leveler.load_config("teacher")
    for case, theirs in zip(cases["audio"], old["audio"]):
        levels, voiced, seconds = case["levels"], case["voiced"], case["seconds"]
        timed = SpokenTimes(voiced["spoken"], voiced["character_starts"])
        found = holds.holds_of(scene(case["scene"]))
        curve = voice_leveler.gain_curve(case["leveler_levels"], leveler)
        ours = {
            "holds": found,
            "cuts": holds.cuts(case["scene"]["narration"], found, timed, seconds, cases["terms"], levels),
            "room_tone": holds.room_tone_span(levels),
            "quiet": holds.quiet_stretches(levels, timed, seconds),
            "curve": curve,
            "curve_filter": voice_leveler.curve_filter(curve, leveler),
            "floor": voice_leveler._floor(case["leveler_levels"], curve, case["gain_db"], leveler, case["fills"]),
            "stretch": opening_take.stretch(voiced["spoken"], voiced["character_starts"], 5),
        }
        assert roundtrip(ours) == theirs, case["scene"]["id"]


def test_teacher_style_pass(cases: dict, old: dict) -> None:
    requests = [list(narration_style.request_for(script, signature)) for script, signature in cases["style_scripts"]]
    assert roundtrip(requests) == old["style_requests"]
    assert [narration_style.problem(*case) for case in cases["style_problems"]] == old["style_problems"]


def test_subtitles(cases: dict, old: dict) -> None:
    assert srt.build_srt([tuple(cue) for cue in cases["cues"]]) == old["srt"]
