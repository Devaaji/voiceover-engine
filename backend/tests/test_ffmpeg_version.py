"""An FFmpeg too old for the pipeline's filters is refused before anything is spent."""

import pytest

from voiceover import ffmpeg_version
from voiceover.core.exceptions import AppError


def test_versions_are_read_from_every_kind_of_build() -> None:
    assert ffmpeg_version.parse("ffmpeg version 9.0.2-full_build-www.gyan.dev Copyright (c) 2000-2026") == (9, 0, 2)
    assert ffmpeg_version.parse("ffmpeg version n9.0-latest-linux64-gpl-9.0 Copyright") == (9, 0, 0)
    assert ffmpeg_version.parse("ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023") == (6, 1, 1)
    assert ffmpeg_version.parse("ffmpeg version N-118000-g1234abcd Copyright") is None


def test_an_old_ffmpeg_is_refused_and_a_new_one_is_not() -> None:
    with pytest.raises(AppError, match="FFmpeg 6.1.1 is installed"):
        ffmpeg_version.check("ffmpeg version 6.1.1-3ubuntu5 Copyright (c) 2000-2023")
    ffmpeg_version.check("ffmpeg version 9.0.2-full_build-www.gyan.dev")
    ffmpeg_version.check("ffmpeg version 9.1 Copyright")
    ffmpeg_version.check("ffmpeg version N-118000-g1234abcd Copyright")  # a git build: let through


def test_this_machines_ffmpeg_is_new_enough() -> None:
    ffmpeg_version.check()
