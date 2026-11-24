"""The opening line ("Hey guys! This is Ed Roh.") is the same in every video, and the first thing the viewer hears.

Now and then a take draws one of its words out and pauses after it, as if the phrase ended there
("Eddd... Roh"): the model reads that word as the end of a phrase. Such a take is spoken again.

A word's length comes from the times the voice gives for its characters: from the word's first
character to the next word's, against how long the scene's other words take per character. A word
before punctuation is left out, since a pause there is meant. Measured on 2026-11-15 over 18
openings of edroh-pro: in the 16 good ones no word of the line took more than 1.7 times its share,
in the two drawn-out ones "Ed" took 3.0 and 3.8 times.
"""

import re
from statistics import median

# A word of the opening line that takes more than this many times its share of time is drawn out.
STRETCH_LIMIT = 2.5
# The first take and at most two more. A take of the opening scene costs about 150 credits.
TAKES = 3
# A pause after a word or before the next one is meant when punctuation stands there.
PUNCTUATION = re.compile(r"[.,!?;:—–…\"'()\[\]-]")
WORD = re.compile(r"\S+")
# Fewer words than this do not give a pace to measure against.
MIN_WORDS = 5


def opening_words(narration: str, signature: str) -> int:
    """How many words of the narration are the opening line: 0 when the narration does not open with it."""
    line = signature.strip()
    return len(line.split()) if line and narration.strip().startswith(line) else 0


def _timed_words(spoken: str, starts: list[float]) -> list[tuple[int, str, float, int]]:
    """Each word not next to punctuation: (its place among the words, the word, its time to the next word,
    its characters with the space after it)."""
    found = list(WORD.finditer(spoken))
    rows = []
    for place, (word, following) in enumerate(zip(found, found[1:])):
        if PUNCTUATION.search(word.group()[-1]) or PUNCTUATION.match(following.group()):
            continue
        rows.append((place, word.group(), starts[following.start()] - starts[word.start()], following.start() - word.start()))
    return rows


def stretch(spoken: str, starts: list[float], words: int) -> dict[str, float]:
    """How many times its share of time each of the first `words` words takes. Empty when the times cannot tell."""
    if len(starts) < len(spoken):
        return {}
    rows = _timed_words(spoken, starts)
    if len(rows) < MIN_WORDS:
        return {}
    pace = median(seconds / chars for _, _, seconds, chars in rows)
    if pace <= 0:
        return {}
    return {word: round(seconds / (chars * pace), 1) for place, word, seconds, chars in rows if place < words}


def drawn_out(spoken: str, starts: list[float], words: int) -> dict[str, float]:
    """The words of the opening line that take more than STRETCH_LIMIT times their share of time."""
    return {word: times for word, times in stretch(spoken, starts, words).items() if times > STRETCH_LIMIT}


def worst(spoken: str, starts: list[float], words: int) -> float:
    """How many times its share the slowest word of the opening line takes: the take with the lowest is kept."""
    return max(stretch(spoken, starts, words).values(), default=0.0)
