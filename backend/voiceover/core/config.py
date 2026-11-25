"""Settings from the environment (.env at the project root, see .env.example) and where the engine's files are.

The names the copied pipeline imports (VOICE_CONFIG_FILE, APPROVED_OPENING, PAUSE_RHYTHM, ...) are the same as in
backend/app/core/config.py of the Video Automation repo; the .env keys are this engine's own.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

from voiceover.core.constants import DEFAULT_ANTHROPIC_EFFORT, DEFAULT_ANTHROPIC_MODEL, DEFAULT_MAX_JOB_COST_USD, DEFAULT_VOICE_TYPE

BACKEND_DIR = Path(__file__).resolve().parents[2]
ROOT_DIR = BACKEND_DIR.parent

load_dotenv(ROOT_DIR / ".env")


def _env(name: str) -> str:
    return os.getenv(name, "").strip()


def _on(name: str) -> bool:
    return _env(name).lower() != "off"


def resolve_path(path: str) -> Path:
    """Relative paths in .env are relative to the project root."""
    p = Path(path).expanduser()
    return (p if p.is_absolute() else ROOT_DIR / p).resolve()


# --- files ---

DATA_DIR = resolve_path(_env("DATA_DIR") or "data")
JOBS_DIR = DATA_DIR / "jobs"
CONFIG_DIR = ROOT_DIR / "config"
PROMPTS_DIR = ROOT_DIR / "prompts"
# The voice types to choose from: how each speaks, how its script is worded, how it is levelled.
VOICE_CONFIG_FILE = CONFIG_DIR / "voice.json"
# Written term -> how the voice should say it.
PRONUNCIATIONS_FILE = CONFIG_DIR / "pronunciations.json"
# The teacher's own words: every .md or .txt file in a subfolder named after the narration (teacher/).
STYLE_EXAMPLES_DIR = PROMPTS_DIR / "style_examples"
# The pass that puts a script's narration in the teacher's way of talking (services/narration_style.py).
STYLE_PROMPT_FILE = PROMPTS_DIR / "narration_style_system.md"
# The lesson plan, written before the narration (mode "content").
PLAN_PROMPT_FILE = PROMPTS_DIR / "plan_system.md"
# The approved take of the opening line (services/approved_opening.py).
APPROVED_OPENING_DIR = ROOT_DIR / "assets" / "voice"

# --- the voice ---

# The voice the engine was tuned with (the teacher's own clone, "edroh-pro"). It must belong to the ElevenLabs
# account of ELEVENLABS_API_KEY.
DEFAULT_ELEVENLABS_VOICE_ID = "rExOvxZPbTNhO480h6cK"
# "elevenlabs", or "mock" for silent audio of a realistic length (tests without credits).
TTS_PROVIDER = _env("TTS_PROVIDER").lower() or "elevenlabs"
ELEVENLABS_API_KEY = _env("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = _env("ELEVENLABS_VOICE_ID") or DEFAULT_ELEVENLABS_VOICE_ID
# Empty: the API's default, eleven_multilingual_v2.
ELEVENLABS_MODEL_ID = _env("ELEVENLABS_MODEL_ID")
# How the voice is made: a voice type from config/voice.json.
VOICE_TYPE = _env("VOICE_TYPE") or DEFAULT_VOICE_TYPE
# The leveler brings every phrase and every segment of the voice to one loudness. On unless "off".
VOICE_LEVELER = _on("VOICE_LEVELER")
# The pause after each sentence of an explanation (services/holds.py): human = as long as the sentence carried,
# short and long like a person talks; even = 2.2 s after every one, as before 2026-11-22.
PAUSE_RHYTHM = _env("PAUSE_RHYTHM").lower() or "human"

# --- the opening line (off unless a request asks for it) ---

# The line a request with "opening": true opens with. A request may send its own "openingLine".
OPENING_LINE = _env("OPENING_LINE") or "Hey guys! This is Ed Roh."
# The approved take of the opening line, used when its voice and line match. On unless "off".
APPROVED_OPENING = _on("APPROVED_OPENING")
# The quiet after the opening line, before the rest of the first segment, in seconds.
OPENING_PAUSE_SECONDS = float(_env("OPENING_PAUSE_SECONDS") or 1.0)

# --- Claude (the narration) ---

ANTHROPIC_API_KEY = _env("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = _env("ANTHROPIC_MODEL") or DEFAULT_ANTHROPIC_MODEL
ANTHROPIC_EFFORT = _env("ANTHROPIC_EFFORT").lower() or DEFAULT_ANTHROPIC_EFFORT
# A key that is not tied to one workspace must name the workspace on every request.
ANTHROPIC_WORKSPACE_ID = _env("ANTHROPIC_WORKSPACE_ID")
# The most a job may spend on Claude, in US dollars.
COST_LIMIT_USD = float(_env("COST_LIMIT_USD") or DEFAULT_MAX_JOB_COST_USD)

# --- the API ---

# Every request must send it as the X-API-Key header. The API refuses every request while it is not set.
API_KEY = _env("API_KEY")
# The sites that may call the API from a browser, comma separated (the test page calls it from its own server).
CORS_ORIGINS = [origin.strip().rstrip("/") for origin in (_env("CORS_ORIGINS") or "http://localhost:3000").split(",") if origin.strip()]
# FastAPI's /docs and /openapi.json, which need no key: on only when "on" (local development).
API_DOCS = _env("API_DOCS").lower() == "on"
# How many jobs make their voice at the same time.
MAX_CONCURRENT_JOBS = max(1, int(_env("MAX_CONCURRENT_JOBS") or 1))
