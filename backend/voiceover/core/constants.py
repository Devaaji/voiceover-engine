"""Fixed values used across the pipeline."""

# Output video
WIDTH = 1920
HEIGHT = 1080
FPS = 30

# Each scene lasts as long as its audio plus this padding (seconds).
SCENE_PADDING = 0.5

# Where the backend runs code-server for vscode scenes.
CODE_SERVER_HOST = "127.0.0.1"
CODE_SERVER_PORT = 8080

# The voice used when nothing else is set. It needs an API key: without one,
# a job stops at the voice step and says so. "mock" is the silent voice for testing.
DEFAULT_TTS_PROVIDER = "elevenlabs"

# The voice type used when none is chosen: a name from backend/config/voice.json.
DEFAULT_VOICE_TYPE = "teacher"

# Speaking rate used by the mock voice to estimate a duration.
MOCK_WORDS_PER_MINUTE = 150

# Pipeline steps, in the order they run.
STEP_LOAD_SCRIPT = "load_script"
STEP_VOICE = "voice"
STEP_RECORD = "record"
STEP_ASSEMBLE = "assemble"
STEP_SUBTITLES = "subtitles"
STEP_ORDER = (STEP_LOAD_SCRIPT, STEP_VOICE, STEP_RECORD, STEP_ASSEMBLE, STEP_SUBTITLES)

# Job and scene ids are used as folder and file names.
ID_PATTERN = r"^[A-Za-z0-9_-]+$"

# --- AI script generation ---

# The writer for generating, fixing and revising scripts: "claude", or "openai_compatible"
# for another API (DeepSeek and others).
DEFAULT_SCRIPT_PROVIDER = "claude"
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-5-5"
# How hard Claude thinks before answering. Thinking is billed as output, so this is the main cost control.
DEFAULT_ANTHROPIC_EFFORT = "medium"
# Claude calls for one job stop being made automatically once they would cost more than this (US dollars).
# One script call with its thinking costs about $0.75 (2026-11), and a whole first run about $1.10, so this
# leaves room to fix, draw, write again and revise (raised from $2 at the user's request, 2026-11-17).
DEFAULT_MAX_JOB_COST_USD = 5.0
# A video has no target length: it is as long as its lesson needs. One that comes out longer
# than this gets a note on the review page, since it may hold more than one lesson (minutes).
LONG_VIDEO_MINUTES = 20
# How many times a script that fails its checks is sent back to be corrected. A correction costs $0.10-0.30
# (2026-11); with 2, a useTransition run (2026-11-17) ended with a timing problem left for the teacher to send back.
MAX_FIX_ATTEMPTS = 3

# --- Pacing of what is on screen (warnings on the review page) ---

# The same picture should not stay on screen longer than this (seconds).
MAX_STILL_SECONDS = 15
# A diagram or a list should show something new at least this often (seconds).
MAX_STEP_SECONDS = 6
# The same concept template may be used this many times in a row.
MAX_SAME_TEMPLATE_IN_A_ROW = 2

# --- How the lesson is guided (errors the script writer has to fix) ---

# Diagrams and pictures in one part of the lesson (between two section scenes). Fewer pictures,
# each explained longer, are easier to follow for someone new to the topic. Removing material that
# is interesting but not needed has the largest effect in the multimedia-learning research.
MAX_PICTURES_PER_PART = 2
# Diagrams and pictures in the whole video: the core mechanism gets a picture, other ideas are
# shown on the running page or said. The numbers are reasoned defaults, not measured optima.
MAX_PICTURES_PER_VIDEO = 3
# Image scenes in a video: at most the one analogy.
MAX_IMAGE_SCENES = 1
# Diagrams and pictures in a row before the viewer sees code or a page (section scenes don't count).
MAX_PICTURES_IN_A_ROW = 2
# A diagram ends with a replay of what it built: this many steps that draw nothing new.
MIN_WALKTHROUGH_STEPS = 3
# Steps that add or change something, in a row, before one points back at what is there (warning).
MAX_CHANGES_BEFORE_POINT_BACK = 2
# A section scene is a short card: its name, and a sentence back and a sentence forward.
MAX_SECTION_HEADING_WORDS = 6
MAX_SECTION_WORDS = 30
MIN_SECTION_SENTENCES = 2
# A part longer than this gets a note: it probably holds more than one step of the lesson (minutes).
LONG_PART_MINUTES = 3.5
# The lesson plan's core sentence is said, in the same words, at least this many times.
MIN_CORE_SENTENCE_REPEATS = 3
# In a vscode scene, the narration from the typing on may outlast the typing by this much. More,
# and the voice is talking about something the screen does not show (narration and picture
# have to be about the same thing at the same moment). A reasoned limit, not a measured one.
MAX_TALK_AFTER_TYPING_SECONDS = 8.0

