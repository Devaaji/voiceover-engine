"""The backend/config/voice.json format: the voice types to choose from, and what each one is made of."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LevelerFeel(Strict):
    """How firmly the leveler evens out a voice. Each voice type has its own."""

    # How much of a moment's distance to the scene's loudness is taken away. 1: all of it, 0: none.
    strength: float = Field(ge=0, le=1)
    # A moment is never made louder or quieter by more than this.
    max_change_db: float = Field(ge=0, le=24)
    # A moment's level is that of the speech in a window this long around it.
    window_ms: int = Field(ge=200, le=10000)
    # The gain is averaged over this long, so it never moves fast.
    smooth_ms: int = Field(ge=50, le=5000)


class LevelerShared(Strict):
    """How the leveler measures a voice. The same for every voice type."""

    # The gain is a line through one point every this long.
    point_ms: int = Field(ge=50, le=2000)
    # The audio is measured in pieces this long.
    frame_ms: int = Field(ge=10, le=200)
    # A piece this far under the scene's loud level is not counted as speech: a pause, a soft ending.
    gate_db: float = Field(ge=10, le=60)
    # Sound this far under the scene's loudness is a breath or a noise, not speech: it is not brought up.
    ignore_below_db: float = Field(ge=3, le=40)
    # The limiter keeps the peaks this far under the final video's peak limit.
    limiter_headroom_db: float = Field(ge=0, le=6)
    # The floor: after the gain, a pause is brought down to this level (dBFS), never more than
    # max_floor_cut_db. The gain lifts the voice's own quiet and the room tone with it (to -47 dBFS in
    # one video, heard as a "zzz" in the pauses); ACX asks for -60 at most.
    floor_db: float = Field(default=-60.0, ge=-90, le=-30)
    # A pause: at least min_quiet_ms of audio this far under the scene's loud level. Words, their tails
    # and breaths are louder, and keep their level.
    quiet_below_db: float = Field(default=30.0, ge=15, le=60)
    min_quiet_ms: int = Field(default=200, ge=50, le=2000)
    # How long the floor takes to come down after a pause starts, and to go back up before it ends.
    floor_ramp_ms: int = Field(default=80, ge=10, le=500)
    max_floor_cut_db: float = Field(default=24.0, ge=0, le=60)


class LevelerConfig(LevelerFeel, LevelerShared):
    """Everything the leveler needs for one voice type: its feel and the shared numbers."""


class VoiceStyle(Strict):
    """How an ElevenLabs voice speaks: sent with every request instead of the voice's stored settings."""

    # Lower: more variation and emotion from one sentence to the next. Higher: steadier, flatter.
    stability: float = Field(ge=0, le=1)
    # How closely the voice keeps to the original speaker.
    similarity_boost: float = Field(ge=0, le=1)
    # How much of the speaker's style is exaggerated. 0: none.
    style: float = Field(ge=0, le=1)
    use_speaker_boost: bool
    speed: float = Field(ge=0.7, le=1.2)


class VoiceType(Strict):
    """One way a video's voice is made, to choose in Settings: how it speaks, how its script is worded, how it is levelled."""

    # What Settings shows for it.
    label: str = Field(min_length=1)
    note: str = ""
    # A name from `styles`. Empty: the settings stored with the voice at ElevenLabs.
    style: str = ""
    # How the script's narration is worded: plain statements, written for a voice that performs, or the way
    # the teacher talks in his own videos (prompts/style_examples holds his own words).
    narration: Literal["plain", "spoken", "teacher"]
    leveler: LevelerFeel


class VoiceConfig(Strict):
    types: dict[str, VoiceType] = Field(min_length=1)
    styles: dict[str, VoiceStyle]
    leveler: LevelerShared


class VoiceTypeChoice(BaseModel):
    """A voice type as the Settings page lists it."""

    id: str
    label: str
    note: str = ""
