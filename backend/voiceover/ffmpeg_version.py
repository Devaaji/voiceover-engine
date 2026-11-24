"""Which FFmpeg is installed, and whether it makes the audio right. New in voiceover-engine.

The pipeline's filters were made and approved with FFmpeg 9.0.2 (the golden tests' build). FFmpeg 6.1, Ubuntu 24.04's
own, cuts the audio short where a pause is filled with room tone: a 10 s segment came out 1.7 s long (2026-11-24). So
a job refuses an FFmpeg older than MIN_MAJOR instead of making broken audio.
"""

import re
import subprocess

from voiceover.core.exceptions import AppError

MIN_MAJOR = 9
# "ffmpeg version 9.0.2-full_build-www.gyan.dev", "ffmpeg version n9.0-...", "ffmpeg version 6.1.1-3ubuntu5".
VERSION = re.compile(r"ffmpeg version n?(\d+)\.(\d+)(?:\.(\d+))?")


def parse(first_line: str) -> tuple[int, int, int] | None:
    """(major, minor, patch) from `ffmpeg -version`'s first line, or None for a build that does not say (git builds)."""
    match = VERSION.search(first_line)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3) or 0)


def first_line() -> str:
    try:
        out = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, encoding="utf-8", errors="replace", check=True).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise AppError(f"FFmpeg could not be run: {error}. Install FFmpeg {MIN_MAJOR} or newer.") from error
    return out.splitlines()[0] if out else ""


def check(line: str | None = None) -> None:
    """Raise AppError when FFmpeg is older than MIN_MAJOR. A build that does not tell its version is let through."""
    line = first_line() if line is None else line
    version = parse(line)
    if version is not None and version[0] < MIN_MAJOR:
        found = ".".join(str(part) for part in version)
        raise AppError(
            f"FFmpeg {found} is installed, and this engine needs FFmpeg {MIN_MAJOR} or newer: older versions cut the "
            "audio short where a pause is filled. Upgrade it (macOS: brew upgrade ffmpeg), or use the Docker image."
        )
