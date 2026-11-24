"""Brings a scene's voice to one loudness: from second to second, and the scene as a whole.

A voice can come back from its provider at another volume with every request, and drift
inside one: a sentence louder, the end of another trailing off. The final video's loudness
pass moves the whole video by one gain, so those differences stay. Here each scene's audio
is measured, a gain follows the level of the speech around each moment (it knows what comes
next, so it moves slowly and never jumps), the scene is brought to the target loudness, and
a limiter keeps the peaks under the limit.

Nothing is written here: level() returns the FFmpeg filter that does it, and the assemble
step applies it while it adds the audio to the clip. The provider's audio stays as it came.
"""

import math
from dataclasses import dataclass
from pathlib import Path

from voiceover.core.config import VOICE_CONFIG_FILE
from voiceover.schemas.voice import LevelerConfig
from voiceover.services import voice_config
from voiceover.utils import ffmpeg

# Raised when the filter made here changes, so audio levelled by an older one is levelled again.
# 5: the room tone filled in for holds and quiet ends always goes down to the floor.
# 6: a quiet padding comes up to the floor, so the room never drops out at a change of scene.
# 7: the padding gets back the floor that stays down over it after a pause that runs to the end.
VERSION = 7
# A fill meets the voice in a crossfade at each end: the floor stays off that much of it, so no word is touched.
FILL_EDGE_SECONDS = 0.05
# The padding's room tone is brought up to the floor by at most this much: enough for a quiet tone, never a hiss.
MAX_PAD_BOOST_DB = 12.0
# The share of a scene's pieces that are quieter than its "loud level".
LOUD_SHARE = 0.9
# The speech around a moment is measured when at least this share of it is not a pause.
SPOKEN_SHARE = 0.3
# The gains are applied in pieces of this many samples, so a ramp is smooth.
GAIN_FRAME_SAMPLES = 480
# The gain's line is drawn with the points that move it by at least this much (dB). Doubled
# until the filter fits in a command line.
SMALLEST_MOVE_DB = 0.2
LONGEST_FILTER = 16000
# The floor's own filter (services: floor_filter), beside the gain's on the same command line.
LONGEST_FLOOR_FILTER = 8000
# FFmpeg's expressions take only about 95 terms in one sum (measured with FFmpeg 9). Longer sums
# are added up in parenthesized groups of this many, which it takes in any number.
SUM_GROUP = 20
# A scene is at the target when it is this close to it (LU), and is corrected at most this often.
CLOSE_ENOUGH_LU = 0.1
MAX_CORRECTIONS = 4
STEREO = "aformat=channel_layouts=stereo"


@dataclass(frozen=True)
class Levelling:
    """What level() found in a scene's audio, and the filter that evens it out."""

    filter: str
    measured_lufs: float  # as the provider made it
    gain_db: float  # the scene's own gain to the target, after it was evened
    swing_db: float  # how far apart the gain's highest and lowest point inside the scene are
    end_cut_db: float = 0.0  # how far the floor stays down after the end of the audio, over the clip's padding


def load_config(voice_type: str = "", path: Path = VOICE_CONFIG_FILE) -> LevelerConfig:
    """The leveler's numbers for a voice type (the default one when none is named), from voice.json."""
    return voice_config.leveler(voice_type, path)


def recipe(config: LevelerConfig | None, target_lufs: float, peak_db: float) -> dict:
    """What a scene's audio was levelled with. Kept beside the result, so a change is noticed."""
    if config is None:
        return {"leveler": None}
    return {"leveler": config.model_dump(), "target_lufs": target_lufs, "peak_db": peak_db, "version": VERSION}


def _mean_db(levels: list[float]) -> float:
    """The level of several pieces together: the mean of their power."""
    return 10 * math.log10(sum(10 ** (level / 10) for level in levels) / len(levels))


def gain_curve(levels: list[float], config: LevelerConfig) -> list[float]:
    """The gain (dB) for each piece of a scene's audio, from the level of each piece (ffmpeg.rms_levels).

    Each moment is compared with the scene: the speech in the window around it against all the
    speech of the scene. Where it is quieter the gain goes up, where it is louder it goes down.
    In a pause, and over a breath or a noise far under the scene, the gain stays where it was.
    Empty for audio without speech.
    """
    if not levels:
        return []
    loud = sorted(levels)[min(len(levels) - 1, int(len(levels) * LOUD_SHARE))]
    if loud <= ffmpeg.SILENT_DB:
        return []
    spoken = [level > loud - config.gate_db for level in levels]
    scene = _mean_db([level for level, on in zip(levels, spoken) if on])

    half = max(1, round(config.window_ms / config.frame_ms / 2))
    enough = max(2, round(2 * half * SPOKEN_SHARE))
    gains: list[float | None] = []
    held: float | None = None
    for index in range(len(levels)):
        window = range(max(0, index - half), min(len(levels), index + half + 1))
        around = [levels[at] for at in window if spoken[at]]
        if len(around) >= enough:
            here = _mean_db(around)
            if here >= scene - config.ignore_below_db:
                held = max(-config.max_change_db, min(config.max_change_db, config.strength * (scene - here)))
        gains.append(held)
    first = next((gain for gain in gains if gain is not None), 0.0)
    filled = [first if gain is None else gain for gain in gains]

    # Smoothed, so the gain never moves fast enough to be heard as a change.
    span = max(1, round(config.smooth_ms / config.frame_ms / 2))
    return [sum(filled[max(0, at - span): at + span + 1]) / len(filled[max(0, at - span): at + span + 1]) for at in range(len(filled))]


