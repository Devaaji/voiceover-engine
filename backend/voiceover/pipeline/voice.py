"""Step 1: one audio file per segment, with its holds, and when each of its characters is spoken.

voiceover-engine: from backend/app/pipeline/steps/voice.py of the Video Automation repo (2026-11-23). The functions
that make the voice and put the holds in are the same; what only a video needs is not copied:

- the voice that waits for code being typed (services/timeline/fit.py): for a scene that types nothing, fit gave
  back the holds as they were, and a segment types nothing;
- the times of diagram steps and of the waits of clicks and typing;
- the move of audio made before holds existed (_keep_old_audio).

The voice is made once per narration (work/voice, with the time of every character). The segment's audio
(work/audio) is that voice with the holds put in (services/holds.py). When only the holds change, the audio is made
again from the kept voice, without a new voice.
"""

import json
import logging
import re
import shutil
from pathlib import Path

from voiceover.core.config import APPROVED_OPENING, APPROVED_OPENING_DIR, OPENING_PAUSE_SECONDS
from voiceover.pipeline.context import StepContext
from voiceover.providers.tts.base import Context, SpokenTimes
from voiceover.providers.tts.registry import get_tts_provider
from voiceover.segments import Segment as Scene
from voiceover.services import approved_opening, holds, opening_take
from voiceover.utils import ffmpeg

log = logging.getLogger(__name__)

# What the voice is told of the segments around a segment: two sentences on each side, at most this long.
CONTEXT_SENTENCES = 2
CONTEXT_CHARS = 300
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
# How the room tone fills are made (ffmpeg.insert_silence). A new value makes every segment's audio
# again from its kept voice, without a new voice.
FILLS = "merged, crossfaded with the voice, room tone from smooth noise at the heard level, kept in float"


def _read(file: Path) -> dict | None:
    try:
        return json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(file: Path, data: dict) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _sentences(text: str) -> list[str]:
    return [sentence for sentence in SENTENCE_END.split(text.strip()) if sentence] if text else []


def context_of(around: tuple) -> Context:
    """The last sentences of the segment before and the first of the segment after: said around this one."""
    previous, following = around
    before = " ".join(_sentences(previous.narration)[-CONTEXT_SENTENCES:]) if previous is not None else ""
    after = " ".join(_sentences(following.narration)[:CONTEXT_SENTENCES]) if following is not None else ""
    if len(before) > CONTEXT_CHARS:
        before = before[-CONTEXT_CHARS:].split(" ", 1)[-1]
    if len(after) > CONTEXT_CHARS:
        after = after[:CONTEXT_CHARS].rsplit(" ", 1)[0]
    return Context(before, after)


def _said(text: str) -> str:
    return " ".join(text.split())


def _says_other_words(ctx: StepContext, scene: Scene) -> bool:
    """Whether the kept voice was made for another narration than the segment has now."""
    saved = _read(ctx.paths.voice_times(scene.id)) or {}
    if not isinstance(saved.get("narration"), str) or _said(saved["narration"]) == _said(scene.narration):
        return False
    log.warning("[%s] %s: the kept voice says other words than the script; it is made again", ctx.job_id, scene.id)
    return True


def _voice(
    ctx: StepContext, scene: Scene, provider, terms: dict[str, str], around: tuple = (None, None)
) -> tuple[Path, SpokenTimes | None, bool]:
    """The segment's voice without holds, and when each character is spoken. Made when missing or forced.

    The voice is told what is said around the segment (context_of), so it speaks the segment as a
    part of one talk. That context is not part of what decides whether a voice is made again.
    """
    voice = ctx.paths.voice(scene.id)
    # Audio that was deleted by hand (work/audio) asks for a new voice, as it always did.
    deleted = ctx.paths.held(scene.id).exists() and ctx.paths.audio(scene.id) is None
    made = voice is None or ctx.force or deleted or _says_other_words(ctx, scene)
    if made:
        for stale in (voice, ctx.paths.audio(scene.id), ctx.paths.merged(scene.id), ctx.paths.held(scene.id)):
            if stale is not None:
                stale.unlink(missing_ok=True)
        ctx.paths.voice_dir.mkdir(parents=True, exist_ok=True)
        voice = ctx.paths.voice_dir / f"{scene.id}.{provider.extension}"
        # Spoken as one text, so the voice stays natural. (A segment has no waits to cut it at.)
        parts = [scene.narration]
        try:
            voiced = _with_approved_opening(ctx, provider, parts, context_of(around), voice)
            if voiced is _NO_OPENING:
                voiced = provider.synthesize_parts(parts, voice, context=context_of(around))
                voiced = _opening_take(ctx, scene, provider, parts, context_of(around), voice, voiced)
        except Exception:
            voice.unlink(missing_ok=True)
            raise
        times = {"narration": scene.narration}
        if voiced is not None:
            times.update(spoken=voiced.text, character_starts=[round(start, 3) for start in voiced.starts])
        _write(ctx.paths.voice_times(scene.id), times)
    saved = _read(ctx.paths.voice_times(scene.id)) or {}
    voiced = None
    if saved.get("narration") == scene.narration and "character_starts" in saved:
        voiced = SpokenTimes(saved["spoken"], saved["character_starts"])
    return voice, voiced, made


