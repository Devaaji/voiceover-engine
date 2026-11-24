"""Every path inside a job folder, in one place.

voiceover-engine: the per-segment paths of the audio (voice, holds, room tone, finished audio) are the same as in
backend/app/core/paths.py of the Video Automation repo, so the copied code finds its files where it always did. A
voiceover has no video, code or diagrams; its output is audio and a transcript.
"""

from dataclasses import dataclass
from pathlib import Path

from voiceover.core.config import JOBS_DIR


@dataclass(frozen=True)
class JobPaths:
    job_id: str
    base: Path | None = None  # another jobs folder (tests); JOBS_DIR when None

    @property
    def root(self) -> Path:
        return (self.base or JOBS_DIR) / self.job_id

    @property
    def job_file(self) -> Path:
        return self.root / "job.json"

    @property
    def input_dir(self) -> Path:
        return self.root / "input"

    @property
    def request(self) -> Path:
        """The request as it came in (without secrets)."""
        return self.input_dir / "request.json"

    @property
    def segments(self) -> Path:
        """The segments the voice speaks, after the script was cut and the narration written."""
        return self.input_dir / "segments.json"

    @property
    def llm_dir(self) -> Path:
        """What was sent to Claude and what came back."""
        return self.root / "work" / "llm"

    # work/
    @property
    def audio_dir(self) -> Path:
        return self.root / "work" / "audio"

    @property
    def voice_dir(self) -> Path:
        return self.root / "work" / "voice"

    @property
    def merged_dir(self) -> Path:
        return self.root / "work" / "merged"

    # output/
    @property
    def output_dir(self) -> Path:
        return self.root / "output"

    def output(self, name: str) -> Path:
        return self.output_dir / name

    # per segment (a "scene" in the copied code)
    def audio(self, scene_id: str) -> Path | None:
        """The segment's audio file, whatever its extension (wav or mp3)."""
        return next(iter(sorted(self.audio_dir.glob(f"{scene_id}.*"))), None)

    def voice(self, scene_id: str) -> Path | None:
        """The segment's voice as the provider made it, without holds. work/audio has it with them."""
        found = [path for path in sorted(self.voice_dir.glob(f"{scene_id}.*")) if path.suffix != ".json"]
        return found[0] if found else None

    def voice_times(self, scene_id: str) -> Path:
        """When each character of the segment's voice is spoken, before the holds: what the voice said."""
        return self.voice_dir / f"{scene_id}.json"

    def held(self, scene_id: str) -> Path:
        """Which holds the segment's audio in work/audio was made with, so it is made again when they change."""
        return self.voice_dir / f"{scene_id}.held.json"

    def room_tone(self, scene_id: str) -> Path:
        """A piece of the quiet between the voice's own words, made to loop: what fills its holds and its end."""
        return self.root / "work" / "tone" / f"{scene_id}.wav"

    def merged(self, scene_id: str) -> Path:
        """The segment's finished audio (levelled, its end filled with room tone), to the sample. The voiceover's
        audio is joined from these, uncompressed."""
        return self.merged_dir / f"{scene_id}.wav"

    def levelled(self, scene_id: str) -> Path:
        """What the segment's finished audio was levelled with, and what was measured in it."""
        return self.merged_dir / f"{scene_id}.level.json"

    def ensure(self) -> None:
        for folder in (self.input_dir, self.audio_dir, self.voice_dir, self.merged_dir, self.output_dir):
            folder.mkdir(parents=True, exist_ok=True)
