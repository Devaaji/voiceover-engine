"""The audio is the same as the Video Automation repo made it, to the byte.

Each fixture is a scene of a finished job of the old repo (tests/golden/build_fixtures.py): the voice ElevenLabs
returned, and the SHA-256 of what the old pipeline made from it. Here the same voice goes through this engine, with
no call to ElevenLabs: the holds and room tone (pipeline/voice.py), then the levelling and the padding
(pipeline/assemble.py). The holds' places and the levelling's measurements must be equal; the audio files must be
byte-identical when FFmpeg is the build the fixtures were made with (the bytes of an encoder can change between
builds; the numbers do not).
"""

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from voiceover.core.paths import JobPaths
from voiceover.pipeline import assemble, voice
from voiceover.pipeline.context import StepContext
from voiceover.providers.tts.base import SpokenTimes
from voiceover.schemas.settings import VoiceChoice
from voiceover.segments import Segment
from voiceover.services import pronunciation_service

FIXTURES = Path(__file__).parent / "fixtures"
CASES = sorted(folder.name for folder in FIXTURES.iterdir() if (folder / "expected.json").exists())


def sha256(file: Path) -> str:
    return hashlib.sha256(file.read_bytes()).hexdigest()


def ffmpeg_version() -> str:
    return subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]


def made(scene_id: str, tmp_path: Path) -> tuple[dict, JobPaths, StepContext, Segment, Path]:
    """The scene's audio with its holds, made by this engine from the old voice."""
    fixture = FIXTURES / scene_id
    expected = json.loads((fixture / "expected.json").read_text(encoding="utf-8"))
    paths = JobPaths("golden", base=tmp_path)
    paths.ensure()
    shutil.copyfile(fixture / "voice.mp3", paths.voice_dir / f"{scene_id}.mp3")
    shutil.copyfile(fixture / "voice.json", paths.voice_times(scene_id))
    segment = Segment(**expected["segment"])
    ctx = StepContext(
        job_id="golden",
        paths=paths,
        segments=[segment],
        voice=VoiceChoice(tts_provider="mock", voice_type="teacher"),
        terms=pronunciation_service.load(),
    )
    saved = json.loads((fixture / "voice.json").read_text(encoding="utf-8"))
    voiced = SpokenTimes(saved["spoken"], saved["character_starts"])
    audio, _ = voice._held(ctx, segment, paths.voice(scene_id), voiced, ctx.terms, (None, None))
    return expected, paths, ctx, segment, audio


@pytest.mark.parametrize("scene_id", CASES)
def test_holds_and_room_tone_are_where_the_old_pipeline_put_them(scene_id: str, tmp_path: Path) -> None:
    expected, paths, _, _, audio = made(scene_id, tmp_path)
    record = json.loads(paths.held(scene_id).read_text(encoding="utf-8"))
    for key in ("cuts", "room_tone", "quiet_ends", "spoken", "character_starts"):
        assert record[key] == expected["held"][key], key
    assert audio.name == expected["audio_name"]


@pytest.mark.parametrize("scene_id", CASES)
def test_finished_audio_is_byte_identical(scene_id: str, tmp_path: Path) -> None:
    expected, paths, ctx, segment, audio = made(scene_id, tmp_path)
    kept = assemble.finish(ctx, segment, expected["clip_seconds"], assemble.leveler_for(ctx))
    for key in ("measured_lufs", "gain_db", "swing_db"):
        assert kept[key] == expected["levelled"][key], key
    if ffmpeg_version() != expected["ffmpeg"]:
        pytest.skip(f"FFmpeg is not the build of the fixtures ({expected['ffmpeg']}): only the numbers are compared")
    assert sha256(audio) == expected["audio_sha256"]
    assert sha256(paths.merged(scene_id)) == expected["merged_sha256"]
