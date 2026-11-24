"""The Video Automation repo's side of the parity test: run with that repo's Python, reads the cases (JSON) on stdin,
answers on stdout. It only calls functions; it writes nothing.

    <old repo>/backend/.venv/Scripts/python.exe old_side.py <old repo>/backend < cases.json
"""

import json
import sys
from types import SimpleNamespace

sys.path.insert(0, sys.argv[1])

from app.pipeline.steps.voice import context_of  # noqa: E402
from app.providers.tts.base import Context, SpokenTimes  # noqa: E402
from app.providers.tts.elevenlabs import ElevenLabsTTS  # noqa: E402
from app.services import holds, narration_style, opening_take, voice_config, voice_leveler  # noqa: E402
from app.utils import srt  # noqa: E402
from app.utils.text import apply_pronunciations, split_sentences, with_opening  # noqa: E402


def scene(case: dict) -> SimpleNamespace:
    return SimpleNamespace(id=case["id"], type=case["type"], narration=case["narration"], holds=case.get("holds") or [], actions=[], spec=None)


def answer(cases: dict) -> dict:
    terms = cases["terms"]
    out: dict = {}
    out["pronounced"] = [apply_pronunciations(text, terms) for text in cases["texts"]]
    out["sentences"] = [split_sentences(text) for text in cases["texts"]]
    out["opened"] = [with_opening(text, cases["opening_line"]) for text in cases["texts"]]
    out["marks"] = [list(holds.take_marks(text)) for text in cases["marked"]]
    out["kinds"] = [holds.kinds_of(scene(case)) for case in cases["scenes"]]
    out["beats"] = [holds.sentence_beat(a, b) for a, b in cases["beats"]]
    out["contexts"] = [
        list(context_of((scene(a) if a else None, scene(b) if b else None)).__dict__.values()) for a, b in cases["contexts"]
    ]
    style = voice_config.style("teacher")
    tts = ElevenLabsTTS("key", "voice", "", style.model_dump() if style else None)
    out["requests"] = [tts._request(text, Context(before, after)) for text, before, after in cases["requests"]]
    leveler = voice_leveler.load_config("teacher")
    audio = []
    for case in cases["audio"]:
        levels, voiced, seconds = case["levels"], case["voiced"], case["seconds"]
        timed = SpokenTimes(voiced["spoken"], voiced["character_starts"]) if voiced else None
        found = holds.holds_of(scene(case["scene"]))
        curve = voice_leveler.gain_curve(case["leveler_levels"], leveler)
        audio.append({
            "holds": found,
            "cuts": holds.cuts(case["scene"]["narration"], found, timed, seconds, terms, levels),
            "room_tone": holds.room_tone_span(levels),
            "quiet": holds.quiet_stretches(levels, timed, seconds),
            "curve": curve,
            "curve_filter": voice_leveler.curve_filter(curve, leveler),
            "floor": voice_leveler._floor(case["leveler_levels"], curve, case["gain_db"], leveler, case["fills"]),
            "stretch": opening_take.stretch(voiced["spoken"], voiced["character_starts"], 5) if voiced else {},
        })
    out["audio"] = audio
    out["style_requests"] = [list(narration_style.request_for(script, signature)) for script, signature in cases["style_scripts"]]
    out["style_problems"] = [narration_style.problem(*case) for case in cases["style_problems"]]
    out["srt"] = srt.build_srt([tuple(cue) for cue in cases["cues"]])
    return out


if __name__ == "__main__":
    json.dump(answer(json.loads(sys.stdin.read())), sys.stdout)
