"""Holds: silence put into a scene's voice, so what was just said has time to land.

Spoken information is gone once it is said, and viewers rarely pause a video themselves (in one
study only 10 of 32 learners ever did), so the video pauses for them at the complex points.

Where the holds come from:
- The script writer writes "[pause]" in the narration: after a prediction question, after the
  analogy is mapped, after "what you just saw". The tool takes the marks out of the text and
  keeps them as the scene's `holds`, anchored at the words that follow.
- Some come by rule: after a diagram step that draws something new, at the end of a diagram,
  at the end of a section card.

The voice is made once, without holds (work/voice). The holds are cut into a copy of it
(work/audio) at the times the voice says the words are spoken, and every time after a cut moves
on by the length of the silence. So holds can change without a new voice.
"""

import hashlib
import json
import re
from collections.abc import Iterable

from voiceover.core.constants import (
    CLICK_SENTENCE_WORDS,
    HOLD_BEFORE_TAKEAWAY_SECONDS,
    HOLD_CLICK_SECONDS,
    HOLD_DIAGRAM_LOOK_SECONDS,
    HOLD_DIAGRAM_STEP_SECONDS,
    HOLD_ENTER_FROM_EDITOR_SECONDS,
    HOLD_LEAVE_TO_EDITOR_SECONDS,
    HOLD_LOOK_SECONDS,
    HOLD_SECTION_END_SECONDS,
    HOLD_SENTENCE_BASE,
    HOLD_SENTENCE_CARRIES_ON,
    HOLD_SENTENCE_MIN_WORDS,
    HOLD_SENTENCE_PER_WORD,
    HOLD_SENTENCE_QUESTION,
    HOLD_SENTENCE_RANGE,
    HOLD_SENTENCE_SCENES,
    HOLD_SENTENCE_SECONDS,
    HOLD_SENTENCE_VARIES,
    HOLD_THINK_SECONDS,
    PAUSE_MARK,
    SCENE_PADDING,
)
from voiceover.core.config import PAUSE_RHYTHM
from voiceover.core.paths import JobPaths
from voiceover.providers.tts.base import SpokenTimes
from voiceover.segments import Segment as Scene
from voiceover.utils.text import apply_pronunciations

MARK = re.compile(r"\s*" + re.escape(PAUSE_MARK) + r"\s*", re.IGNORECASE)
# How many words after a mark name its place.
ANCHOR_WORDS = 5
# Without the voice's levels, a cut goes this much before the first sound of the words after it.
CUT_LEAD_SECONDS = 0.03
# With them (reports/Human sounding ElevenLabs narration.md), it goes right after the words before
# it have died away: a breath before the next sentence then stays with that sentence, instead of
# being cut off from it by seconds of quiet. This much of the voice's own pause is kept before it.
TAIL_SECONDS = 0.12
# The words have ended where the voice stays this long below the level of speech.
QUIET_SECONDS = 0.1
# The voice's levels are measured in pieces this long.
LEVEL_FRAME_SECONDS = 0.02
# The room tone (the quiet the holds are filled with) is taken from a pause at least this long,
# without its edges, and at most this long: long enough that a long hold does not repeat a short piece.
ROOM_TONE_MIN_SECONDS = 0.15
ROOM_TONE_MAX_SECONDS = 0.5
ROOM_TONE_EDGE_SECONDS = 0.04
# A piece whose level changes more than this (frame to frame, in dB) is not even enough to loop: the
# scene borrows the room tone of the scene before it instead.
ROOM_TONE_MAX_SPREAD_DB = 12.0
# A voice whose quiet and loud parts are closer than this has no pauses to measure.
SPEECH_SPREAD_DB = 15.0
# Quieter than this is digital silence, not a room: never used as room tone.
DIGITAL_SILENCE_DB = -110.0


# --- the writer's marks ---


