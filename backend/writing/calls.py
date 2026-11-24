"""What the Claude calls of a job cost, and whether one more would go over its limit.

From backend/app/services/generation_service.py of the Video Automation repo (_cost, _record_call, over_cost_limit),
working on a job's own list of calls.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

from voiceover.core.config import CONFIG_DIR
from voiceover.providers.script.writer import LLMResponse
from voiceover.utils.files import read_json

log = logging.getLogger(__name__)

LLM_PRICES_FILE = CONFIG_DIR / "llm_prices.json"


def cost(response: LLMResponse) -> float | None:
    """Estimated cost in US dollars, from the per-million-token prices in the config."""
    price = read_json(LLM_PRICES_FILE).get(response.model)
    if not isinstance(price, dict):
        return None
    cache_read = price.get("cache_read", price["input"] * 0.1)
    cache_write = price.get("cache_write", price["input"] * 1.25)
    total = (
        response.input_tokens * price["input"]
        + response.output_tokens * price["output"]
        + response.cache_read_tokens * cache_read
        + response.cache_write_tokens * cache_write
    )
    return round(total / 1_000_000, 4)


def record(calls: list[dict], llm_dir: Path, response: LLMResponse, purpose: str, job_id: str) -> dict:
    """Add a call to the job's list, and keep the API's answer in work/llm. Returns the call."""
    call = {
        "purpose": purpose,
        "model": response.model,
        "input_tokens": response.input_tokens,
        "output_tokens": response.output_tokens,
        "cache_read_tokens": response.cache_read_tokens,
        "cache_write_tokens": response.cache_write_tokens,
        "thinking_tokens": response.thinking_tokens,
        "cost_usd": cost(response),
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    calls.append(call)
    log.info(
        "[%s] %s %s: %d input, %d output (%d thinking), %d cache read, %d cache write tokens, cost %s",
        job_id, call["model"], purpose, call["input_tokens"], call["output_tokens"], call["thinking_tokens"],
        call["cache_read_tokens"], call["cache_write_tokens"],
        f"${call['cost_usd']:.4f}" if call["cost_usd"] is not None else "unknown",
    )
    llm_dir.mkdir(parents=True, exist_ok=True)
    (llm_dir / f"{len(calls):02d}-{purpose}.json").write_text(response.raw, encoding="utf-8")
    return call


def total(calls: list[dict]) -> float:
    return round(sum(call.get("cost_usd") or 0 for call in calls), 4)


def over_cost_limit(calls: list[dict], limit: float, like: tuple[str, ...] = ()) -> str | None:
    """A warning if one more model call would take the job over its cost limit, else None.

    The next call is assumed to cost what this job's calls of the same kind (`like`: their purposes) have cost on
    average, or all its calls when it has made none of that kind yet.
    """
    priced = [call for call in calls if call.get("cost_usd") is not None]
    similar = [call for call in priced if call["purpose"] in like]
    costs = [call["cost_usd"] for call in similar or priced]
    if not costs or limit <= 0:
        return None
    expected = sum(costs) / len(costs)
    spent = total(calls)
    if spent + expected <= limit:
        return None
    return (
        f"This job has used ${spent:.2f} of its ${limit:.2f} cost limit, and another "
        f"call to the language model costs about ${expected:.2f}."
    )
