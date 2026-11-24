"""The narration in the teacher's own way of talking: a second pass over a finished script.

Blind tests against Ed's real recordings (2026-11-14, reports/PVC voice fidelity on multilingual v2.md):
polished lesson prose made his voice clone sound like AI with every voice setting, and his own way of
talking passed for him. The script writer has a hundred rules to keep and lands the voice only partway,
so this pass rewrites only the narration, scene by scene, in his way of talking (his transcribed words in
prompts/style_examples/teacher), and keeps every word the video is timed on.

A scene keeps the narration it had when its new one loses one of those words or a technical term, or
changes its length too much. The caller runs the checks on the result and puts back the narration of any
scene the new wording broke (generation_service._restyle).
"""

import json
import re
from dataclasses import dataclass, field

from voiceover.core.config import STYLE_EXAMPLES_DIR, STYLE_PROMPT_FILE
from voiceover.providers.script.writer import LLMResponse, ScriptWriter, only_json
from voiceover.services import prompt_service

# Diagram scenes keep their narration: each of its sentences is a step of the picture, drawn as it is said.
UNTOUCHED_TYPES = ("diagram",)
# How much shorter or longer a new narration may be (in words): the video is timed on its length.
MIN_LENGTH_RATIO = 0.75
MAX_LENGTH_RATIO = 1.3
# A technical term: camelCase, a call, an all-capitals word, or a name with a dot in it.
TERM = re.compile(r"\b[a-z]+[A-Z]\w*\b|\b\w+\(\)|\b[A-Z]{2,}\b|\b\w+\.\w+\b")
WORD = re.compile(r"[\w'’-]+")


@dataclass
class Restyled:
    """What the pass did: the script with new narration, the scenes it changed and the ones it kept, and the call."""

    script: dict
    changed: list[str] = field(default_factory=list)
    kept: dict[str, str] = field(default_factory=dict)  # scene id: why it kept its narration
    response: LLMResponse | None = None


def timed_words(scene: dict, signature: str = "") -> list[str]:
    """The phrases the scene's actions are timed on, in the order the narration says them: the teacher's
    opening line, then what each wait ends at (`until`, or `text` in the writer's answer format)."""
    words: list[str] = []
    if signature and str(scene.get("narration", "")).startswith(signature):
        words.append(signature)
    for action in scene.get("actions") or []:
        if isinstance(action, dict) and action.get("do") == "wait":
            anchor = action.get("until") or action.get("text")
            if isinstance(anchor, str) and anchor.strip():
                words.append(anchor)
    return words


def _as_said(narration: str, phrase: object) -> list[str]:
    """The phrase as the narration writes it ("swap in the box" for the label "Swap in the box"), if it says it."""
    at = narration.lower().find(phrase.lower()) if isinstance(phrase, str) and phrase.strip() else -1
    return [narration[at : at + len(phrase)]] if at >= 0 else []


def kept_words(scene: dict, signature: str = "", phrases: tuple[str, ...] = ()) -> list[str]:
    """Every phrase a scene's narration must keep as written: its timed words, where its holds go, a typing
    scene's goal (its label, or `heading` in the writer's answer format), said before the typing, and the
    whole video's `phrases` it says (the lesson plan's core sentence, said word for word each time)."""
    holds = [hold["before"] for hold in scene.get("holds") or [] if isinstance(hold, dict) and hold.get("before")]
    goal = scene.get("label") or (scene.get("heading") if scene.get("type") == "vscode" else "")
    narration = str(scene.get("narration", ""))
    said = [words for phrase in phrases for words in _as_said(narration, phrase)]
    return timed_words(scene, signature) + holds + _as_said(narration, goal) + said


def _in_order(narration: str, words: list[str]) -> bool:
    at = 0
    for wanted in words:
        found = narration.find(wanted, at)
        if found < 0:
            return False
        at = found + len(wanted)
    return True