def take_marks(narration: str) -> tuple[str, list[dict]]:
    """The narration without its "[pause]" marks, and a hold for each mark, anchored at the words after it."""
    pieces = MARK.split(narration)
    if len(pieces) == 1:
        return narration, []
    text, holds = "", []
    for index, piece in enumerate(pieces):
        piece = piece.strip()
        if index:
            # As long as its kind says: a think pause after a question, a look pause anywhere else.
            holds.append({"before": " ".join(piece.split()[:ANCHOR_WORDS])})
        if piece:
            text = f"{text} {piece}" if text else piece
    return text, holds


def put_marks(narration: str, holds: Iterable) -> str:
    """The narration with a "[pause]" mark where each of its holds is: how the writer wrote it."""
    places = sorted(index for index, _ in resolve(narration, holds))
    for index in reversed(places):
        before, after = narration[:index].rstrip(), narration[index:].lstrip()
        narration = f"{before} {PAUSE_MARK} {after}".strip() if after else f"{before} {PAUSE_MARK}"
    return narration


def take_marks_in_script(script: dict) -> None:
    """Turn the "[pause]" marks of every scene of a script (as the writer wrote it) into holds, in place."""
    for scene in script.get("scenes") or []:
        if not isinstance(scene, dict) or not isinstance(scene.get("narration"), str):
            continue
        text, holds = take_marks(scene["narration"])
        if holds:
            scene["narration"] = text
            scene["holds"] = [*(scene.get("holds") or []), *holds]


# --- where the holds are ---


def _field(hold, name: str):
    return hold.get(name) if isinstance(hold, dict) else getattr(hold, name)


SENTENCE_START = re.compile(r"(?<=[.!?])\s+(?=\S)")


# A sentence that asks the viewer to stop the video and do something: a think pause follows it.
PAUSE_THE_VIDEO = re.compile(r"\bpause the video\b", re.IGNORECASE)


def _writer_hold(narration: str, index: int, seconds: float | None) -> tuple[float, str]:
    """A writer's hold: a think pause after a question or an invitation to pause the video and try
    something, a look pause anywhere else. A hold that was given its own seconds keeps them."""
    before = narration[:index].rstrip()
    asks = before.endswith("?") or bool(PAUSE_THE_VIDEO.search(before[last_sentence_start(before) :]))
    kind = "think" if asks else "look"
    if seconds is None:
        seconds = HOLD_THINK_SECONDS if kind == "think" else HOLD_LOOK_SECONDS
    return float(seconds), kind


def _resolved(narration: str, holds: Iterable) -> list[tuple[int, float, str]]:
    """(place in the narration, seconds, kind) of each hold the writer marked that can be found, in order."""
    found, at = [], 0
    for hold in holds:
        before = _field(hold, "before") or ""
        index = narration.find(before, at) if before else len(narration)
        if index < 0:
            continue
        if before:
            at = index
        found.append((index, *_writer_hold(narration, index, _field(hold, "seconds"))))
    return found


def resolve(narration: str, holds: Iterable) -> list[tuple[int, float]]:
    """(place in the narration, seconds) of each hold that can be found, in order. Empty words: the end."""
    return [(index, seconds) for index, seconds, _ in _resolved(narration, holds)]


def last_sentence_start(narration: str) -> int:
    """Where the narration's last sentence starts (0 when it has one sentence)."""
    starts = [match.end() for match in SENTENCE_START.finditer(narration.rstrip())]
    return starts[-1] if starts else 0


def _at_scene_end(narration: str, index: int, seconds: float, kind: str) -> tuple[int, float, str]:
    """A writer's hold at the very end of a scene, where the gap between scenes is part of it.

    A think pause stays (the question is the last thing said). A look pause goes before the
    scene's last sentence instead, so the scene ends on its takeaway and never on a stop.
    """
    if index < len(narration):
        return index, seconds, kind
    if kind == "think":
        return index, max(seconds - SCENE_PADDING, SCENE_PADDING), kind
    last = last_sentence_start(narration)
    if last > 0:
        return last, HOLD_BEFORE_TAKEAWAY_SECONDS, kind
    return index, max(HOLD_BEFORE_TAKEAWAY_SECONDS - SCENE_PADDING, SCENE_PADDING), kind


