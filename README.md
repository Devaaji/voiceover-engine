# voiceover-engine

Turns a script into a natural voiceover: an audio file and a transcript with the time of every segment, sentence
and word. It is the audio pipeline of the Video Automation tool, taken out so any video tool can call it over HTTP.

The voice, its settings, the pauses, the room tone, the levelling and the prompts are the same as in that tool: its
Python code is reused, and golden tests check that the audio comes out byte for byte the same.

| Mode | Input | Status |
|---|---|---|
| `script` | A finished script. Spoken word for word, or rewritten in the teacher's way of talking with `"rewrite": true`. | Available |
| `content` | Raw material or a topic. The narration is written first (lesson plan, narration, the teacher's way of talking). | Coming next |

## How it works

1. The script is cut into segments (a blank line ends one). `[pause]` in the text becomes a pause: after a
   question about 3 s (time to think), anywhere else about 1.5 s.
2. Optionally (`"rewrite": true`), Claude rewrites each segment in the teacher's way of talking. A segment whose new
   wording loses a technical term, moves a `[pause]` or changes its length too much keeps its own words.
3. ElevenLabs speaks each segment in one request, with the sentences around it as context so it sounds like one talk,
   and returns the time of every character. The pronunciation list (`config/pronunciations.json`) changes only what
   the voice is given, never the transcript.
4. Pauses go in: the human rhythm after each sentence of an explanation (0.3 to 1.2 s), and the `[pause]` marks. They
   are filled with the voice's own room tone, never digital silence.
5. Each segment is levelled (a slow gain that evens out loud and soft phrases, pauses brought down to -60 dBFS),
   padded by 0.5 s, joined, and brought to -16 LUFS.
6. The transcript is timed from ElevenLabs' character times: `transcript.json`, `subtitles.srt`, `subtitles.vtt`.

## Project layout

```
backend/            FastAPI
  main.py           the app (CORS, error handling)
  api/              the routes and the X-API-Key check
  jobs/             jobs on disk (data/jobs/<id>/), run in background threads
  voiceover/        the audio pipeline, copied from the Video Automation repo
  writing/          the Claude calls (rewrite now, mode "content" next)
  tests/            golden, parity and API tests
frontend/           Next.js test page (paste a script, generate, play, read the transcript)
config/             voice.json (voice types), pronunciations.json, llm_prices.json
prompts/            the teacher-style prompt and the teacher's own words, the lesson-plan prompt
assets/voice/       the approved take of the opening line
Dockerfile          the backend with FFmpeg, for Railway
```

## Setup

You need Python 3.13, Node.js 20 or newer, and FFmpeg (`ffmpeg` and `ffprobe` on the PATH).

```bash
cp .env.example .env          # then fill in API_KEY, ELEVENLABS_API_KEY and, for rewrite, ANTHROPIC_API_KEY

cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt     # macOS/Linux: .venv/bin/python
.venv/Scripts/python -m uvicorn main:app --port 8000

cd ../frontend
cp .env.example .env.local    # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install
npm run dev                   # http://localhost:3000, paste the API_KEY into the page
```

## Environment variables

All of them go in `.env` at the project root (or in the host's variables). See `.env.example`.

| Name | Default | What it does |
|---|---|---|
| `API_KEY` | (none) | Required. Every request must send it in the `X-API-Key` header; without it set, every request is refused. |
| `CORS_ORIGINS` | `http://localhost:3000` | Sites that may call the API from a browser, comma separated. |
| `API_DOCS` | `off` | `on` serves FastAPI's `/docs`, which needs no key. Local development only. |
| `ELEVENLABS_API_KEY` | (none) | Required for the voice. |
| `ELEVENLABS_VOICE_ID` | `rExOvxZPbTNhO480h6cK` | The voice. **It must exist in the ElevenLabs account that owns `ELEVENLABS_API_KEY`**: a voice clone made in that account, or a voice added to its library. A voice of another account returns an error. |
| `ELEVENLABS_MODEL_ID` | `eleven_multilingual_v2` | The model the voice was tuned and approved with. |
| `TTS_PROVIDER` | `elevenlabs` | `mock` makes silent audio of a realistic length: for tests, no credits. |
| `VOICE_TYPE` | `teacher` | A voice type of `config/voice.json`: `teacher`, `steady` or `lively`. A request can choose another. |
| `VOICE_LEVELER` | on | `off` skips the per-phrase levelling (the final loudness is still set). |
| `PAUSE_RHYTHM` | `human` | `even` gives every sentence of an explanation the same 2.2 s pause, as before 2026-11-22. |
| `OPENING_LINE` | `Hey guys! This is Ed Roh.` | The line a request with `"opening": true` opens with. |
| `APPROVED_OPENING` | on | Uses the approved take in `assets/voice` when the voice and the line match it. `off` speaks the line anew. |
| `OPENING_PAUSE_SECONDS` | `1.0` | The quiet after the opening line. |
| `ANTHROPIC_API_KEY` | (none) | Required for `"rewrite": true` and mode `content`. |
| `ANTHROPIC_MODEL` | `claude-sonnet-5-5` | |
| `ANTHROPIC_EFFORT` | `medium` | |
| `ANTHROPIC_WORKSPACE_ID` | (none) | Only for a key that is not tied to one workspace. |
| `COST_LIMIT_USD` | `5` | The most one job may spend on Claude. |
| `DATA_DIR` | `data` | Where jobs' files go. Mount a volume here on Railway. |
| `MAX_CONCURRENT_JOBS` | `1` | How many jobs make their voice at the same time. |

## API

Every endpoint needs the header `X-API-Key: <API_KEY>`. Without it: `401`.

### POST /voiceover

Starts a job and answers at once with `202`. Making the voice takes from seconds to minutes, so poll the job's
`statusUrl` until its `status` is `done` or `failed`, or pass a `callbackUrl`.

| Field | Default | |
|---|---|---|
| `mode` | `"script"` | `"script"` or `"content"` (coming next). |
| `script` | | The script as text. A blank line ends a segment. `[pause]` puts a pause in. |
| `segments` | | Instead of `script`: `[{ "text": "...", "kind": "explain" \| "section" \| "plain" }]`. `explain` pauses after each sentence (the default), `section` pauses at its end, `plain` only where `[pause]` says. |
| `rewrite` | `false` | `true` rewrites the script in the teacher's way of talking first (Claude). |
| `voiceType` | `VOICE_TYPE` | A voice type of `config/voice.json` (`GET /voice-types`). |
| `opening` | `false` | `true` opens the voiceover with `OPENING_LINE`. |
| `openingLine` | | Opens with this line instead. Off when neither is sent. |
| `pronunciations` | `{}` | Extra terms, `{ "ROS": "ross" }`, on top of `config/pronunciations.json`. |
| `format` | `"mp3"` | `"mp3"` (192 kb/s) or `"wav"` (16-bit, 48 kHz, stereo). |
| `callbackUrl` | | Called with the job as JSON (POST) when it is done or failed. |

```bash
curl -X POST http://localhost:8000/voiceover \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{
    "script": "So this little robot arm has three joints.\n\nWhich joint moves first? [pause] All three at once.",
    "format": "mp3"
  }'
```

```json
{
  "id": "vo-20261124-062527-1524c4",
  "status": "queued",
  "mode": "script",
  "step": null,
  "progress": "",
  "statusUrl": "http://localhost:8000/voiceover/vo-20261124-062527-1524c4",
  "fileUrls": {}
}
```

### GET /voiceover/{id}

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/voiceover/vo-20261124-062527-1524c4
```

```json
{
  "id": "vo-20261124-062527-1524c4",
  "status": "done",
  "step": null,
  "progress": "Done",
  "error": null,
  "warnings": [],
  "voice": { "tts_provider": "elevenlabs", "elevenlabs_voice_id": "rExOvxZPbTNhO480h6cK", "elevenlabs_model_id": "", "voice_type": "teacher" },
  "voice_credits": 159,
  "claude_calls": [],
  "claude_cost_usd": 0.0,
  "loudness": { "measured_lufs": -16.1, "final_lufs": -16.2, "true_peak_db": -3.2, "voice_spread_lu": 2.4, "seconds": 24.299 },
  "duration": 24.299,
  "files": ["audio.mp3", "subtitles.srt", "subtitles.vtt", "transcript.json"],
  "statusUrl": "http://localhost:8000/voiceover/vo-20261124-062527-1524c4",
  "fileUrls": {
    "audio.mp3": "http://localhost:8000/voiceover/vo-20261124-062527-1524c4/files/audio.mp3",
    "transcript.json": "http://localhost:8000/voiceover/vo-20261124-062527-1524c4/files/transcript.json"
  }
}
```

`status` is `queued`, `running` (`step`: `writing`, `voice`, `levelling`, `transcript`), `done` or `failed` (with
`error`). A job that was waiting or running when the server restarted is `failed`: send it again.

### GET /voiceover/{id}/files/{name}

`audio.mp3` or `audio.wav`, `transcript.json`, `subtitles.srt`, `subtitles.vtt`.

```bash
curl -H "X-API-Key: $API_KEY" -o voiceover.mp3 http://localhost:8000/voiceover/vo-20261124-062527-1524c4/files/audio.mp3
```

`transcript.json` (times in seconds from the start of the audio; a sentence or word marked `"estimated"` was spread
by its length because the voice's times could not be followed there):

```json
{
  "text": "So this little robot arm has three joints. ...",
  "duration": 24.299,
  "segments": [
    {
      "id": "s01", "kind": "explain", "text": "...", "start": 0.0, "end": 8.763,
      "sentences": [
        {
          "text": "So this little robot arm has three joints, and each one has its own motor.",
          "start": 0.0, "end": 4.327,
          "words": [{ "text": "So", "start": 0.0, "end": 0.163 }, { "text": "this", "start": 0.163, "end": 0.279 }]
        }
      ]
    }
  ]
}
```

### GET /voice-types

The voice types of `config/voice.json`, for `voiceType`.

### Errors

`401` without the right key, `422` for a request that is not valid (the body says which field), `400` for an unknown
voice type or a mode that is not available, `404` for an unknown job or file, `503` while `API_KEY` is not set.

## Calling it from another tool

```python
import time, httpx

API, KEY = "https://<your-app>.up.railway.app", "<API_KEY>"
headers = {"X-API-Key": KEY}

job = httpx.post(f"{API}/voiceover", headers=headers, json={"script": open("script.txt").read()}).json()
while job["status"] in ("queued", "running"):
    time.sleep(2)
    job = httpx.get(job["statusUrl"], headers=headers).json()
if job["status"] == "failed":
    raise RuntimeError(job["error"])
open("voiceover.mp3", "wb").write(httpx.get(job["fileUrls"]["audio.mp3"], headers=headers).content)
transcript = httpx.get(job["fileUrls"]["transcript.json"], headers=headers).json()
```

```ts
const headers = { "X-API-Key": process.env.VOICEOVER_API_KEY!, "Content-Type": "application/json" };
let job = await (await fetch(`${API}/voiceover`, { method: "POST", headers, body: JSON.stringify({ script }) })).json();
while (job.status === "queued" || job.status === "running") {
  await new Promise((resolve) => setTimeout(resolve, 2000));
  job = await (await fetch(job.statusUrl, { headers })).json();
}
const audio = await (await fetch(job.fileUrls["audio.mp3"], { headers })).arrayBuffer();
```

Keep the API key on the server side of your tool: a browser page that holds it gives it to everyone who opens it.

## Tests

```bash
cd backend
.venv/Scripts/python -m pytest                     # golden + API tests (mock voice, no credits)
OLD_REPO=D:/1_FREELANCE/automation-video-tools .venv/Scripts/python -m pytest   # + parity with the old code
```

- **Golden** (`tests/golden`): real voices of five scenes of a finished Video Automation job (a title, three
  explanations, a section, with `[pause]` holds). This engine makes their audio again from the same voice, with no call
  to ElevenLabs, and the result must be byte-identical to what the old pipeline made: the pauses, the room tone, the
  levelling, the padding. Byte comparison needs the FFmpeg build the fixtures were made with (9.0.2); with another
  build only the numbers are compared. Rebuild fixtures with `tests/golden/build_fixtures.py`.
- **Parity** (`tests/parity`, only with `OLD_REPO`): the old repo's own code, run in its own Python, and the copy here
  answer the same cases the same way (pronunciations, pauses, room tone, leveler filters, the ElevenLabs request, the
  teacher-style pass, subtitles).
- **API** (`tests/test_api.py`, `tests/test_segments.py`): the key, the request rules, the opening option, a job from
  request to files.

## Deploying to Railway

1. Create a service from this repository; Railway builds the `Dockerfile` (Python 3.13 and FFmpeg 9.0.2).
2. Add a volume mounted at `/data` (job files survive a redeploy).
3. Set the variables: `API_KEY`, `ELEVENLABS_API_KEY`, `ANTHROPIC_API_KEY` (for rewrite), `CORS_ORIGINS` (the test
   page's URL), and any other from the table. `PORT` is set by Railway.
4. Keep one replica: jobs run in the service's own background threads.
5. The test page (`frontend/`) is deployed on its own (Vercel, or a second Railway service) with
   `NEXT_PUBLIC_API_URL` set to the backend's URL. It asks for the API key in the page and keeps it in that browser.

## Where the code comes from

`backend/voiceover/` is the Video Automation repo's `backend/app/` audio code of 2026-11-23, with `app.` renamed to
`voiceover.`. Unchanged: the ElevenLabs provider, the pronunciation wrapper, the mock voice, the leveler, the voice
types, the opening take, the teacher-style pass, the holds (one import), ffmpeg/text/srt helpers, constants and errors.
Derived from its pipeline steps, with the video-only parts left out: `pipeline/voice.py` (no waiting for typed code,
no diagram timing), `pipeline/assemble.py` (no video join, no dead-stop check) and `pipeline/transcript.py` (plus VTT
and per-word times). New: `segments.py`, `output.py` (an audio-only join and MP3/WAV output), the jobs, the API.
