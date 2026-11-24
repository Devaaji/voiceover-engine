"""The opening line ("Hey guys! This is Ed Roh.") from one approved take, in every video.

Each video spoke its own opening, and every take sounded a little different: one in useRef v5 (2026-11-16) came out
5 semitones higher than the teacher's voice and was heard as "robotic", while useReducer's was right. A real
channel opens every video the same way. So the take the teacher approved is kept (backend/assets/voice:
opening.mp3, and opening.json with the voice and line it was made with and when each character is spoken), and
the scene that opens with that line speaks only the rest of its narration: the approved opening, a pause
(OPENING_PAUSE_SECONDS), then the rest. The rest is told the opening line was said before it, so it goes on from it.
"""

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from voiceover.providers.tts.base import SpokenTimes
from voiceover.utils import ffmpeg

# The two pieces meet with a fade this long on each side of the pause: no click.
FADE_SECONDS = 0.02


@dataclass
class Opening:
    audio: Path
    line: str  # the opening line as written ("Hey guys! This is Ed Roh.")
    spoken: str  # as the voice was given it, with the space after it ("... Ed Roe. ")
    starts: list[float]  # when each character of `spoken` is spoken
    seconds: float  # how long the audio is


def load(folder: Path, voice_id: str, line: str) -> Opening | None:
    """The approved opening in `folder`, when it was made with this voice and this opening line."""
    try:
        record = json.loads((folder / "opening.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    audio = folder / "opening.mp3"
    if record.get("voice_id") != voice_id or record.get("line", "").strip() != line.strip() or not audio.exists():
        return None
    return Opening(audio, record["line"], record["spoken"], record["character_starts"], float(record["seconds"]))


def rest_of(parts: list[str], line: str) -> list[str] | None:
    """The scene's spoken parts without the opening line, or None when the scene does not open with it."""
    if not parts or not line.strip() or not parts[0].startswith(line.strip()):
        return None
    first = parts[0][len(line.strip()):].lstrip()
    rest = ([first] if first else []) + parts[1:]
    return rest or None


def splice(opening: Opening, rest_audio: Path, rest: SpokenTimes | None, dst: Path, pause: float) -> SpokenTimes | None:
    """Write to dst the approved opening, `pause` seconds of quiet, then the rest; return when each character of
    the whole is spoken. The quiet is digital silence: the voice step fills it with room tone, as any pause."""
    graph = (
        f"[0:a]aresample=44100,afade=t=out:st={max(0.0, opening.seconds - FADE_SECONDS):.3f}:d={FADE_SECONDS},"
        f"apad=pad_dur={pause:.3f}[a];[1:a]aresample=44100,afade=t=in:d={FADE_SECONDS}[b];[a][b]concat=n=2:v=0:a=1[out]"
    )
    subprocess.run(
        [ffmpeg._binary("ffmpeg"), "-y", "-loglevel", "error", "-i", str(opening.audio), "-i", str(rest_audio),
         "-filter_complex", graph, "-map", "[out]", "-ac", "1", "-b:a", "128k", str(dst)],
        check=True, capture_output=True,
    )
    if rest is None:
        return None
    shift = opening.seconds + pause
    return SpokenTimes(opening.spoken + rest.text, [*opening.starts, *(round(start + shift, 3) for start in rest.starts)])
