"""Join the segments' finished audio and write the voiceover's file. New in voiceover-engine.

The old pipeline joined each scene's audio with its video clip (utils/ffmpeg.join) and encoded the audio once, to
AAC, in its loudness pass (utils/ffmpeg.normalize_loudness). A voiceover has no video: the audio is joined on its own,
to the sample, and the same loudness pass writes MP3 (192 kb/s, as the AAC was) or 16-bit WAV.
"""

from pathlib import Path
from typing import Literal

from voiceover.utils import ffmpeg

Format = Literal["mp3", "wav"]
CODECS: dict[str, list[str]] = {
    "mp3": ["-c:a", "libmp3lame", "-b:a", "192k"],
    "wav": ["-c:a", "pcm_s16le"],
}


def join_audio(files: list[Path], dst: Path) -> None:
    """Join the segments' finished audio (.wav, 48 kHz stereo) into one .wav, without encoding it again."""
    listing = dst.with_name(f"{dst.stem}.list.txt")
    ffmpeg._listing(files, listing)
    try:
        ffmpeg._encode(["-f", "concat", "-safe", "0", "-i", str(listing), "-c:a", "pcm_s16le"], dst)
    finally:
        listing.unlink(missing_ok=True)


def normalize_loudness(src: Path, dst: Path, measured: dict, target_lufs: float, true_peak_db: float, fmt: Format) -> None:
    """Second loudnorm pass, as utils/ffmpeg.normalize_loudness: the same filter, into an audio file."""
    loudnorm = (
        f"loudnorm=I={target_lufs}:TP={true_peak_db}:LRA={ffmpeg.LOUDNESS_RANGE}"
        f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
        f":offset={measured['target_offset']}:linear=true"
    )
    # loudnorm works at 192 kHz internally, so the rate is set back.
    ffmpeg._encode(["-i", str(src), "-af", loudnorm, *CODECS[fmt], "-ar", "48000", "-ac", "2"], dst)


def copy_silent(src: Path, dst: Path, fmt: Format) -> None:
    """Silent audio (the mock voice) has no loudness to set: it is only written in the asked format."""
    ffmpeg._encode(["-i", str(src), *CODECS[fmt], "-ar", "48000", "-ac", "2"], dst)