# --- Narration written for the ear (reports/Human sounding ElevenLabs narration.md) ---
# The voice gives sentences of the same shape the same tune: a row of them that open with the same
# words ("This line prints... This line prints...") sounds like a machine reading a list.
MAX_SAME_OPENINGS_IN_A_ROW = 2
SAME_OPENING_WORDS = 2
# Three dots are read as hesitation by eleven_multilingual_v2, not as a confident beat.
MAX_ELLIPSES_PER_SCENE = 1
# A spoken sentence is heard once: a beginner holds its start to its end. use() (2026-11-19) had six sentences over
# 30 words, most with a definition inside ("a promise, which is a value that stands for..."), where the lessons the
# client found fine had 0 to 2; broadcast writing keeps sentences to about 20 words (reports/Lesson flow for one
# concept videos.md).
MAX_SENTENCE_WORDS = 30

# --- Holds: silence put into a scene's voice, so an idea has time to land ---
# Spoken information is gone once it is said, and viewers rarely pause a video themselves, so
# the video pauses for them at the complex points. Inserted into the voice that was already
# made: no new voice is needed when they change.

# A hold teaches through what the viewer does in it, not through its length, and a frozen picture
# over quiet reads as the video stalling (reports/Processing pauses that feel natural.md). So
# every hold has a kind, and the stage gives each kind something to show (hold_spans).
#
# Where the writer puts "[pause]" in the narration. After a question it is a think pause: the
# viewer guesses or recalls, with the question on screen (wait-time research: about 3 s after a
# question that asks for thought).
HOLD_THINK_SECONDS = 3.0
# Anywhere else it is a look pause: the sentence before it says where to look.
HOLD_LOOK_SECONDS = 1.5
# After a short sentence a click is timed on ("Let's click."), before the next one: a look at what the click
# changed, so the answer said next ("One!") comes after the page shows it. The click itself starts early and
# lands on the words (recording/web_recorder.py, click_lead and click_after). A 2.5 s beat covered a click that
# started late (a cleared highlight stood between the words and the click), and left the page still for 2.7 s
# where the click was on time (useReducer, 2026-11-15).
HOLD_CLICK_SECONDS = 1.0
# A click sentence is short: the words from the wait's words to the sentence's end.
CLICK_SENTENCE_WORDS = 4
# A look pause the writer put at the very end of a scene goes before the scene's last sentence (its
# takeaway) instead, this long: words right after a pause are remembered better, and the scene ends
# on the voice, not on a stop.
HOLD_BEFORE_TAKEAWAY_SECONDS = 1.0
# The one length every "[pause]" got before pauses had kinds. A hold stored with it gets its kind's.
HOLD_PAUSE_SECONDS = 2.5
# A finished diagram: a look beat before its last sentence, the element it ends on lit and the rest
# dimmed. The only tested automatic pause (Spanjers et al. 2012) was 2 s, over a dimmed picture. 1.0 s with the human
# rhythm below: a look, not a stop (voice trial of 2026-11-22, version G).
HOLD_DIAGRAM_LOOK_SECONDS = 1.0
# After a diagram step that draws something new (0.8 s until the faster voice of 2026-11-22).
HOLD_DIAGRAM_STEP_SECONDS = 0.6
# After each sentence of an explanation (a diagram, a slide of points, code beside its page), the whole pause heard:
# time to take the idea in before the next one. The user and the client found the videos too fast for newcomers; of
# four versions of the useTransition diagram (as it was, the voice 8% slower, these holds, both) the user chose this
# one as the easiest to take in (2026-11-18). Pauses at complex points help novices learn (Liu et al. 2022, d about
# 0.4-0.5), who rarely pause a video themselves.
# Then the client (2026-11-21): at 1x "lots of pauses and the talking feels quite slow", mostly outside the code; and
# the user (2026-11-22): the same pause after every sentence sounds flat and robotic, a person pauses short and long,
# fast on average. Of five versions (outputs/voice-style-trial) the user liked best the one with this human rhythm: a
# pause as long as the sentence carried (HOLD_SENTENCE_BASE + HOLD_SENTENCE_PER_WORD a word), longer after a question,
# shorter when the next sentence carries on from it, never twice exactly the same (holds.sentence_beat). The numbers
# are version G of the trial, set after measuring a clip of the teacher's own talk (0.73 s after a sentence on average,
# 232 words a minute): with the faster voice the video says about 174 words a minute and pauses about 1 s after a
# sentence, the closest of eight versions to his pace (outputs/voice-style-trial).
HOLD_SENTENCE_SECONDS = 2.2  # the one beat every sentence had before (2026-11-18 to 2026-11-22)
HOLD_SENTENCE_BASE = 0.25
HOLD_SENTENCE_PER_WORD = 0.03
HOLD_SENTENCE_QUESTION = 0.25  # a question is given a moment more
HOLD_SENTENCE_CARRIES_ON = 0.65  # times the pause when the next sentence starts with So, And, Then...
HOLD_SENTENCE_VARIES = 0.15  # up to this share shorter or longer, the same for the same sentence
HOLD_SENTENCE_RANGE = (0.3, 1.2)
HOLD_SENTENCE_SCENES = ("diagram", "points", "connect")
# A sentence this short ("Nice.", "Let's see.") carries no idea to take in.
HOLD_SENTENCE_MIN_WORDS = 5
# After a section card: with the gap between scenes, about a second at the boundary.
HOLD_SECTION_END_SECONDS = 0.5
# A dead stop: the picture stands still while the audio is quiet. Every final video is checked for
# one this long or longer.
DEAD_STOP_MAX_SECONDS = 1.5
# A connect scene that comes from the editor starts quiet while the editor shrinks into its code
# panel and the page slides in (about 1.25 s); its voice starts after that, as the viewer has
# found their way on the new layout. One going back to the editor ends quiet while the code
# panel grows into the editor. Continuity research: animated layout changes of about 1 s keep
# viewers oriented, and the eyes settle about 300 ms after a change.
HOLD_ENTER_FROM_EDITOR_SECONDS = 1.3
HOLD_LEAVE_TO_EDITOR_SECONDS = 1.0
# The written marker for a hold in the narration.
PAUSE_MARK = "[pause]"