def problem(old: str, new: str, keep: list[str], timed: list[str] | None = None) -> str | None:
    """Why a new narration cannot replace the old one, or None when it can. `keep`: every phrase it must
    keep as written; `timed`: those the actions wait for, which must also stay in their order."""
    missing = [word for word in keep if word and word not in new]
    if missing:
        return f'it lost "{missing[0]}", which the video depends on'
    # Said again elsewhere ("Let's click Save." at the end too): the wait may end at the wrong one.
    repeated = [word for word in keep if word and new.count(word) > old.count(word)]
    if repeated:
        return f'it says "{repeated[0]}" more often than the original'
    timed = timed or []
    if _in_order(old, timed) and not _in_order(new, timed):
        return "its timed words are in another order"
    lost = sorted(set(TERM.findall(old)) - set(TERM.findall(new)))
    if lost:
        return f"it lost the term{'s' if len(lost) > 1 else ''} {', '.join(lost)}"
    old_words, new_words = len(WORD.findall(old)), len(WORD.findall(new))
    if old_words and not MIN_LENGTH_RATIO <= new_words / old_words <= MAX_LENGTH_RATIO:
        return f"it has {new_words} words where the old one had {old_words}"
    if "[pause]" in old and old.count("[pause]") != new.count("[pause]"):
        return "it moved a [pause]"
    return None


def system_prompt() -> str:
    examples = prompt_service.style_examples(STYLE_EXAMPLES_DIR / "teacher")
    blocks = [f'<example file="{name}">\n{text}\n</example>' for name, text in examples]
    return "\n\n".join([STYLE_PROMPT_FILE.read_text(encoding="utf-8").rstrip(), "# The teacher's own words", *blocks]) + "\n"


def request_for(
    script: dict, signature: str = "", phrases: tuple[str, ...] = (), skip: set[str] | frozenset[str] = frozenset()
) -> tuple[str, dict[str, list[str]]]:
    """The request (the scenes to rewrite, with what each must keep) and the kept phrases of each scene.
    `phrases`: what the whole video says word for word (kept_words). `skip`: scenes to leave as they are."""
    items, keeps = [], {}
    for scene in script.get("scenes") or []:
        if not isinstance(scene, dict) or scene.get("type") in UNTOUCHED_TYPES or not str(scene.get("narration", "")).strip():
            continue
        if scene.get("id") in skip:
            continue
        keeps[scene["id"]] = kept_words(scene, signature, phrases)
        items.append({"id": scene["id"], "type": scene.get("type"), "narration": scene["narration"], "keep": keeps[scene["id"]]})
    return json.dumps({"scenes": items}, ensure_ascii=False, indent=1), keeps


def restyle(
    script: dict, writer: ScriptWriter, effort: str = "low", signature: str = "", phrases: tuple[str, ...] = (),
    skip: set[str] | frozenset[str] = frozenset(),
) -> Restyled:
    """The script with each scene's narration in the teacher's way of talking, where the new wording keeps
    everything the video depends on. One call to the writer. `skip`: scenes to leave as they are."""
    request, keeps = request_for(script, signature, phrases, skip)
    result = Restyled(script=json.loads(json.dumps(script)))
    if not keeps:
        return result
    result.response = writer.complete_json(system_prompt(), request, effort)
    try:
        answer = json.loads(only_json(result.response.text))
    except ValueError:
        result.kept = {scene_id: "the answer could not be read" for scene_id in keeps}
        return result
    new = {item.get("id"): item.get("narration") for item in answer.get("scenes") or [] if isinstance(item, dict)}
    for scene in result.script.get("scenes") or []:
        scene_id = scene.get("id") if isinstance(scene, dict) else None
        if scene_id not in keeps:
            continue
        narration = new.get(scene_id)
        if not isinstance(narration, str) or not narration.strip():
            result.kept[scene_id] = "no new narration came back"
            continue
        narration = " ".join(narration.split())
        why = problem(scene["narration"], narration, keeps[scene_id], timed_words(scene, signature))
        if why:
            result.kept[scene_id] = why
        elif narration != scene["narration"]:
            scene["narration"] = narration
            result.changed.append(scene_id)
    return result


def put_back(script: dict, original: dict, scene_ids: set[str]) -> None:
    """The original narration of these scenes, back in the script."""
    before = {scene.get("id"): scene.get("narration") for scene in original.get("scenes") or [] if isinstance(scene, dict)}
    for scene in script.get("scenes") or []:
        if isinstance(scene, dict) and scene.get("id") in scene_ids and scene.get("id") in before:
            scene["narration"] = before[scene["id"]]