_NO_OPENING = object()


def _signature(ctx: StepContext) -> str:
    return ctx.opening_line


def _with_approved_opening(ctx: StepContext, provider, parts: list[str], context: Context, voice: Path):
    """The segment that opens with the opening line, as the approved take of that line (services/approved_opening.py),
    a pause, and the rest of the segment spoken after it; its times. _NO_OPENING when there is no approved take for
    this voice and line, or the segment does not open with it."""
    if not APPROVED_OPENING or ctx.voice.tts_provider != "elevenlabs":
        return _NO_OPENING
    signature = _signature(ctx) or ""
    opening = approved_opening.load(APPROVED_OPENING_DIR, ctx.voice.elevenlabs_voice_id, signature)
    rest = approved_opening.rest_of(parts, signature) if opening is not None else None
    if rest is None:
        return _NO_OPENING
    spoken_rest = voice.with_name(f"{voice.stem}.rest{voice.suffix}")
    try:
        # The rest goes on from the opening line, as if the voice had just said it.
        voiced = provider.synthesize_parts(rest, spoken_rest, context=Context(signature, context.after))
        voiced = approved_opening.splice(opening, spoken_rest, voiced, voice, OPENING_PAUSE_SECONDS)
    finally:
        spoken_rest.unlink(missing_ok=True)
    log.info("[%s] the approved opening line opens the segment", ctx.job_id)
    return voiced


def _opening_take(
    ctx: StepContext, scene: Scene, provider, parts: list[str], context: Context, voice: Path, voiced: SpokenTimes | None
) -> SpokenTimes | None:
    """The segment that opens with the opening line is spoken again while a word of that line is drawn out
    (services/opening_take.py), at most TAKES times in all. The take whose slowest word is the least
    drawn out is kept in `voice`; its times are returned."""
    words = opening_take.opening_words(scene.narration, _signature(ctx))
    if not words or voiced is None:
        return voiced
    best = opening_take.worst(voiced.text, voiced.starts, words)
    takes = 1
    while best > opening_take.STRETCH_LIMIT and takes < opening_take.TAKES:
        drawn = ", ".join(f'"{word}" {times}x' for word, times in opening_take.drawn_out(voiced.text, voiced.starts, words).items())
        log.info("[%s] %s: the opening line draws out %s; speaking it again", ctx.job_id, scene.id, drawn)
        takes += 1
        take = ctx.paths.root / "work" / "takes" / f"{scene.id}.take{takes}.{provider.extension}"
        take.parent.mkdir(parents=True, exist_ok=True)
        again = provider.synthesize_parts(parts, take, context=context)
        slowest = opening_take.worst(again.text, again.starts, words) if again is not None else best
        if again is not None and slowest < best:
            shutil.move(str(take), str(voice))
            voiced, best = again, slowest
        else:
            take.unlink(missing_ok=True)
    if best > opening_take.STRETCH_LIMIT:
        drawn = ", ".join(f'"{word}" {times}x' for word, times in opening_take.drawn_out(voiced.text, voiced.starts, words).items())
        ctx.warn(
            f"{scene.id}: the opening line still draws out {drawn} its normal length after {takes} takes. "
            "Listen to the start of the voiceover, and make it again if it sounds wrong."
        )
    return voiced