# --- Loudness of the final video ---

LOUDNESS_TARGET_LUFS = -16.0
LOUDNESS_TRUE_PEAK_DB = -1.5

# --- Images for image and concept scenes ---

# "manual": the teacher makes each picture from its prompt and uploads it.
# "elevenlabs" generates them, but its API needs the Pro plan or above.
DEFAULT_IMAGE_PROVIDER = "manual"
DEFAULT_IMAGE_MODEL = "gemini-2.5-flash-image"
DEFAULT_IMAGE_STYLE = (
    "clean flat illustration, dark navy background, one soft accent color, simple shapes, "
    "no text, no letters, no logos"
)
DEFAULT_MAX_IMAGES_PER_JOB = 4
IMAGE_ASPECT_RATIO = "16:9"

# Bullet-point scenes in a row: a third list right after two reads as a wall of bullets (client review
# 2026-11-14). The why and when to reach for it are one list.
MAX_POINTS_IN_A_ROW = 2

# Words on a diagram's board besides its title (reports/Minimal screen text and code context.md): the
# picture names the parts, the narration explains them. About 15 is the aim; more than this is sent back.
MAX_DIAGRAM_WORDS = 18
# A part's name, an arrow's label and a moving value, in words.
MAX_DIAGRAM_LABEL_WORDS = 4
MAX_ARROW_LABEL_WORDS = 3
MAX_MOVING_TEXT_WORDS = 2
# Labeled arrows in one diagram: only the key action is written, the narration says the rest.
MAX_LABELED_ARROWS = 1
# A panel's title, in words (the client's diagram guidelines, 2026-11-14).
MAX_PANEL_CAPTION_WORDS = 3
