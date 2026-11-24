"""The script in the teacher's way of talking: the pass of services/narration_style.py on the request's script.

Used in mode "script" only when the request sends "rewrite": true: a finished script is otherwise spoken word for
word. Each segment's text goes to Claude with what it must keep (the opening line, "[pause]"); a segment whose new
wording loses a technical term, moves a "[pause]" or changes its length too much keeps its own words, as in the
Video Automation repo.
"""

from pathlib import Path

from voiceover.core import config
from voiceover.core.exceptions import AppError
from voiceover.providers.script.claude import ClaudeScriptWriter
from voiceover.services import narration_style
from voiceover.segments import SCENE_TYPES, SegmentInput
from writing import calls as llm_calls

# The effort the Video Automation repo gives this pass (generation_service._restyle).
STYLE_EFFORT = "medium"
STYLE_CALLS = ("style", "plan")


def writer() -> ClaudeScriptWriter:
    return ClaudeScriptWriter(config.ANTHROPIC_API_KEY, config.ANTHROPIC_MODEL, config.ANTHROPIC_WORKSPACE_ID)


def restyle(parts: list[SegmentInput], opening_line: str, calls: list[dict], llm_dir: Path, job_id: str, warn) -> list[SegmentInput]:
    """The segments with their text in the teacher's way of talking, where the new wording keeps what it must."""
    limit = llm_calls.over_cost_limit(calls, config.COST_LIMIT_USD, STYLE_CALLS)
    if limit:
        warn(f"The script was not put in the teacher's way of talking. {limit}")
        return parts
    script = {
        "scenes": [
            {"id": f"s{number:02d}", "type": SCENE_TYPES[part.kind], "narration": " ".join(part.text.split())}
            for number, part in enumerate(parts, start=1)
        ]
    }
    request, _ = narration_style.request_for(script, opening_line)
    llm_dir.mkdir(parents=True, exist_ok=True)
    (llm_dir / f"{len(calls) + 1:02d}-style-request.txt").write_text(request, encoding="utf-8")
    try:
        restyled = narration_style.restyle(script, writer(), STYLE_EFFORT, opening_line)
    except AppError as error:
        paid = getattr(error, "response", None)
        if paid is not None:
            llm_calls.record(calls, llm_dir, paid, "style", job_id)
        raise
    if restyled.response is not None:
        llm_calls.record(calls, llm_dir, restyled.response, "style", job_id)
    for scene_id, why in restyled.kept.items():
        warn(f"Segment {scene_id} keeps its own words: {why}.")
    new = {scene["id"]: scene["narration"] for scene in restyled.script["scenes"]}
    return [
        SegmentInput(text=new.get(f"s{number:02d}", part.text), kind=part.kind)
        for number, part in enumerate(parts, start=1)
    ]