def unplaced(narration: str, holds: Iterable) -> list[str]:
    """The words of the holds that are not in the narration (in order), so they cannot be placed."""
    missing, at = [], 0
    for hold in holds:
        before = _field(hold, "before") or ""
        if not before:
            continue
        index = narration.find(before, at)
        if index < 0:
            missing.append(before)
        else:
            at = index
    return missing


ENDS_SENTENCE = (".", "!", "?", "…")


def _click_holds(scene: Scene) -> list[tuple[int, float, str]]:
    """A look beat after each short sentence a click is timed on ("Let's click."): the pointer travels to the
    button and clicks during it, so what the next sentence says ("Three!") is on the page as it is said."""
    narration, found, at, timed = scene.narration, [], 0, None
    for action in scene.actions:
        if action.do == "wait" and getattr(action, "until", None):
            index = narration.find(action.until, at)
            if index >= 0:
                timed, at = index, index
        elif action.do == "click" and timed is not None:
            starts_sentence = timed == 0 or narration[:timed].rstrip().endswith(ENDS_SENTENCE)
            ends = [narration.find(mark, timed) for mark in ENDS_SENTENCE]
            end = min((index for index in ends if index >= 0), default=-1)
            if starts_sentence and end >= 0 and len(narration[timed : end + 1].split()) <= CLICK_SENTENCE_WORDS:
                following = end + 1 + (len(narration[end + 1 :]) - len(narration[end + 1 :].lstrip()))
                if following < len(narration):
                    found.append((following, HOLD_CLICK_SECONDS, "click"))
            timed = None
    return found


# A sentence that carries on from the one before it: the pause between them is short.
CARRIES_ON = re.compile(r"^(so|and|but|then|now|that|which|because|first|next)\b", re.IGNORECASE)


def sentence_beat(sentence: str, following: str) -> float:
    """How long a person pauses after a sentence (constants.HOLD_SENTENCE_*): longer after a long one that carries an
    idea, or a question; shorter when the next one carries on from it; never twice exactly the same, but always the
    same for the same sentence, so a scene made again pauses where it did. PAUSE_RHYTHM=even: HOLD_SENTENCE_SECONDS."""
    if PAUSE_RHYTHM == "even":
        return HOLD_SENTENCE_SECONDS
    seconds = HOLD_SENTENCE_BASE + HOLD_SENTENCE_PER_WORD * len(sentence.split())
    if sentence.rstrip().endswith("?"):
        seconds += HOLD_SENTENCE_QUESTION
    if CARRIES_ON.match(following.strip()):
        seconds *= HOLD_SENTENCE_CARRIES_ON
    share = int(hashlib.sha1(sentence.strip().encode("utf-8")).hexdigest()[:4], 16) / 0xFFFF  # 0..1
    seconds *= 1 - HOLD_SENTENCE_VARIES + 2 * HOLD_SENTENCE_VARIES * share
    low, high = HOLD_SENTENCE_RANGE
    return round(min(max(seconds, low), high), 2)


def _sentence_holds(scene: Scene) -> list[tuple[int, float, str]]:
    """A pause after each sentence of an explanation that carries an idea (sentence_beat), so it is taken in before the
    next one; not after the scene's last sentence, where the scene ends."""
    if scene.type not in HOLD_SENTENCE_SCENES:
        return []
    narration, found, start = scene.narration, [], 0
    matches = list(SENTENCE_START.finditer(narration))
    for index, match in enumerate(matches):
        sentence = narration[start : match.start()]
        following = narration[match.end() : matches[index + 1].start() if index + 1 < len(matches) else len(narration)]
        if len(sentence.split()) >= HOLD_SENTENCE_MIN_WORDS:
            found.append((match.end(), sentence_beat(sentence, following), "sentence"))
        start = match.end()
    return found


def _by_rule(scene: Scene, previous: Scene | None = None, following: Scene | None = None) -> list[tuple[int, float, str]]:
    """The holds a scene gets by its kind and its neighbors, as (place, seconds, kind): after each sentence of an
    explanation, after diagram steps that draw, before a diagram's last sentence, after a section card, and around a
    connect scene that comes from or goes to the editor (its transition plays then)."""
    return [*_sentence_holds(scene), *_kind_holds(scene, previous, following)]


