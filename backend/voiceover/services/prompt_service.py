"""The teacher's narration examples (backend/app/services/prompt_service.py of the Video Automation repo).

voiceover-engine: only style_examples() is copied, word for word; the rest of that file builds the video script's
prompt.
"""

from pathlib import Path

from voiceover.core.config import STYLE_EXAMPLES_DIR

EXAMPLE_TYPES = (".md", ".txt")


def style_examples(folder: Path = STYLE_EXAMPLES_DIR) -> list[tuple[str, str]]:
    """(file name, text) of every .md or .txt file in the folder, in name order. Empty files are skipped."""
    if not folder.is_dir():
        return []
    examples = []
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix.lower() in EXAMPLE_TYPES:
            text = path.read_text(encoding="utf-8").strip()
            if text:
                examples.append((path.name, text))
    return examples
