"""Build the golden fixtures from a finished job of the Video Automation repo. The old job is only read.

For each scene: the voice ElevenLabs made (work/voice/<id>.mp3) and when its characters are spoken (<id>.json), the
scene's narration and holds, and what the old pipeline made from that voice: the audio with its holds (work/audio),
the finished audio (work/merged), as SHA-256, and what it measured. The golden test makes the same files from the
same voice with this engine, and they must be byte-identical (with the same FFmpeg build).

Usage, from backend/:
    python tests/golden/build_fixtures.py <old job folder> s01 s02 ...
"""

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
KINDS = {"points": "explain", "section": "section", "title": "plain"}


def sha256(file: Path) -> str:
    return hashlib.sha256(file.read_bytes()).hexdigest()


def probe(file: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(file)],
        capture_output=True, text=True, check=True,
    ).stdout
    return float(out.strip())


def ffmpeg_version() -> str:
    return subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]


def main(job: Path, ids: list[str]) -> None:
    script = json.loads((job / "input" / "script.json").read_text(encoding="utf-8"))
    scenes = {scene["id"]: scene for scene in script["scenes"]}
    for scene_id in ids:
        scene = scenes[scene_id]
        if scene["type"] not in KINDS:
            raise SystemExit(f"{scene_id} is a {scene['type']} scene: only title, points and section scenes have a kind.")
        held = json.loads((job / "work" / "voice" / f"{scene_id}.held.json").read_text(encoding="utf-8"))
        if not isinstance(held.get("room_tone"), list):
            raise SystemExit(f"{scene_id} borrowed its room tone ({held.get('room_tone')}): pick a scene with its own.")
        audio = next((job / "work" / "audio").glob(f"{scene_id}.*"))
        merged = job / "work" / "merged" / f"{scene_id}.wav"
        target = FIXTURES / scene_id
        target.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(job / "work" / "voice" / f"{scene_id}.mp3", target / "voice.mp3")
        shutil.copyfile(job / "work" / "voice" / f"{scene_id}.json", target / "voice.json")
        expected = {
            "source": f"{job.name} {scene_id}",
            "ffmpeg": ffmpeg_version(),
            "segment": {
                "id": scene_id,
                "kind": KINDS[scene["type"]],
                "narration": scene["narration"],
                "holds": scene.get("holds") or [],
            },
            "audio_name": audio.name,
            "audio_sha256": sha256(audio),
            "held": {key: held.get(key) for key in ("cuts", "room_tone", "quiet_ends", "seconds", "spoken", "character_starts")},
            # The old scene lasted as long as its clip: its audio plus the padding, as the video's frames allowed.
            "clip_seconds": probe(job / "work" / "video" / f"{scene_id}.mp4"),
            "merged_sha256": sha256(merged),
            "levelled": json.loads((job / "work" / "merged" / f"{scene_id}.level.json").read_text(encoding="utf-8")),
        }
        (target / "expected.json").write_text(json.dumps(expected, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"{scene_id}: {scene['type']} -> {KINDS[scene['type']]}, {len(held.get('cuts') or [])} cuts")


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2:])