def _kind_holds(scene: Scene, previous: Scene | None = None, following: Scene | None = None) -> list[tuple[int, float, str]]:
    if scene.type == "section":
        return [(len(scene.narration), HOLD_SECTION_END_SECONDS, "section")]
    if scene.type == "browser":
        return _click_holds(scene)
    if scene.type == "connect":
        found = _click_holds(scene)
        if previous is not None and previous.type == "vscode":
            found.append((0, HOLD_ENTER_FROM_EDITOR_SECONDS, "transition"))
        if following is not None and following.type == "vscode":
            found.append((len(scene.narration), HOLD_LEAVE_TO_EDITOR_SECONDS, "transition"))
        return found
    if scene.type != "diagram":
        return []
    parts = scene.spoken_parts()
    found, place, said = [], 0, False
    for index, (part, step) in enumerate(zip(parts, scene.spec.steps)):
        if part:
            place += (1 if said else 0) + len(part)
            said = True
        draws = any(isinstance(verb, dict) and "draw" in verb for verb in step.do)
        later = any(parts[index + 1 :])
        # Never in the middle of a sentence that goes on in the next step.
        if draws and part and later and part.rstrip().endswith(ENDS_SENTENCE):
            found.append((place + 1, HOLD_DIAGRAM_STEP_SECONDS, "step"))
    # The finished picture gets a look beat before the last thing said about it (its takeaway), with the
    # element it ends on lit: the scene then ends on the voice, not on a frozen picture.
    spoken = [part for part in parts if part]
    if len(spoken) > 1 and spoken[-2].rstrip().endswith(ENDS_SENTENCE):
        found.append((len(scene.narration) - len(spoken[-1]), HOLD_DIAGRAM_LOOK_SECONDS, "diagram"))
    else:
        found.append((len(scene.narration), HOLD_DIAGRAM_LOOK_SECONDS - SCENE_PADDING, "diagram"))
    return found


def kinds_of(scene: Scene, previous: Scene | None = None, following: Scene | None = None) -> list[tuple[int, float, str]]:
    """Every hold of the scene as (place in its narration, seconds, kind), sorted. Two at one place: the
    longer one. Kinds: think and look (the writer's), sentence, step, diagram, section, transition and click (by rule)."""
    narration = scene.narration
    writer = [_at_scene_end(narration, *hold) for hold in _resolved(narration, scene.holds)]
    merged: dict[int, tuple[float, str]] = {}
    for index, seconds, kind in [*writer, *_by_rule(scene, previous, following)]:
        index = min(max(index, 0), len(narration))
        if index not in merged or seconds > merged[index][0]:
            merged[index] = (seconds, kind)
    return [(index, seconds, kind) for index, (seconds, kind) in sorted(merged.items())]


def holds_of(scene: Scene, previous: Scene | None = None, following: Scene | None = None) -> list[tuple[int, float]]:
    """Every hold of the scene as (place in its narration, seconds), sorted (kinds_of without the kinds).

    `previous` and `following` are the scenes around it: some holds depend on where a scene comes from.
    """
    return [(index, seconds) for index, seconds, _ in kinds_of(scene, previous, following)]


def neighbors(scenes: list, index: int) -> tuple:
    """The scenes before and after the one at `index`, or None at either end."""
    return (scenes[index - 1] if index > 0 else None, scenes[index + 1] if index + 1 < len(scenes) else None)


def total_seconds(scene: Scene, previous: Scene | None = None, following: Scene | None = None) -> float:
    return sum(seconds for _, seconds in holds_of(scene, previous, following))


# --- in the audio ---


