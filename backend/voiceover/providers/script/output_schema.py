"""The JSON schema Claude's lesson plan must follow (structured outputs).

voiceover-engine: only the lesson plan's schema is copied from backend/app/providers/script/output_schema.py of the
Video Automation repo, word for word. The video script's schema (scenes, actions, files) is not.
"""

STRING = {"type": "string"}
INTEGER = {"type": "integer"}
STRINGS = {"type": "array", "items": STRING}


def _object(**properties: dict) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _array(items: dict) -> dict:
    return {"type": "array", "items": items}


# The lesson plan, written before the script (services/generation_service.py, prompts/plan_system.md):
# what the viewer knows, the why, the core model and its sentence, the new terms in the order they
# depend on each other, the one running example, the one analogy, the parts. A schema of its own,
# so it costs nothing of the script schema's size limit.
NAMED = _object(name=STRING, meaning=STRING)
PLAN_SCHEMA = _object(
    audience=STRING,
    why=STRING,
    model=_array(NAMED),
    core_sentence=STRING,
    terms=_array(_object(term=STRING, plain=STRING)),
    example=STRING,
    analogy=_object(source=STRING, mapping=_array(_object(part=STRING, analog=STRING)), relation=STRING, breaks=STRING),
    parts=_array(_object(heading=STRING, goal=STRING)),
    # Plain words and the official terms they stand for: shown together on screen when first said.
    words=_array(_object(plain=STRING, official=STRING)),
    said_not_shown=STRINGS,
)
