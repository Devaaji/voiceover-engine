"""Step 3: the transcript with its times: transcript.json, subtitles.srt and subtitles.vtt.

voiceover-engine: from backend/app/pipeline/steps/subtitles.py of the Video Automation repo (2026-11-23). A sentence
starts when the voice says its first word (holds included), from the times ElevenLabs gives for every character;
without them, the sentences are spread over the segment by their length, as before. New here: the WebVTT file, and
transcript.json with each segment, sentence and word and its start and end.

A word's time comes from the characters of its spoken form (after the pronunciation list): "useState" is said as
"use state", and starts where "use" does. A sentence whose spoken words cannot be followed gets its words spread by
their length, marked "estimated".
"""

import json

from voiceover.core.constants import SCENE_PADDING
from voiceover.core.exceptions import StepFailed
from voiceover.pipeline.context import StepContext
from voiceover.providers.tts.base import SpokenTimes
from voiceover.services import holds
from voiceover.utils import ffmpeg, srt
from voiceover.utils.text import apply_pronunciations, split_sentences

# A cue is shown at least this long.
MIN_CUE_SECONDS = 0.3


def _timed_cues(sentences: list[str], starts: list[float], scene_start: float, spoken: float) -> list[srt.Cue]:
    cues = []
    for index, sentence in enumerate(sentences):
        start = scene_start + starts[index]
        end = scene_start + (starts[index + 1] if index + 1 < len(sentences) else spoken)
        cues.append((start, max(end, start + MIN_CUE_SECONDS), sentence))
    return cues


def _word_times(sentence: str, start: float, end: float, times: SpokenTimes | None, terms: dict[str, str], at: int) -> tuple[list[dict], int, bool]:
    """Each word of the sentence with its start and end, the place in the spoken text after the sentence, and whether
    the times are estimated. `at` is where the sentence's spoken form starts in the spoken text (in characters)."""
    words = sentence.split()
    text = times.text if times is not None else ""
    found: list[tuple[str, float]] = []
    exact = times is not None and len(times.starts) == len(text)
    cursor = at
    if exact:
        for word in words:
            spoken = apply_pronunciations(word, terms)
            while cursor < len(text) and text[cursor] == " ":
                cursor += 1
            if not text.startswith(spoken, cursor):
                exact = False
                break
            found.append((word, float(times.starts[cursor])))
            cursor += len(spoken)
    if not exact:
        total = sum(len(word) for word in words) or 1
        found, before = [], 0
        for word in words:
            found.append((word, start + (end - start) * before / total))
            before += len(word)
        cursor = at
    result = []
    for index, (word, word_start) in enumerate(found):
        word_end = found[index + 1][1] if index + 1 < len(found) else end
        result.append({"text": word, "start": round(word_start, 3), "end": round(max(word_end, word_start), 3)})
    return result, cursor, not exact


def run(ctx: StepContext) -> dict:
    """Write the transcript files to output/. Returns transcript.json's content."""
    terms = ctx.terms
    cues: list[srt.Cue] = []
    segments: list[dict] = []
    scene_start = 0.0

    for scene in ctx.segments:
        audio = ctx.paths.audio(scene.id)
        if audio is None:
            raise StepFailed(f"Segment {scene.id} has no audio. Make the voice first.")
        spoken = ffmpeg.probe_duration(audio)
        # The segment's real length in the voiceover, when it has been finished.
        merged = ctx.paths.merged(scene.id)
        length = ffmpeg.probe_duration(merged) if merged.exists() else spoken + SCENE_PADDING

        sentences = split_sentences(scene.narration)
        times = holds.audio_times(ctx.paths, scene)
        spoken_sentences = [apply_pronunciations(sentence, terms) for sentence in sentences]
        starts = times.part_starts(spoken_sentences) if times and sentences else None
        if sentences and starts is not None:
            scene_cues = _timed_cues(sentences, starts, scene_start, spoken)
        elif sentences:
            scene_cues = srt.spread_by_length(sentences, scene_start, spoken)
        else:
            scene_cues = []
        cues += scene_cues

        shifted = SpokenTimes(times.text, [scene_start + start for start in times.starts]) if times and starts is not None else None
        at = 0
        timed_sentences = []
        for sentence, (start, end, _) in zip(sentences, scene_cues):
            if shifted is not None:
                while at < len(shifted.text) and shifted.text[at] == " ":
                    at += 1
            words, after, estimated = _word_times(sentence, start, end, shifted, terms, at)
            at = after if not estimated else at + len(apply_pronunciations(sentence, terms))
            item = {"text": sentence, "start": round(start, 3), "end": round(end, 3), "words": words}
            if estimated:
                item["estimated"] = True
            timed_sentences.append(item)
        segments.append(
            {
                "id": scene.id,
                "kind": scene.kind,
                "text": scene.narration,
                "start": round(scene_start, 3),
                "end": round(scene_start + length, 3),
                "sentences": timed_sentences,
            }
        )
        scene_start += length

    ctx.paths.output("subtitles.srt").write_text(srt.build_srt(cues), encoding="utf-8")
    ctx.paths.output("subtitles.vtt").write_text(build_vtt(cues), encoding="utf-8")
    transcript = {
        "text": " ".join(scene.narration for scene in ctx.segments),
        "duration": round(scene_start, 3),
        "segments": segments,
    }
    ctx.paths.output("transcript.json").write_text(json.dumps(transcript, indent=2, ensure_ascii=False), encoding="utf-8")
    ctx.progress(f"{len(cues)} lines")
    return transcript


def _vtt_timestamp(seconds: float) -> str:
    return srt.format_timestamp(seconds).replace(",", ".")


def build_vtt(cues: list[srt.Cue]) -> str:
    blocks = [f"{_vtt_timestamp(start)} --> {_vtt_timestamp(end)}\n{text}\n" for start, end, text in cues]
    return "WEBVTT\n\n" + "\n".join(blocks)