def _held(
    ctx: StepContext,
    scene: Scene,
    voice: Path,
    voiced: SpokenTimes | None,
    terms: dict[str, str],
    around: tuple,
    borrowed: Path | None = None,
) -> tuple[Path, bool]:
    """The segment's audio: the voice with its holds put in. Made again when the voice or the holds changed.

    The holds are filled with the voice's own quiet (its room tone), kept in work/tone, which
    also fills the pause at the end of the segment: a pause of digital silence in a voice
    that has a background sounds like the recording stopping. A short segment without a pause to
    take it from (a section) uses `borrowed`, the room tone of the segment before it.
    """
    seconds = ffmpeg.probe_duration(voice)
    try:
        levels = ffmpeg.rms_levels(voice, holds.LEVEL_FRAME_SECONDS)
    except RuntimeError:
        levels = []  # not measurable: the holds go in as before, with silence
    # The old pipeline's fit (the voice waiting for code being typed) gave back the holds as they were for a scene
    # that types nothing, sorted.
    wanted = sorted(holds.holds_of(scene, *around))
    cuts = holds.cuts(scene.narration, wanted, voiced, seconds, terms, levels)
    span = holds.room_tone_span(levels)
    borrowed = borrowed if span is None and borrowed is not None and borrowed.exists() else None
    has_tone = span is not None or borrowed is not None
    # The digital silence in the voice (its ends, some of its pauses) and whatever the take holds after
    # its last word (a breath, a cut-off sound) become room tone, as long as they were.
    quiet = holds.quiet_stretches(levels, voiced, seconds) if has_tone else []
    stat = voice.stat()
    made_from = {
        "voice": [voice.name, stat.st_size, stat.st_mtime_ns],
        "fills": FILLS,
        "cuts": [list(cut) for cut in cuts],
        "room_tone": list(span) if span else (f"from {borrowed.stem}" if borrowed else None),
        "quiet_ends": [list(stretch) for stretch in quiet],
    }
    audio = ctx.paths.audio(scene.id)
    tone = ctx.paths.room_tone(scene.id)
    record = _read(ctx.paths.held(scene.id)) or {}
    if audio is not None and {key: record.get(key) for key in made_from} == made_from and (not has_tone or tone.exists()):
        return audio, False
    for old in ctx.paths.audio_dir.glob(f"{scene.id}.*"):
        old.unlink()
    ctx.paths.audio_dir.mkdir(parents=True, exist_ok=True)
    tone.unlink(missing_ok=True)
    tone.parent.mkdir(parents=True, exist_ok=True)
    if span:
        ffmpeg.write_room_tone(voice, tone, *span)
    elif borrowed:
        shutil.copyfile(borrowed, tone)
    if cuts or quiet:
        audio = ctx.paths.audio_dir / f"{scene.id}.wav"
        ffmpeg.insert_silence(voice, audio, cuts, **({"tone": tone, "quiet": quiet} if has_tone else {}))
    else:
        audio = ctx.paths.audio_dir / voice.name
        shutil.copyfile(voice, audio)
    shifted = holds.shift(voiced, cuts)
    record = {**made_from, "narration": scene.narration, "seconds": round(ffmpeg.probe_duration(audio), 3)}
    if shifted is not None:
        record.update(spoken=shifted.text, character_starts=shifted.starts)
    _write(ctx.paths.held(scene.id), record)
    # New audio is finished again.
    ctx.paths.merged(scene.id).unlink(missing_ok=True)
    return audio, True


def run(ctx: StepContext) -> None:
    # The provider speaks the pronunciation list's spoken forms. The narration
    # itself is left as written, for the transcript.
    terms = ctx.terms
    provider = get_tts_provider(ctx.voice, terms)
    scenes = ctx.segments

    # The room tone of the latest segment that has one: for a short segment that has no pause of its own.
    borrowed: Path | None = None
    # Segments before the first one with a room tone (a short opening, say): they take that first one, so the
    # pause after the opening is not digital silence.
    waiting: list[tuple] = []
    try:
        for index, scene in enumerate(scenes, start=1):
            around = holds.neighbors(scenes, index - 1)
            voice, voiced, made = _voice(ctx, scene, provider, terms, around)
            audio, rebuilt = _held(ctx, scene, voice, voiced, terms, around, borrowed)
            ctx.progress(f"{index}/{len(scenes)} segments ({ctx.voice.tts_provider})")
            if ctx.paths.room_tone(scene.id).exists():
                borrowed = ctx.paths.room_tone(scene.id)
                for earlier in waiting:
                    _held(ctx, *earlier[1:6], borrowed)
                waiting = []
            elif borrowed is None:
                waiting.append((index, scene, voice, voiced, terms, around))
    finally:
        # What the voice cost is kept with the job, also when a later segment failed.
        if provider.credits:
            ctx.voice_credits += provider.credits
