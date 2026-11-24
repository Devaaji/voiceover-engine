"""ElevenLabs text to speech.

API reference: https://elevenlabs.io/docs/api-reference/text-to-speech/convert
With the time of every character: .../text-to-speech/convert-with-timestamps
"""

import base64
import logging
from pathlib import Path

import httpx

from voiceover.core.exceptions import ProviderUnavailable
from voiceover.providers.tts.base import Context, SpokenTimes, TTSProvider
from voiceover.schemas.settings import Voice

API_URL = "https://api.elevenlabs.io"
# The API's own default when no model_id is sent.
DEFAULT_MODEL_ID = "eleven_multilingual_v2"
# The best MP3 the Creator plan gives, at the same credits as 128 kb/s: the voice comes back very quiet
# (about -42 LUFS, as the clone's training audio is) and is raised about 27 dB, so less coding noise
# under it is worth having. A plan that does not allow it gets FALLBACK_FORMAT instead.
OUTPUT_FORMAT = "mp3_44100_192"
FALLBACK_FORMAT = "mp3_44100_128"

log = logging.getLogger(__name__)


def _check(response: httpx.Response) -> None:
    if response.status_code != 200:
        raise ProviderUnavailable(
            f"ElevenLabs returned {response.status_code}: {response.text[:300]}"
        )


class ElevenLabsTTS(TTSProvider):
    extension = "mp3"

    def __init__(self, api_key: str, voice_id: str, model_id: str, voice_settings: dict | None = None) -> None:
        if not api_key:
            raise ProviderUnavailable("ElevenLabs needs an API key. Add one in Settings.")
        if not voice_id:
            raise ProviderUnavailable("ElevenLabs needs a voice. Pick one in Settings.")
        self._api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id or DEFAULT_MODEL_ID
        # How the voice speaks (stability, style, speed). None: the settings stored with the voice.
        self.voice_settings = voice_settings
        self.credits = 0
        self.output_format = OUTPUT_FORMAT

    def _request(self, text: str, context: Context | None = None) -> dict:
        request = {"text": text, "model_id": self.model_id}
        if self.voice_settings:
            request["voice_settings"] = self.voice_settings
        # Request stitching: what is said around the text, so its first and last sentences are
        # spoken as part of a talk and not as a talk of their own. Not spoken, and not charged
        # (the character-cost header is the same with and without it, measured 2026-11-12).
        if context is not None and context.before:
            request["previous_text"] = context.before
        if context is not None and context.after:
            request["next_text"] = context.after
        return request

    def _post(self, url: str, request: dict) -> httpx.Response:
        """A request in the best format the plan allows: OUTPUT_FORMAT, or FALLBACK_FORMAT when the plan
        refuses it (remembered, so the next request asks for the one that works)."""
        response = httpx.post(url, params={"output_format": self.output_format}, headers={"xi-api-key": self._api_key}, json=request, timeout=120)
        if response.status_code in (400, 401, 402, 403, 422) and "output_format" in response.text and self.output_format != FALLBACK_FORMAT:
            log.warning("ElevenLabs refused %s on this plan; using %s", self.output_format, FALLBACK_FORMAT)
            self.output_format = FALLBACK_FORMAT
            return self._post(url, request)
        return response

    def synthesize(self, text: str, out_path: Path) -> None:
        response = self._post(f"{API_URL}/v1/text-to-speech/{self.voice_id}", self._request(text))
        _check(response)
        self.credits += _log_cost(response, text)
        out_path.write_bytes(response.content)

    def synthesize_parts(self, parts: list[str], out_path: Path, context: Context | None = None) -> SpokenTimes | None:
        """One request for the whole text, which also returns when every character is spoken."""
        text = " ".join(parts)
        response = self._post(f"{API_URL}/v1/text-to-speech/{self.voice_id}/with-timestamps", self._request(text, context))
        _check(response)
        self.credits += _log_cost(response, text)
        data = response.json()
        out_path.write_bytes(base64.b64decode(data["audio_base64"]))
        return spoken_times(text, data.get("alignment"))


def spoken_times(text: str, alignment: dict | None) -> SpokenTimes | None:
    """The time of every character of the text, as the API returned it.

    None when the times don't cover the text character by character, so they can't be trusted.
    """
    times = (alignment or {}).get("character_start_times_seconds") or []
    return SpokenTimes(text, [float(time) for time in times]) if text and len(times) == len(text) else None


def part_starts(parts: list[str], alignment: dict | None) -> list[float] | None:
    """When each part starts, from the times of the characters of the parts joined with spaces."""
    timed = spoken_times(" ".join(parts), alignment)
    return timed.part_starts(parts) if timed else None


def _log_cost(response: httpx.Response, text: str) -> int:
    """What the request cost in credits, as ElevenLabs reports it. Logged next to the length of the text."""
    cost = response.headers.get("character-cost")
    if cost is None:
        return 0
    endpoint = "with-timestamps" if response.url.path.endswith("with-timestamps") else "convert"
    log.info("ElevenLabs %s: %d characters sent, character-cost %s", endpoint, len(text), cost)
    return int(cost) if cost.isdigit() else 0


def list_voices(api_key: str) -> list[Voice]:
    voices: list[Voice] = []
    params: dict[str, str | int] = {"page_size": 100}
    while True:
        response = httpx.get(
            f"{API_URL}/v2/voices", params=params, headers={"xi-api-key": api_key}, timeout=30
        )
        _check(response)
        page = response.json()
        voices += [
            Voice(
                voice_id=voice["voice_id"],
                name=voice.get("name") or voice["voice_id"],
                category=voice.get("category") or "",
                preview_url=voice.get("preview_url"),
            )
            for voice in page["voices"]
        ]
        if not page.get("has_more") or not page.get("next_page_token"):
            return voices
        params["next_page_token"] = page["next_page_token"]
