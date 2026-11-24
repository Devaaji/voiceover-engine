"""Small text helpers."""

import re


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [part for part in parts if part]


def to_lf(text: str) -> str:
    """Windows (CRLF) and old Mac (CR) line endings as plain LF, the one the editor and the checks use."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def count_words(text: str) -> int:
    return len(text.split())


def apply_pronunciations(text: str, pronunciations: dict[str, str]) -> str:
    """Replace written terms with how they should be spoken ("npx" -> "N P X").

    Whole words only and case sensitive. Longer terms win over shorter ones,
    and text that was already replaced is not matched again.
    """
    terms = sorted((term for term in pronunciations if term), key=len, reverse=True)
    if not terms:
        return text
    pattern = r"(?<!\w)(?:" + "|".join(re.escape(term) for term in terms) + r")(?!\w)"
    return re.sub(pattern, lambda match: pronunciations[match.group(0)], text)


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def with_opening(narration: str, opening: str) -> str:
    """The narration, starting with the opening line. Unchanged if it already does
    (compared by words only, so punctuation and capitals don't matter)."""
    opening = opening.strip()
    if not opening:
        return narration
    words = _words(opening)
    if _words(narration)[: len(words)] == words:
        return narration
    if opening[-1] not in ".!?":
        opening += "."
    return f"{opening} {narration.lstrip()}"


def slugify(text: str, fallback: str = "job") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:40].strip("-") or fallback
