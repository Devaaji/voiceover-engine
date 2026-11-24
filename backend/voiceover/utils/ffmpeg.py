"""Thin wrappers around the ffmpeg and ffprobe command lines."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Iterable


def _binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"{name} was not found on PATH. Install FFmpeg and restart.")
    return path


def require() -> None:
    """Raise if ffmpeg or ffprobe is missing."""
    _binary("ffmpeg")
    _binary("ffprobe")


def _run(args: list[str]) -> str:
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise RuntimeError(f"{Path(args[0]).stem} failed: {proc.stderr.strip()[-800:]}")
    return proc.stdout


def _encode(args: list[str], dst: Path) -> None:
    """Run ffmpeg into a temp file, so a failed run never leaves a half-written dst."""
    tmp = dst.with_name(f"{dst.stem}.part{dst.suffix}")
    try:
        _run([_binary("ffmpeg"), "-y", "-loglevel", "error", *args, str(tmp)])
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)


def probe_duration(path: Path) -> float:
    out = _run(
        [
            _binary("ffprobe"),
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    return float(out.strip())


def trim_to_mp4(
    src: Path, dst: Path, start: float, duration: float, width: int, height: int, fps: int
) -> None:
    """Cut [start, start + duration] out of a recording and encode it as a silent H.264 clip.

    If the recording is short, the last frame is held so the clip always lasts `duration`.
    """
    filters = ",".join(
        [
            f"fps={fps}",
            f"scale={width}:{height}:force_original_aspect_ratio=decrease",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2",
            f"tpad=stop_mode=clone:stop_duration={duration:.3f}",
        ]
    )
    _encode(
        [
            "-ss", f"{start:.3f}",
            "-i", str(src),
            "-vf", filters,
            "-t", f"{duration:.3f}",
            "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        ],
        dst,
    )


def scene_audio(
    audio: Path, dst: Path, duration: float, audio_filter: str = "", tone: Path | None = None, tone_gain_db: float = 0.0
) -> None:
    """Write a scene's finished audio to dst (a .wav), exactly `duration` long, to the sample.

    The audio is padded up to `duration`: with `tone` looped (the voice's own quiet, see
    write_room_tone) when there is one, else with silence. `audio_filter` is applied to the
    audio first (the leveler's gains, for example).

    The tone crossfades with the end of the audio, which may be the voice or room tone already:
    either way there is no click and no dip. `tone_gain_db` changes the tone's level first, so the padding
    lands at the floor after `audio_filter` raises the scene (voice_leveler.pad_gain).
    """
    samples = round(duration * SAMPLE_RATE)
    if tone is not None:
        tone_samples = round(probe_duration(tone) * SAMPLE_RATE)
        pad = max(0.0, duration - probe_duration(audio)) + 1.0
        fill = _tone_fill("[g]", tone_samples, pad + CROSSFADE_SECONDS, "[t]")
        graph = (
            f"[1:a]volume={tone_gain_db:.2f}dB[g];[0:a]{_MONO}[v];{fill};"
            f"[v][t]acrossfade=d={CROSSFADE_SECONDS}:c1=qsin:c2=qsin,"
            f"{','.join(part for part in ('aresample=48000', audio_filter) if part)}"
        )
        inputs = ["-i", str(audio), "-i", str(tone)]
    else:
        graph = f"[0:a]{','.join(part for part in ('aresample=48000', audio_filter, 'apad') if part)}"
        inputs = ["-i", str(audio)]
    graph += f",atrim=end_sample={samples}[a]"
    _encode([*inputs, "-filter_complex", graph, "-map", "[a]", "-c:a", "pcm_s16le", "-ac", "2"], dst)


def _listing(files: list[Path], dst: Path) -> None:
    """A concat demuxer list of `files`."""
    paths = [file.resolve().as_posix().replace("'", "'\\''") for file in files]
    dst.write_text("".join(f"file '{path}'\n" for path in paths), encoding="utf-8")


def join(videos: list[Path], audios: list[Path], dst: Path) -> None:
    """Join the scenes: their clips (video only, not encoded again) and their audio (.wav, to the sample).

    dst is a .mov (it keeps the clips' timestamps and takes uncompressed audio), so the audio is
    encoded once, at the end. Joining clips that each carry their own AAC audio put the encoder's
    delay (about 20 ms of silence) at every join, and the voice fell further behind the picture
    with each scene.
    """
    video_list = dst.with_name(f"{dst.stem}.video.txt")
    audio_list = dst.with_name(f"{dst.stem}.audio.txt")
    _listing(videos, video_list)
    _listing(audios, audio_list)
    try:
        _encode(
            [
                "-f", "concat", "-safe", "0", "-i", str(video_list),
                "-f", "concat", "-safe", "0", "-i", str(audio_list),
                "-map", "0:v", "-map", "1:a",
                "-c:v", "copy", "-c:a", "pcm_s16le",
            ],
            dst,
        )
    finally:
        video_list.unlink(missing_ok=True)
        audio_list.unlink(missing_ok=True)


# --- Loudness ---

LOUDNESS_RANGE = 11.0
# Quieter than this is treated as silence (the mock voice): there is nothing to normalize.
SILENCE_LUFS = -70.0


def measure_loudness(path: Path, target_lufs: float, true_peak_db: float, audio_filter: str = "") -> dict | None:
    """Measure a file's audio (EBU R128) with the loudnorm filter.

    Returns loudnorm's measurements (input_i, input_tp, input_lra, input_thresh,
    target_offset) as floats, or None when the audio is silent. With `audio_filter`,
    the audio is measured as it is after that filter.
    """
    loudnorm = f"loudnorm=I={target_lufs}:TP={true_peak_db}:LRA={LOUDNESS_RANGE}:print_format=json"
    proc = subprocess.run(
        [
            _binary("ffmpeg"), "-hide_banner", "-nostats", "-i", str(path),
            "-af", ",".join(part for part in (audio_filter, loudnorm) if part),
            "-vn", "-f", "null", "-",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip()[-800:]}")
    # The filter prints one JSON object at the end of the log.
    start = proc.stderr.rfind("{")
    end = proc.stderr.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError("ffmpeg did not report the loudness.")
    values = {key: float(value) for key, value in json.loads(proc.stderr[start : end + 1]).items()
              if key != "normalization_type"}
    if values["input_i"] < SILENCE_LUFS:  # includes -inf
        return None
    return values


def normalize_loudness(
    src: Path, dst: Path, measured: dict, target_lufs: float, true_peak_db: float
) -> None:
    """Second loudnorm pass: bring the audio to the target, using the first pass's measurements.

    The video is copied as it is. Only the audio is encoded again.
    """
    loudnorm = (
        f"loudnorm=I={target_lufs}:TP={true_peak_db}:LRA={LOUDNESS_RANGE}"
        f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}:linear=true"
    )
    _encode(
        [
            "-i", str(src),
            "-af", loudnorm,
            "-c:v", "copy",
            # loudnorm works at 192 kHz internally, so the rate is set back.
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart",
        ],
        dst,
    )


SAMPLE_RATE = 48000
# What a piece of audio without any sound is reported as (dBFS).
SILENT_DB = -120.0


def frame_at_edge(src: Path, dst: Path, last: bool) -> None:
    """Save the first or the last frame of a video as a picture (the format of dst's extension)."""
    seek = ["-sseof", "-0.1"] if last else ["-ss", "0"]
    _run([_binary("ffmpeg"), "-y", "-loglevel", "error", *seek, "-i", str(src), "-frames:v", "1", "-update", "1", str(dst)])


# Room tone and the voice cross over this fast where they meet: no click, and no dip to silence.
CROSSFADE_SECONDS = 0.01
# Float, not 16-bit: the voice comes back very quiet (about -42 LUFS) and is raised about 27 dB only when the
# scene is levelled, so rounding it to 16 bits before that raised the rounding noise with it, to 24-31 dB
# under the fading ends of words. The scene's finished audio, at its real level, is 16-bit.
_MONO = f"aresample={SAMPLE_RATE},aformat=sample_fmts=flt:channel_layouts=mono"
# What the voice and its room tone are kept in until the leveler's gain.
_WORKING_CODEC = "pcm_f32le"


# A room tone is made this long, from noise: long enough that its repeats are never heard as a rhythm.
ROOM_TONE_SECONDS = 6.0
# The same noise every time, so a scene made again sounds the same.
ROOM_TONE_SEED = 7
# The room tone is as loud as the voice's own quiet, but never louder than this (dBFS, before the
# loudness is set) nor quieter than the floor: a pause is heard as quiet, never as hiss or a dropout.
ROOM_TONE_MAX_DB = -64.0
ROOM_TONE_MIN_DB = -80.0
# Soft "air" without a hum: pink noise without its lowest and highest part.
ROOM_TONE_BAND = "highpass=f=100,lowpass=f=6000"


def write_room_tone(src: Path, dst: Path, start: float, seconds: float) -> None:
    """Save to dst (a .wav) a room tone as loud as the quiet piece of src (start, seconds), followed by
    itself backwards so it loops without a jump.

    The piece itself, looped, was the room tone before. But a quiet piece of a voice is often a tenth of
    a second long, and a tenth of a second looped is a rhythm ("tetet") the ear picks out in every hold;
    a piece with the tail of a vowel in it loops into a hum. So the room tone is smooth noise with no
    tone and no rhythm in it, at the piece's level (within ROOM_TONE_MIN_DB and ROOM_TONE_MAX_DB): a
    pause sounds clean and quiet, where digital silence would sound like the recording stopped.
    """
    # Measured in the noise's own band: most of a voice's quiet is rumble under 100 Hz that nobody hears,
    # and noise as loud as all of it is louder than the quiet the ear hears around it.
    heard = rms_db(src, start, max(seconds, 0.02), ROOM_TONE_BAND)
    level = min(ROOM_TONE_MAX_DB, max(ROOM_TONE_MIN_DB, heard))
    noise = dst.with_name(f"{dst.stem}.noise.wav")
    try:
        _encode(
            ["-f", "lavfi", "-i",
             f"anoisesrc=d={ROOM_TONE_SECONDS}:c=pink:r={SAMPLE_RATE}:a=0.5:s={ROOM_TONE_SEED},{ROOM_TONE_BAND},{_MONO}",
             "-c:a", "pcm_f32le"],
            noise,
        )
        gain = level - rms_db(noise)
        chain = f"[0:a]volume={gain:.2f}dB,{_MONO},asplit=2[f][b];[b]areverse[r];[f][r]concat=n=2:v=0:a=1[out]"
        _encode(["-i", str(noise), "-filter_complex", chain, "-map", "[out]", "-c:a", _WORKING_CODEC], dst)
    finally:
        noise.unlink(missing_ok=True)


def rms_db(path: Path, start: float = 0.0, seconds: float | None = None, audio_filter: str = "") -> float:
    """The level (RMS, dBFS) of a file's audio, or of `seconds` of it from `start`, mixed to one channel,
    after `audio_filter` (a band, for example)."""
    trim = f"atrim=start={start:.3f}" + (f":duration={seconds:.3f}" if seconds else "") + (f",{audio_filter}" if audio_filter else "")
    proc = subprocess.run(
        [
            _binary("ffmpeg"), "-hide_banner", "-nostats", "-i", str(path),
            "-af", f"{trim},aformat=channel_layouts=mono,astats=metadata=1:reset=0,"
                   "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
            "-vn", "-f", "null", "-",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip()[-800:]}")
    level = SILENT_DB
    for line in proc.stdout.splitlines():
        _, found, value = line.partition("lavfi.astats.Overall.RMS_level=")
        if found and value.strip() not in ("-inf", "nan"):
            level = max(SILENT_DB, float(value))
    return level


def _tone_fill(input_label: str, tone_samples: int, seconds: float, label: str) -> str:
    """A filter that loops the room tone on `input_label` for `seconds`, as `label`. It meets the voice
    in a crossfade (CROSSFADE_SECONDS), not a fade to silence: at the ends of a scene's audio the next
    scene's room tone goes on, and anywhere a fade to silence would be a dip the ear hears."""
    return f"{input_label}{_MONO},aloop=loop=-1:size={tone_samples},atrim=duration={seconds:.3f},asetpts=PTS-STARTPTS{label}"


def _without_slivers(pieces: list[list]) -> list[list]:
    """The pieces with any bit of voice too short to crossfade on both sides filled with room tone too."""
    found: list[list] = []
    for piece in pieces:
        if piece[0] == "voice" and len(pieces) > 1 and piece[2] - piece[1] < 3 * CROSSFADE_SECONDS:
            piece = ["fill", piece[2] - piece[1]]
        if piece[0] == "fill" and found and found[-1][0] == "fill":
            found[-1][1] += piece[1]
        else:
            found.append(list(piece))
    return found


def insert_silence(
    src: Path,
    dst: Path,
    cuts: list[tuple[float, float]],
    tone: Path | None = None,
    quiet: list[tuple[float, float]] | None = None,
) -> None:
    """Write src's audio to dst (a .wav) with pauses put in: (at second, seconds) for each cut.

    A cut at or after the end adds the pause at the end. A pause is filled with `tone`, the
    voice's own quiet looped (write_room_tone), or with digital silence when there is none.
    `quiet` are (start, end) stretches of src that are digital silence: with a tone, they are
    replaced by as much of it, so nothing moves. Everything is resampled to one rate and one
    channel, and the room tone crosses over with the voice (CROSSFADE_SECONDS), so the pieces join
    without a click or a dip; the fills are longer by the overlaps, so the voice keeps its times.
    """
    duration = probe_duration(src)
    tone_samples = round(probe_duration(tone) * SAMPLE_RATE) if tone is not None else 0
    # (at, seconds of pause, where src goes on): a cut goes on where it is, a quiet stretch after it.
    events = [(at, seconds, at) for at, seconds in cuts]
    if tone_samples:
        events += [(begin, end - begin, end) for begin, end in quiet or [] if end > begin]
    # The pieces in order: ["voice", start, end] of src, or ["fill", seconds].
    pieces: list[list] = []
    start = 0.0
    for at, seconds, resume in sorted(events):
        at = min(max(at, start), duration)
        if at > start:
            pieces.append(["voice", start, at])
        if pieces and pieces[-1][0] == "fill":
            pieces[-1][1] += seconds  # fills that meet are one fill
        else:
            pieces.append(["fill", seconds])
        start = max(at, min(resume, duration))
    if start < duration:
        pieces.append(["voice", start, duration])
    if tone_samples:
        pieces = _without_slivers(pieces)
    chain = []
    for index, piece in enumerate(pieces):
        label = f"[p{index}]"
        if piece[0] == "voice":
            chain.append(f"[0:a]atrim=start={piece[1]:.3f}:end={piece[2]:.3f},asetpts=PTS-STARTPTS,{_MONO}{label}")
        elif tone_samples:
            # Longer by the crossfades that lay it over the voice on either side, so nothing moves.
            overlaps = (index > 0) + (index + 1 < len(pieces))
            chain.append(_tone_fill("[1:a]", tone_samples, piece[1] + overlaps * CROSSFADE_SECONDS, label))
        else:
            chain.append(f"anullsrc=r={SAMPLE_RATE}:cl=mono,atrim=duration={piece[1]:.3f},{_MONO}{label}")
    if tone_samples and len(pieces) > 1:
        # Equal-power crossfades between the voice and its room tone: no click, and no dip to silence.
        joined = "[p0]"
        for index in range(1, len(pieces)):
            out = f"[x{index}]" if index + 1 < len(pieces) else "[out]"
            chain.append(f"{joined}[p{index}]acrossfade=d={CROSSFADE_SECONDS}:c1=qsin:c2=qsin{out}")
            joined = out
    else:
        chain.append(f"{''.join(f'[p{index}]' for index in range(len(pieces)))}concat=n={len(pieces)}:v=0:a=1[out]")
    inputs = ["-i", str(src), *(["-i", str(tone)] if tone_samples else [])]
    _encode([*inputs, "-filter_complex", ";".join(chain), "-map", "[out]", "-c:a", _WORKING_CODEC], dst)


# A picture this close to the frame before counts as standing still; audio below this level as quiet.
# At -60 dB a few characters typed on a 1920x1080 editor counted as standing still, so the voice waiting
# for the typing (services/typing_holds.py) was reported as a dead stop while the code was visibly being
# typed (useReducer, 2026-11-16: 11 false stops). At -70 dB typing counts as movement, and a real stop
# (a still diagram in a silent hold) is still found.
FREEZE_NOISE_DB = -70
QUIET_DB = -35
_DETECTED = re.compile(r"(freeze|silence)_(start|end): ([\d.]+)")


# A noisy pause: a steady hiss, louder than the floor by this much (dB) but under speech, for at least this long.
NOISY_PAUSE_ABOVE_FLOOR_DB = 8.0
NOISY_PAUSE_SPEECH_DB = -32.0
# Longer than a breath (0.2 to 0.4 s between sentences, kept: it is part of the voice); the hisses heard
# were 0.5 to 2.6 s.
NOISY_PAUSE_SECONDS = 0.45
NOISY_PAUSE_STEADY_DB = 2.0
# Hiss is bright: at least this share of it (dB) lies above 2 kHz. A soft voiced sound ("mm") is not.
NOISY_PAUSE_HISS_SHARE_DB = -15.0


def noisy_pauses(path: Path, floor_db: float) -> list[tuple[float, float, float]]:
    """(start, seconds, level dBFS) of every stretch of a file's audio that sounds like a pause filled with
    hiss: steady (it varies less than NOISY_PAUSE_STEADY_DB), louder than the floor by NOISY_PAUSE_ABOVE_FLOOR_DB
    and quieter than speech, and bright (NOISY_PAUSE_HISS_SHARE_DB of it above 2 kHz). Room tone lifted with the
    voice sounds like that, a "zzz" in the pause; a soft voiced sound in the voice itself is dull, and is left out."""
    frame = 0.05
    levels = rms_levels(path, frame)
    bright = rms_levels(path, frame, "highpass=f=2000:poles=2")
    shortest = round(NOISY_PAUSE_SECONDS / frame)
    found: list[tuple[float, float, float]] = []
    run: list[float] = []
    start = 0
    for index, level in enumerate([*levels, SILENT_DB]):
        steady = not run or abs(level - sum(run) / len(run)) <= NOISY_PAUSE_STEADY_DB
        if floor_db + NOISY_PAUSE_ABOVE_FLOOR_DB < level < NOISY_PAUSE_SPEECH_DB and steady:
            if not run:
                start = index
            run.append(level)
            continue
        if len(run) >= shortest:
            share = sum(bright[start : start + len(run)]) / len(run) - sum(run) / len(run) if len(bright) >= start + len(run) else 0.0
            if share >= NOISY_PAUSE_HISS_SHARE_DB:
                found.append((start * frame, len(run) * frame, sum(run) / len(run)))
        run = [level] if floor_db + NOISY_PAUSE_ABOVE_FLOOR_DB < level < NOISY_PAUSE_SPEECH_DB else []
        start = index
    return found


def dead_stops(path: Path, shortest: float) -> list[tuple[float, float]]:
    """(start, seconds) of every stretch of at least `shortest` seconds in which the picture stands
    still and the audio is quiet at once: a stop that looks like the video stalled."""
    proc = subprocess.run(
        [
            _binary("ffmpeg"), "-hide_banner", "-nostats", "-i", str(path),
            "-filter_complex",
            f"[0:v]freezedetect=n={FREEZE_NOISE_DB}dB:d={shortest}[v];[0:a]silencedetect=n={QUIET_DB}dB:d={shortest}[a]",
            "-map", "[v]", "-map", "[a]", "-f", "null", "-",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip()[-800:]}")
    length = probe_duration(path)
    spans: dict[str, list[list[float]]] = {"freeze": [], "silence": []}
    for kind, edge, value in _DETECTED.findall(proc.stderr):
        if edge == "start":
            spans[kind].append([float(value), length])  # open until its end is reported
        elif spans[kind]:
            spans[kind][-1][1] = float(value)
    found = []
    for still_start, still_end in spans["freeze"]:
        for quiet_start, quiet_end in spans["silence"]:
            start, end = max(still_start, quiet_start), min(still_end, quiet_end)
            if end - start >= shortest:
                found.append((round(start, 2), round(end - start, 2)))
    return sorted(found)


def rms_levels(path: Path, frame_seconds: float, audio_filter: str = "") -> list[float]:
    """The level (RMS, dBFS) of every `frame_seconds` of a file's audio, mixed to one channel, after `audio_filter`
    (a band, for example)."""
    samples = max(1, round(SAMPLE_RATE * frame_seconds))
    proc = subprocess.run(
        [
            _binary("ffmpeg"), "-hide_banner", "-nostats", "-i", str(path),
            "-af", f"aresample={SAMPLE_RATE},aformat=channel_layouts=mono,{audio_filter + ',' if audio_filter else ''}"
                   f"asetnsamples=n={samples}:p=0,astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
            "-vn", "-f", "null", "-",
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {proc.stderr.strip()[-800:]}")
    levels = []
    for line in proc.stdout.splitlines():
        _, found, value = line.partition("lavfi.astats.Overall.RMS_level=")
        if found:
            # Digital silence is printed as -inf.
            levels.append(max(SILENT_DB, float(value)) if value.strip() not in ("-inf", "nan") else SILENT_DB)
    return levels


# --- Pictures ---


def convert_image(src: Path, dst: Path) -> None:
    """Save a picture in the format of dst's extension."""
    _run([_binary("ffmpeg"), "-y", "-loglevel", "error", "-i", str(src), "-frames:v", "1", "-update", "1", str(dst)])


def frames_to_video(frames: Iterable[bytes], dst: Path, fps: int, image: str, encoder: list[str]) -> None:
    """Encode pictures that arrive one by one into a video. `image` is their codec: "png" or "mjpeg"."""
    tmp = dst.with_name(f"{dst.stem}.part{dst.suffix}")
    args = [_binary("ffmpeg"), "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(fps), "-c:v", image, "-i", "-", *encoder, str(tmp)]
    proc = subprocess.Popen(args, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        try:
            for frame in frames:
                proc.stdin.write(frame)
            proc.stdin.close()
        except BrokenPipeError:
            pass  # ffmpeg stopped reading: its own message below says why
        problem = proc.stderr.read().decode("utf-8", errors="replace")
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg failed: {problem.strip()[-800:]}")
        os.replace(tmp, dst)
    finally:
        if proc.poll() is None:
            proc.kill()
        tmp.unlink(missing_ok=True)