def _sum(terms: list[str]) -> str:
    """The terms added up, in groups FFmpeg can parse however many there are. The sum is the same."""
    while len(terms) > SUM_GROUP:
        terms = [f"({'+'.join(terms[at:at + SUM_GROUP])})" for at in range(0, len(terms), SUM_GROUP)]
    return "+".join(terms)


def curve_filter(curve: list[float], config: LevelerConfig) -> str:
    """The FFmpeg filter that applies a gain curve, as straight lines between points. Empty when it changes nothing."""
    if not curve or max(abs(gain) for gain in curve) < SMALLEST_MOVE_DB:
        return ""
    frame = config.frame_ms / 1000
    every = max(1, round(config.point_ms / config.frame_ms))
    points = [(at * frame, curve[at]) for at in range(0, len(curve), every)]

    smallest = SMALLEST_MOVE_DB
    while True:
        terms, now = [f"({points[0][1]:.2f})"], points[0][1]
        for (start, _), (end, gain) in zip(points, points[1:]):
            if abs(gain - now) >= smallest:
                terms.append(f"({gain - now:.2f})*clip((t-{start:.2f})/{end - start:.2f},0,1)")
                now = gain
        made = f"asetnsamples=n={GAIN_FRAME_SAMPLES}:p=0,volume=volume='pow(10,({_sum(terms)})/20)':eval=frame"
        if len(made) <= LONGEST_FILTER:
            return made
        smallest *= 2


def quiet_runs(levels: list[float], config: LevelerConfig) -> list[tuple[int, int]]:
    """The pauses of a scene: (first piece, piece after the last) of each stretch of at least min_quiet_ms
    that is quiet_below_db or more under the scene's loud level. Words, their tails and breaths are louder."""
    if not levels:
        return []
    loud = sorted(levels)[min(len(levels) - 1, int(len(levels) * LOUD_SHARE))]
    quiet = [level < loud - config.quiet_below_db for level in levels]
    shortest = max(1, round(config.min_quiet_ms / config.frame_ms))
    runs, start = [], None
    for index, on in enumerate([*quiet, False]):
        if on and start is None:
            start = index
        elif not on and start is not None:
            if index - start >= shortest:
                runs.append((start, index))
            start = None
    return runs


def _with_fills(runs: list[tuple[int, int]], fills: list[tuple[float, float]], frames: int, frame: float) -> list[tuple[int, int]]:
    """The pauses, with every stretch of room tone the voice step filled in (holds, quiet ends) counted as one,
    however loud it is next to the speech: in a quiet take (useReducer v5 s34, 2026-11-16, lifted 26.9 dB) the
    room tone after the last word was only about 30 dB under the speech, was not taken for a pause, and was
    lifted to -43 dBFS, heard as a "zzz"."""
    found = list(runs)
    for start, end in fills:
        first = max(0, math.ceil((start + FILL_EDGE_SECONDS) / frame))
        # A fill that runs to the end of the audio stays down to it: the clip's padding goes on at the floor after it.
        after = frames if end >= frames * frame - FILL_EDGE_SECONDS else min(frames, math.floor((end - FILL_EDGE_SECONDS) / frame))
        if after > first:
            found.append((first, after))
    merged: list[tuple[int, int]] = []
    for first, after in sorted(found):
        if merged and first <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], after))
        else:
            merged.append((first, after))
    return merged


def floor_filter(
    levels: list[float], curve: list[float], gain_db: float, config: LevelerConfig, fills: list[tuple[float, float]] = ()
) -> str:
    """The FFmpeg filter that brings every pause down to the floor (floor_db) after the gain: the voice's
    own quiet and the room tone that fills the holds, which the gain lifts with the speech. Down over
    floor_ramp_ms once a pause starts, back up over floor_ramp_ms before it ends, so no word is touched;
    a pause that runs to the end stays down (the clip's room tone after it too, see pad_gain). Empty when no
    pause is above the floor. `fills`: (start, end) of the room tone the voice step put in, always a pause."""
    return _floor(levels, curve, gain_db, config, fills)[0]