def speech_level(levels: list[float]) -> float:
    """The level (dBFS) above which a piece of the voice is speech: between its quiet and its loud parts."""
    ordered = sorted(levels)
    quiet, loud = ordered[len(ordered) // 10], ordered[(len(ordered) * 9) // 10]
    return max(quiet + 12.0, loud - 30.0)


def _quiet_runs(levels: list[float]) -> list[tuple[int, int]]:
    """(first frame, frames) of each run of the voice below the level of speech. None found when the
    voice has no clear quiet parts (its quiet and loud parts are less than SPEECH_SPREAD_DB apart)."""
    ordered = sorted(levels)
    if not ordered or ordered[(len(ordered) * 9) // 10] - ordered[len(ordered) // 10] < SPEECH_SPREAD_DB:
        return []
    threshold, runs, first = speech_level(levels), [], None
    for index, level in enumerate([*levels, float("inf")]):
        if level < threshold and first is None:
            first = index
        elif level >= threshold and first is not None:
            runs.append((first, index - first))
            first = None
    return runs


def speech_end(levels: list[float], after: float, before: float) -> float | None:
    """When the words that are being said at `after` die away: the first quiet run of QUIET_SECONDS
    that starts after `after` and before `before`. None when there is none."""
    need = round(QUIET_SECONDS / LEVEL_FRAME_SECONDS)
    for first, frames in _quiet_runs(levels):
        at = first * LEVEL_FRAME_SECONDS
        if at > before:
            break
        if (first + frames) * LEVEL_FRAME_SECONDS > after and frames >= need:
            return max(at, after)
    return None


def room_tone_span(levels: list[float]) -> tuple[float, float] | None:
    """(start, seconds) of the voice's own quiet to fill its holds with: the evenest stretch of its
    pauses between words. Not the quiet before the first word or after the last: the voice pads its
    ends with digital silence, which is what the fill is there to replace.

    A pause often still holds the tail of a word or a breath. Looped through a hold of 3 seconds, a
    louder bit in the piece comes back every second as a puff ("p... p... p..."). So of every
    window that fits in a pause (without its edges), the one whose level changes least is taken,
    and of those the quietest."""
    edge = round(ROOM_TONE_EDGE_SECONDS / LEVEL_FRAME_SECONDS)
    longest = round(ROOM_TONE_MAX_SECONDS / LEVEL_FRAME_SECONDS)
    shortest = round(ROOM_TONE_MIN_SECONDS / LEVEL_FRAME_SECONDS)
    best: tuple[float, float, int, int] | None = None  # (spread, mean, first frame, frames)
    for first, frames in _quiet_runs(levels) if levels else []:
        if first == 0 or first + frames >= len(levels) or min(levels[first : first + frames]) <= DIGITAL_SILENCE_DB:
            continue
        inner_first, inner_frames = first + edge, frames - 2 * edge
        size = min(longest, inner_frames)
        if size < shortest:
            continue
        for start in range(inner_first, inner_first + inner_frames - size + 1):
            window = levels[start : start + size]
            # A longer window is worth a little spread: a short loop repeats more often.
            score = (max(window) - min(window) - (size - shortest) * 0.05, sum(window) / size, start, size)
            if best is None or score < best:
                best = score
    if best is None or best[0] + (best[3] - shortest) * 0.05 > ROOM_TONE_MAX_SPREAD_DB:
        return None
    _, _, start, size = best
    return round(start * LEVEL_FRAME_SECONDS, 3), round(size * LEVEL_FRAME_SECONDS, 3)


def silent_stretches(levels: list[float], seconds: float) -> list[tuple[float, float]]:
    """(start, end) of every stretch of digital silence in the voice: at its ends, where the voice
    pads a take, and in some of its pauses. Replaced by room tone of the same length, so nothing
    moves and the background never drops away. A voice that is all silence has none."""
    if all(level <= DIGITAL_SILENCE_DB for level in levels):
        return []
    found, first = [], None
    for index, level in enumerate([*levels, float("inf")]):
        if level <= DIGITAL_SILENCE_DB and first is None:
            first = index
        elif level > DIGITAL_SILENCE_DB and first is not None:
            end = seconds if index >= len(levels) else index * LEVEL_FRAME_SECONDS
            found.append((round(first * LEVEL_FRAME_SECONDS, 3), round(min(end, seconds), 3)))
            first = None
    return found


def after_last_word(levels: list[float], voiced: SpokenTimes | None, seconds: float) -> tuple[float, float] | None:
    """(start, end) of the voice after its last word has died away (TAIL_SECONDS of that is kept), or None.

    A take often goes on after its text: a breath for words that never come, or the start of a
    sound that the end of the take cuts off. At a scene change that sounds like the narrator was
    cut off, so it is filled with room tone instead. None without the voice's times.
    """
    if voiced is None or not levels or len(voiced.starts) != len(voiced.text):
        return None
    last = next((index for index in range(len(voiced.text) - 1, -1, -1) if voiced.text[index].isalnum()), None)
    if last is None:
        return None
    ended = speech_end(levels, float(voiced.starts[last]), seconds)
    if ended is None:
        return None
    start = round(ended + TAIL_SECONDS, 3)
    return (start, round(seconds, 3)) if seconds - start >= LEVEL_FRAME_SECONDS else None


def filled_spans(record: dict) -> list[tuple[float, float]]:
    """(start, end), in the scene's audio (work/audio), of the room tone the voice step put in, from what its audio
    was made with (paths.held): each pause cut in at a place moves what comes after it, and each quiet stretch of
    the voice is replaced in place (ffmpeg.insert_silence)."""
    events = [(float(at), float(seconds), True) for at, seconds in record.get("cuts") or []]
    events += [(float(start), float(end) - float(start), False) for start, end in record.get("quiet_ends") or [] if end > start]
    spans, shift = [], 0.0
    for at, seconds, inserted in sorted(events):
        spans.append((at + shift, at + shift + seconds))
        if inserted:
            shift += seconds
    return spans


def quiet_stretches(levels: list[float], voiced: SpokenTimes | None, seconds: float) -> list[tuple[float, float]]:
    """(start, end) of every stretch of the voice to replace with room tone, sorted and not overlapping:
    its digital silence (silent_stretches) and what comes after its last word (after_last_word)."""
    found = sorted([*silent_stretches(levels, seconds), *filter(None, [after_last_word(levels, voiced, seconds)])])
    merged: list[tuple[float, float]] = []
    for start, end in found:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _segment_times(
    segments: list[str], voiced: SpokenTimes | None, seconds: float, terms: dict[str, str]
) -> tuple[list[float | None], list[float | None]]:
    """When each segment's first and last character are spoken (None for an empty segment).
    From the voice's character times; without them, estimated from the lengths of the texts."""
    if voiced is not None and len(voiced.starts) == len(voiced.text):
        firsts, lasts, at = [], [], 0
        for segment in segments:
            spoken = apply_pronunciations(segment, terms) if segment else ""
            while at < len(voiced.text) and voiced.text[at] == " ":
                at += 1
            if spoken and not voiced.text.startswith(spoken, at):
                break
            firsts.append(float(voiced.starts[min(at, len(voiced.starts) - 1)]) if spoken else None)
            lasts.append(float(voiced.starts[at + len(spoken) - 1]) if spoken else None)
            at += len(spoken)
        else:
            if not voiced.text[at:].strip():
                return firsts, lasts
    total = sum(len(segment) for segment in segments) or 1
    firsts, lasts, before = [], [], 0
    for segment in segments:
        firsts.append(seconds * before / total if segment else None)
        before += len(segment)
        lasts.append(seconds * before / total if segment else None)
    return firsts, lasts


def cuts(
    narration: str,
    holds: list[tuple[int, float]],
    voiced: SpokenTimes | None,
    seconds: float,
    terms: dict[str, str],
    levels: list[float] | None = None,
) -> list[tuple[float, float]]:
    """(second in the voice, seconds of pause put in) for each hold.

    Without the voice's `levels` (LEVEL_FRAME_SECONDS each), a hold is its full length, right
    before the words after it. With them, it goes right after the words before it have died
    away, and its seconds are the whole pause the viewer hears: the voice's own pause counts,
    and only what is missing is put in.
    """
    if not holds:
        return []
    bounds = [0, *(index for index, _ in holds), len(narration)]
    segments = [narration[start:end].strip() for start, end in zip(bounds, bounds[1:])]
    firsts, lasts = _segment_times(segments, voiced, seconds, terms)
    result = []
    for number, (_, wanted) in enumerate(holds, start=1):
        # The words after the hold (None: nothing is said after it) and the last ones said before it.
        following = firsts[number] if number < len(firsts) else None
        said = [last for last in lasts[:number] if last is not None]
        upto = seconds if following is None else following
        at, heard = (seconds if following is None else max(0.0, following - CUT_LEAD_SECONDS)), 0.0
        if levels and not said:
            at, heard = 0.0, upto  # before the first words: the quiet the voice starts with counts
        elif levels:
            ended = speech_end(levels, said[-1], upto)
            if ended is not None:
                at = min(ended + TAIL_SECONDS, max(0.0, upto - CUT_LEAD_SECONDS)) if following is not None else min(ended + TAIL_SECONDS, seconds)
                heard = max(0.0, upto - ended)
        missing = round(wanted - heard, 3)
        if missing > 0:
            result.append((round(min(at, seconds), 3), missing))
    return result


# A hold's cue on screen starts this long after the start of the last character before it, as the
# words die away.
CUE_AFTER_WORDS_SECONDS = 0.15


def _question_before(narration: str, index: int) -> str:
    """The sentence that ends where a think pause is: the question the viewer thinks about. After
    "Pause the video and make your guess.", the question is the sentence before that one."""
    before = narration[:index].rstrip()
    last = before[last_sentence_start(before) :].strip()
    if PAUSE_THE_VIDEO.search(last) and not last.endswith("?"):
        earlier = before[: last_sentence_start(before)].rstrip()
        question = earlier[last_sentence_start(earlier) :].strip()
        if question.endswith("?"):
            return question
    return last


def hold_spans(paths: JobPaths, scene: Scene, previous: Scene | None, following: Scene | None, terms: dict[str, str]) -> list[dict]:
    """When each hold is in the scene's audio (holds included), from the last words before it until the
    next ones, and its kind: {"start", "end", "kind"}, with the "question" of a think pause. The stage
    gives each kind something to show, so no hold is a frozen picture. Empty without the voice's times."""
    try:
        record = json.loads(paths.held(scene.id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    times, found = audio_times(paths, scene), kinds_of(scene, previous, following)
    if times is None or not found:
        return []
    seconds = float(record.get("seconds") or 0.0)
    narration = scene.narration
    bounds = [0, *(index for index, _, _ in found), len(narration)]
    segments = [narration[start:end].strip() for start, end in zip(bounds, bounds[1:])]
    firsts, lasts = _segment_times(segments, times, seconds, terms)
    spans = []
    for number, (index, _, kind) in enumerate(found, start=1):
        said = [last for last in lasts[:number] if last is not None]
        after = next((first for first in firsts[number:] if first is not None), None)
        start = min(said[-1] + CUE_AFTER_WORDS_SECONDS, seconds) if said else 0.0
        end = after if after is not None else seconds + SCENE_PADDING  # to the end of the clip
        if end - start <= 0:
            continue
        span = {"start": round(start, 3), "end": round(end, 3), "kind": kind}
        if kind == "think":
            span["question"] = _question_before(narration, index)
        spans.append(span)
    return spans


def audio_times(paths: JobPaths, scene: Scene) -> SpokenTimes | None:
    """When each character of the scene's audio, holds included, is spoken. None when it is not known."""
    try:
        record = json.loads(paths.held(scene.id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if record.get("narration") != scene.narration or "character_starts" not in record:
        return None
    return SpokenTimes(record["spoken"], record["character_starts"])


def shift(voiced: SpokenTimes | None, cuts: list[tuple[float, float]]) -> SpokenTimes | None:
    """The character times after the silences went in: everything after a cut comes later by its length."""
    if voiced is None or not cuts:
        return voiced
    return SpokenTimes(
        voiced.text, [round(start + sum(silence for at, silence in cuts if at <= start), 3) for start in voiced.starts]
    )
