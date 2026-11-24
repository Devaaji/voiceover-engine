"""Every endpoint needs the X-API-Key header, equal to API_KEY in .env: the API spends ElevenLabs and Anthropic
credits, so nobody who only knows its URL may use it."""

import secrets

from fastapi import Header, HTTPException, status

from voiceover.core import config


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if not config.API_KEY:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "API_KEY is not set on the server, so every request is refused.")
    if not x_api_key or not secrets.compare_digest(x_api_key.encode("utf-8"), config.API_KEY.encode("utf-8")):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Send the API key in the X-API-Key header.")
