"""Talks to the Claude API for script generation.

API reference: https://platform.claude.com/docs/en/build-with-claude/structured-outputs
and https://platform.claude.com/docs/en/build-with-claude/pdf-support
"""

import base64
from pathlib import Path

import anthropic

from voiceover.core.constants import DEFAULT_ANTHROPIC_MODEL
from voiceover.core.exceptions import ProviderUnavailable
from voiceover.providers.script.output_schema import PLAN_SCHEMA
from voiceover.providers.script.writer import LLMResponse, ScriptWriter, only_json

# Streaming is used, so a long answer never hits an HTTP timeout. Thinking counts toward it: a
# rich lesson can think for 50,000 tokens before it writes 15,000 (useRef did, 2026-11-07), so
# the model's full 128K output is allowed (claude-sonnet-5-5 and the other current models).
MAX_TOKENS = 128_000
# The script's call is told how many tokens its thinking and its answer have together, and sees
# them count down, so it paces its thinking and always ends its answer. Without it, long notes
# thought for 101,000 tokens and the answer was cut off at 128,000 (useReducer, 2026-11-15).
# MAX_TOKENS stays the hard limit; the budget leaves room under it.
SCRIPT_TASK_BUDGET = 112_000
TASK_BUDGET_BETA = "task-budgets-2026-03-13"
# If Claude's safety filters decline a request, the API retries it on the
# model Anthropic recommends for that case instead of returning nothing.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Marks the end of what can be reused (and billed cheaply) by the next call.
CACHED = {"type": "ephemeral"}
WORKSPACE_HEADER = "anthropic-workspace-id"


def notes_block(path: Path) -> dict:
    """The course notes as a content block. A PDF is sent as it is, not converted to text."""
    if path.suffix.lower() == ".pdf":
        data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
        source = {"type": "base64", "media_type": "application/pdf", "data": data}
        return {"type": "document", "source": source, "cache_control": CACHED}
    text = path.read_text(encoding="utf-8")
    return {"type": "text", "text": f"<notes>\n{text}\n</notes>", "cache_control": CACHED}


def _paid(error: ProviderUnavailable, response: LLMResponse) -> ProviderUnavailable:
    error.response = response  # type: ignore[attr-defined]
    return error


class ClaudeScriptWriter(ScriptWriter):
    name = "Claude"

    def __init__(self, api_key: str, model: str, workspace_id: str = "") -> None:
        if not api_key:
            raise ProviderUnavailable(
                "Writing the narration needs an Anthropic API key: set ANTHROPIC_API_KEY in .env."
            )
        # A key that is not tied to one workspace must name the workspace on every request.
        headers = {WORKSPACE_HEADER: workspace_id} if workspace_id else None
        self._client = anthropic.Anthropic(api_key=api_key, default_headers=headers)
        self.model = model or DEFAULT_ANTHROPIC_MODEL

    # voiceover-engine: complete() (the video script, held to PACKAGE_SCHEMA) is not copied.

    def complete_plan(self, system: str, notes: Path, request: str, effort: str) -> LLMResponse:
        """The lesson plan of the notes, held to PLAN_SCHEMA by the API."""
        messages = [{"role": "user", "content": [notes_block(notes), {"type": "text", "text": request}]}]
        output = {"effort": effort, "format": {"type": "json_schema", "schema": PLAN_SCHEMA}}
        return self._ask(system, messages, output, self.model, "lesson plan")

    def complete_json(self, system: str, request: str, effort: str, model: str | None = None) -> LLMResponse:
        """Return Claude's answer to `request` as one JSON object. No schema is enforced: the caller checks it."""
        response = self._ask(system, [{"role": "user", "content": request}], {"effort": effort}, model or self.model, "diagram")
        response.text = only_json(response.text)
        return response

    def _ask(self, system: str, messages: list[dict], output: dict, model: str, what: str) -> LLMResponse:
        try:
            with self._client.beta.messages.stream(
                model=model,
                max_tokens=MAX_TOKENS,
                # The system prompt is the same for every call of its sort, so it is cached.
                system=[{"type": "text", "text": system, "cache_control": CACHED}],
                messages=messages,
                output_config=output,
                betas=[FALLBACK_BETA, TASK_BUDGET_BETA] if "task_budget" in output else [FALLBACK_BETA],
                fallbacks="default",
            ) as stream:
                message = stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise ProviderUnavailable("The Anthropic API key was rejected. Check it in Settings.") from exc
        except anthropic.PermissionDeniedError as exc:
            raise ProviderUnavailable(f"The Anthropic API key may not use this model: {exc.message}") from exc
        except anthropic.NotFoundError as exc:
            raise ProviderUnavailable(f'The model "{model}" was not found. Check it in Settings.') from exc
        except anthropic.RateLimitError as exc:
            raise ProviderUnavailable("The Anthropic API rate limit was reached. Try again in a minute.") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderUnavailable(f"The Anthropic API returned {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderUnavailable("Could not reach the Anthropic API. Check the connection.") from exc

        text = next((block.text for block in message.content if block.type == "text"), "")
        usage = message.usage
        response = LLMResponse(
            text=text,
            model=message.model,
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            cache_read_tokens=usage.cache_read_input_tokens or 0,
            cache_write_tokens=usage.cache_creation_input_tokens or 0,
            thinking_tokens=getattr(usage.output_tokens_details, "thinking_tokens", None) or 0,
            raw=message.to_json(),
        )
        # An answer that is no use was still paid for: the error carries it, so its cost is counted.
        if message.stop_reason == "refusal":
            category = getattr(message.stop_details, "category", None) or "no category given"
            raise _paid(ProviderUnavailable(f"Claude declined to write this {what} ({category})."), response)
        if message.stop_reason == "max_tokens":
            hint = " The notes may hold more than one lesson: split them into two files." if what == "script" else ""
            raise _paid(ProviderUnavailable(f"Claude's answer was cut off because it was too long.{hint}"), response)
        return response
