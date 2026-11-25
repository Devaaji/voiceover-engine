# Voiceover test page

A Next.js page to try the voiceover API: paste a script, generate, play the audio, read the timed transcript.
See ../README.md for setup. The page calls the API through its own server (`app/api`), which adds `API_KEY`:
`start.sh` passes `API_URL` and `API_KEY` from the project's `.env`; without it, set them in `.env.local` (see
`.env.example`).
