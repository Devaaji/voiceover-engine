"""SRT subtitle formatting."""

Cue = tuple[float, float, str]  # start, end, text


def format_timestamp(seconds: float) -> str:
    ms = max(0, round(seconds * 1000))
    hours, ms = divmod(ms, 3_600_000)
    minutes, ms = divmod(ms, 60_000)
    secs, ms = divmod(ms, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def spread_by_length(sentences: list[str], start: float, duration: float) -> list[Cue]:
    """Give each sentence a share of the duration proportional to its character count."""
    total = sum(len(s) for s in sentences)
    cues: list[Cue] = []
    cursor = start
    for sentence in sentences:
        end = cursor + duration * len(sentence) / total
        cues.append((cursor, end, sentence))
        cursor = end
    return cues


def build_srt(cues: list[Cue]) -> str:
    blocks = [
        f"{index}\n{format_timestamp(start)} --> {format_timestamp(end)}\n{text}\n"
        for index, (start, end, text) in enumerate(cues, start=1)
    ]
    return "\n".join(blocks)
