"""Reads config/pronunciations.json: written term -> how it should be spoken.

The list only changes the text sent to the voice provider. The transcript keeps the original text.

voiceover-engine: from backend/app/services/pronunciation_service.py of the Video Automation repo. The list is read
from config/ (a copy of the teacher's list, 152 terms on 2026-11-23) and never written; a request can add terms of
its own.
"""

from voiceover.core.config import PRONUNCIATIONS_FILE
from voiceover.utils.files import read_json


def load(extra: dict[str, str] | None = None) -> dict[str, str]:
    terms = read_json(PRONUNCIATIONS_FILE) if PRONUNCIATIONS_FILE.exists() else {}
    added = {written.strip(): spoken.strip() for written, spoken in (extra or {}).items() if written.strip() and spoken.strip()}
    return {**terms, **added}