def _floor(
    levels: list[float], curve: list[float], gain_db: float, config: LevelerConfig, fills: list[tuple[float, float]] = ()
) -> tuple[str, float]:
    """floor_filter's filter, and how far it stays down after the end of the audio (dB): the cut of a pause that
    runs to the end, which the clip's padding gets too."""
    frame = config.frame_ms / 1000
    ramp = config.floor_ramp_ms / 1000
    pauses: list[tuple[float, list[str], bool]] = []
    for first, after in _with_fills(quiet_runs(levels, config), list(fills), len(levels), frame):
        lifted = sum(curve[first:after]) / (after - first) if curve else 0.0
        cut = min(config.max_floor_cut_db, _mean_db(levels[first:after]) + lifted + gain_db - config.floor_db)
        if cut < SMALLEST_MOVE_DB:
            continue
        start, end = first * frame, after * frame
        span = min(ramp, (end - start) / 2)
        down = [f"(-{cut:.2f})*clip((t-{start:.3f})/{span:.3f},0,1)"]
        stays = after >= len(levels)
        up = [] if stays else [f"({cut:.2f})*clip((t-{end - span:.3f})/{span:.3f},0,1)"]
        pauses.append((cut, down + up, stays))
    # The command line has a limit: with very many pauses, the ones that come down the least are left as they are.
    while pauses:
        terms = [term for _, pause, _ in pauses for term in pause]
        made = f"asetnsamples=n={GAIN_FRAME_SAMPLES}:p=0,volume=volume='pow(10,({_sum(terms)})/20)':eval=frame"
        if len(made) <= LONGEST_FLOOR_FILTER:
            return made, sum(cut for cut, _, stays in pauses if stays)
        pauses.remove(min(pauses, key=lambda pause: pause[0]))
    return "", 0.0


def _chain(gains: str, gain_db: float, ceiling_db: float, floor: str = "") -> str:
    limit = 10 ** (ceiling_db / 20)
    limiter = f"alimiter=limit={limit:.4f}:attack=5:release=50:level=false"
    # A voice has one channel and the video two. Spread over two first, each channel's peaks are
    # 3 dB lower at the same loudness, so the limiter has that much less to take away. It also
    # makes what is measured here the same as what the video gets.
    return ",".join(part for part in (STEREO, gains, f"volume={gain_db:.2f}dB", floor, limiter) if part)


def pad_gain(tone: Path, levelling: "Levelling | None", config: LevelerConfig) -> float:
    """The gain (dB) for the room tone that pads a scene's clip after its voice, so the padding lands at the floor
    once the scene's gain lifts it. The floor filter only knows the pauses inside the voice; the padding comes
    after it. A louder tone was lifted to -40 dBFS there (a "zzz" at the end of a useLayoutEffect title,
    2026-11-15); a quieter one stayed at -70, 7 dB under the pauses around it, and the room went quiet for half a
    second at every change of scene, heard as a skip (useRef v5 at 2:25, 2026-11-16). Brought up by at most
    MAX_PAD_BOOST_DB. The floor of a pause that runs to the end of the voice stays down over the padding too
    (Levelling.end_cut_db): that is given back here, or the padding came down twice, to -81 dBFS."""
    if levelling is None:
        return 0.0
    return min(MAX_PAD_BOOST_DB, config.floor_db - (ffmpeg.rms_db(tone) + levelling.gain_db)) + levelling.end_cut_db


def level(
    audio: Path, target_lufs: float, peak_db: float, config: LevelerConfig, fills: list[tuple[float, float]] = ()
) -> Levelling | None:
    """Measure a scene's audio and return how to even it out. None for audio without speech. `fills`: the room
    tone the voice step put in (holds.filled_spans), brought down to the floor whatever its level."""
    levels = ffmpeg.rms_levels(audio, config.frame_ms / 1000)
    curve = gain_curve(levels, config)
    source = ffmpeg.measure_loudness(audio, target_lufs, peak_db) if curve else None
    if source is None:
        return None
    gains = curve_filter(curve, config)
    ceiling = peak_db - config.limiter_headroom_db

    evened = (ffmpeg.measure_loudness(audio, target_lufs, peak_db, gains) if gains else None) or source
    gain = target_lufs - evened["input_i"]
    # The limiter takes some loudness away with the peaks, and more of it the higher the gain.
    # So the result is measured and the gain corrected, until it is at the target.
    for _ in range(MAX_CORRECTIONS):
        limited = ffmpeg.measure_loudness(audio, target_lufs, peak_db, _chain(gains, gain, ceiling))
        if limited is None or abs(target_lufs - limited["input_i"]) <= CLOSE_ENOUGH_LU:
            break
        gain += target_lufs - limited["input_i"]
    # The pauses come down last: loudness is measured over the speech (EBU R128 gates the pauses out),
    # so the floor leaves the scene's loudness where the gain put it.
    floor, end_cut = _floor(levels, curve, gain, config, fills)

    return Levelling(
        filter=_chain(gains, gain, ceiling, floor),
        measured_lufs=round(source["input_i"], 1),
        gain_db=round(gain, 1),
        swing_db=round(max(curve) - min(curve), 1),
        end_cut_db=round(end_cut, 2),
    )
