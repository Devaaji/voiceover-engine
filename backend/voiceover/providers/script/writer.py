"""The interface for whatever language model writes a script from course notes.

claude.py talks to the Claude API. openai_compatible.py talks to any API that
follows OpenAI's chat format (DeepSeek and others). registry.py picks one.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LLMResponse:
    text: str  # the JSON answer
    model: str  # the model that answered
    input_tokens: int  # not counting the cached ones below
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    thinking_tokens: int  # part of output_tokens
    raw: str  # the API response as JSON, for work/llm/


def only_json(text: str) -> str:
    """The JSON object in an answer, without a code fence or words around it."""
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if 0 <= start < end else text.strip()


class ScriptWriter(ABC):
    name: str  # for messages to the teacher, for example "Claude" or "DeepSeek"
    model: str

    # voiceover-engine: complete() (the video script, in the package format) is not copied.

    def complete_plan(self, system: str, notes: Path, request: str, effort: str) -> LLMResponse | None:
        """Ask for the lesson plan of the notes: one JSON object in the plan format (output_schema.PLAN_SCHEMA).

        None from a writer that can't: the script is then written without a plan.
        """
        return None

    @abstractmethod
    def complete_json(self, system: str, request: str, effort: str, model: str | None = None) -> LLMResponse:
        """Ask for one JSON object in answer to `request`, in no enforced format: the caller checks it.

        Used for a diagram's spec, whose shape depends on its kind. `model` is another
        model of the same API than the one that writes the script.
        """
