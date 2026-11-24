"""Reads backend/config/voice.json: the voice types to choose from, and what each one is made of.

A voice type is chosen in Settings (or with VOICE_TYPE in .env). It decides three things together,
because they only work together: the style the voice speaks in, how the script's narration is
worded for it, and how firmly the leveler evens it out.
"""

from pathlib import Path

from pydantic import ValidationError

from voiceover.core.config import VOICE_CONFIG_FILE
from voiceover.core.constants import DEFAULT_VOICE_TYPE
from voiceover.core.exceptions import AppError
from voiceover.schemas.voice import LevelerConfig, VoiceConfig, VoiceStyle, VoiceType, VoiceTypeChoice


def load(path: Path = VOICE_CONFIG_FILE) -> VoiceConfig:
    """voice.json, checked. A broken file is explained."""
    try:
        config = VoiceConfig.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise AppError(f"{path.name} could not be read: {exc}") from exc
    except ValidationError as exc:
        problem = exc.errors()[0]
        where = ".".join(str(part) for part in problem["loc"])
        raise AppError(f"{path.name} is not valid ({where}: {problem['msg']}).") from exc
    for name, voice_type in config.types.items():
        if voice_type.style and voice_type.style not in config.styles:
            raise AppError(
                f'{path.name}: the voice type "{name}" uses the style "{voice_type.style}", which the file does not define. '
                f"It has: {', '.join(config.styles)}."
            )
    return config


def get(name: str = "", path: Path = VOICE_CONFIG_FILE) -> tuple[VoiceType, VoiceConfig]:
    """The voice type of that name (the default one when the name is empty), and the file it is from."""
    config = load(path)
    name = name or DEFAULT_VOICE_TYPE
    if name not in config.types:
        raise AppError(f'The voice type "{name}" is not in {path.name}. It has: {", ".join(config.types)}.')
    return config.types[name], config


def style(name: str = "", path: Path = VOICE_CONFIG_FILE) -> VoiceStyle | None:
    """How the voice of that type speaks. None: the settings stored with the voice."""
    voice_type, config = get(name, path)
    return config.styles[voice_type.style] if voice_type.style else None


def leveler(name: str = "", path: Path = VOICE_CONFIG_FILE) -> LevelerConfig:
    """The leveler's numbers for that type: its own feel on top of the shared ones."""
    voice_type, config = get(name, path)
    return LevelerConfig(**config.leveler.model_dump(), **voice_type.leveler.model_dump())


def narration(name: str = "", path: Path = VOICE_CONFIG_FILE) -> str:
    """How that type's narration is worded: "plain", "spoken" (for a voice that performs) or "teacher"."""
    return get(name, path)[0].narration


def spoken(name: str = "", path: Path = VOICE_CONFIG_FILE) -> bool:
    """True when that type's narration is written for a voice that performs."""
    return narration(name, path) == "spoken"


def choices(path: Path = VOICE_CONFIG_FILE) -> list[VoiceTypeChoice]:
    """The voice types, for the Settings page."""
    return [VoiceTypeChoice(id=name, label=voice_type.label, note=voice_type.note) for name, voice_type in load(path).types.items()]
