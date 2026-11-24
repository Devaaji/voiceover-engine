"""Step 2: finish each segment's audio, join all segments, and set the loudness of the voiceover.

voiceover-engine: from backend/app/pipeline/steps/assemble.py of the Video Automation repo (2026-11-23). Each
segment's audio is levelled and filled up to its length with room tone (work/merged/<id>.wav), as each scene's was;
a segment lasts as long as its audio plus SCENE_PADDING, as a scene's clip did. Not copied: joining with the video
clips and looking for dead stops (a still picture over quiet), which only a video has.
"""

import json
import logging
from pathlib import Path

from voiceover.core.config import VOICE_LEVELER
from voiceover.core.constants import LOUDNESS_TARGET_LUFS, LOUDNESS_TRUE_PEAK_DB, SCENE_PADDING
from voiceover.core.exceptions import StepFailed
from voiceover.output import Format, copy_silent, join_audio, normalize_loudness
from voiceover.pipeline.context import StepContext
from voiceover.segments import Segment as Scene
from voiceover.services import holds, voice_leveler
from voiceover.utils import ffmpeg

log = logging.getLogger(__name__)

ENCODER_PEAK_MARGIN_DB = 1.0
# Encoding lifts the peaks a little, so the filters aim below the limit.
PEAK_DB = LOUDNESS_TRUE_PEAK_DB - ENCODER_PEAK_MARGIN_DB


def leveler_for(ctx: StepContext):
    """How firmly the voice is evened out: the voice type's leveler, or None when VOICE_LEVELER is off."""
    return voice_leveler.load_config(ctx.voice.voice_type) if VOICE_LEVELER else None


def finish(ctx: StepContext, scene: Scene, duration: float, leveler) -> dict:
    """The segment's finished audio (work/merged), `duration` long to the sample: levelled, its end filled with room
    tone. Kept when it was made with the same recipe. Returns what was kept about its levelling."""
    audio = ctx.paths.audio(scene.id)
    if audio is None:
        raise StepFailed(f"Segment {scene.id} is missing its audio. Make the voice first.")
    # The end of each segment is filled with the voice's own quiet when it has some (work/tone).
    wanted = {**voice_leveler.recipe(leveler, LOUDNESS_TARGET_LUFS, PEAK_DB), "pad": "room tone", "seconds": round(duration, 3)}
    merged = ctx.paths.merged(scene.id)
    kept = _kept(ctx.paths.levelled(scene.id))
    # Audio from before the leveler, or levelled with other numbers, is made again.
    if ctx.force or not merged.exists() or kept.get("recipe") != wanted:
        # The room tone the voice step filled in goes down to the floor, however quiet the take.
        fills = holds.filled_spans(_kept(ctx.paths.held(scene.id)))
        levelling = voice_leveler.level(audio, LOUDNESS_TARGET_LUFS, PEAK_DB, leveler, fills) if leveler else None
        tone = ctx.paths.room_tone(scene.id)
        merged.parent.mkdir(parents=True, exist_ok=True)
        ffmpeg.scene_audio(
            audio, merged, duration, levelling.filter if levelling else "",
            tone if tone.exists() else None,
            # The padding after the voice at the floor too, like the pauses inside it.
            voice_leveler.pad_gain(tone, levelling, leveler) if tone.exists() and leveler else 0.0,
        )
        kept = {
            "recipe": wanted,
            "measured_lufs": levelling.measured_lufs if levelling else None,
            "gain_db": levelling.gain_db if levelling else None,
            "swing_db": levelling.swing_db if levelling else None,
        }
        ctx.paths.levelled(scene.id).write_text(json.dumps(kept), encoding="utf-8")
    return kept


def run(ctx: StepContext, fmt: Format) -> dict:
    """Finish every segment and write output/audio.<fmt>. Returns the loudness: as measured, final, true peak, and how
    far apart the segments' voices were before they were levelled."""
    leveler = leveler_for(ctx)
    merged_files: list[Path] = []
    voices: list[float] = []
    for index, scene in enumerate(ctx.segments, start=1):
        audio = ctx.paths.audio(scene.id)
        if audio is None:
            raise StepFailed(f"Segment {scene.id} is missing its audio. Make the voice first.")
        # A segment lasts as long as its audio plus the padding, as a scene's clip did.
        kept = finish(ctx, scene, ffmpeg.probe_duration(audio) + SCENE_PADDING, leveler)
        if kept.get("measured_lufs") is not None:
            voices.append(kept["measured_lufs"])
        merged_files.append(ctx.paths.merged(scene.id))
        ctx.progress(f"{index}/{len(ctx.segments)} segments levelled")

    final = ctx.paths.output(f"audio.{fmt}")
    final.parent.mkdir(parents=True, exist_ok=True)
    for old in final.parent.glob("audio.*"):
        old.unlink()
    joined = ctx.paths.root / "work" / "joined.wav"
    try:
        join_audio(merged_files, joined)
        ctx.progress("Setting the loudness")
        loudness = _set_loudness(joined, final, fmt)
    finally:
        joined.unlink(missing_ok=True)
    if voices and loudness.get("final_lufs") is not None:
        loudness["voice_spread_lu"] = round(max(voices) - min(voices), 1)
    if leveler:
        _warn_noisy_pauses(ctx, final, leveler.floor_db)
    loudness["seconds"] = round(ffmpeg.probe_duration(final), 3)
    return loudness


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:04.1f}"


def _warn_noisy_pauses(ctx: StepContext, final: Path, floor_db: float) -> None:
    """Warn about every pause that still hisses above the floor: the leveler brings the pauses and the padding down
    to it, so one that did not is a bug to report, not a sound to keep."""
    try:
        noisy = ffmpeg.noisy_pauses(final, floor_db)
    except RuntimeError as error:
        ctx.warn(f"Could not listen for noisy pauses: {error}")
        return
    for start, seconds, level in noisy:
        ctx.warn(
            f"A noisy pause at {_clock(start)}: {seconds:.1f}s of steady hiss at {level:.0f} dBFS, where pauses sit at "
            f"{floor_db:.0f}. It is heard as a \"zzz\"."
        )


def _kept(file: Path) -> dict:
    """What was kept with a finished segment about its levelling. Empty when there is none."""
    try:
        kept = json.loads(file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return kept if isinstance(kept, dict) else {}


def _set_loudness(src: Path, dst: Path, fmt: Format) -> dict:
    """Write src to dst at the target loudness, in two passes: measure, then correct."""
    measured = ffmpeg.measure_loudness(src, LOUDNESS_TARGET_LUFS, PEAK_DB)
    if measured is None:
        # Silent audio (the mock voice): nothing to bring up.
        copy_silent(src, dst, fmt)
        return {"measured_lufs": None, "final_lufs": None, "true_peak_db": None}
    normalize_loudness(src, dst, measured, LOUDNESS_TARGET_LUFS, PEAK_DB, fmt)
    after = ffmpeg.measure_loudness(dst, LOUDNESS_TARGET_LUFS, PEAK_DB) or {}
    return {
        "measured_lufs": round(measured["input_i"], 1),
        "final_lufs": round(after["input_i"], 1) if after else None,
        "true_peak_db": round(after["input_tp"], 1) if after else None,
    }

