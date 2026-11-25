"use client";

import { useEffect, useRef, useState } from "react";

type Mode = "script" | "content";

// What each tab starts with, so the page can be tried at once: two segments and a pause.
const EXAMPLES: Record<Mode, string> = {
  script:
    "So this robot arm has three joints. Each one turns on its own motor.\n\n" +
    "Can you guess which joint moves first? [pause] It's the base.",
  content: "How a robot arm with three joints moves: the base turns, the shoulder lifts, the elbow bends.",
};

interface Job {
  id: string;
  status: "queued" | "running" | "done" | "failed";
  step: string | null;
  progress: string;
  error: string | null;
  warnings: string[];
  voice_credits: number;
  claude_cost_usd: number;
  duration: number | null;
  loudness: { final_lufs?: number | null } | null;
  files: string[];
}

interface Word {
  text: string;
  start: number;
  end: number;
}

interface Transcript {
  duration: number;
  segments: { id: string; kind: string; sentences: { text: string; start: number; end: number; words: Word[] }[] }[];
}

function clock(seconds: number): string {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${(seconds - minutes * 60).toFixed(1).padStart(4, "0")}`;
}

// The API through this page's own server (app/api), which adds the API key from its environment.
async function call(path: string, init: RequestInit = {}): Promise<Response> {
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const detail = Array.isArray(body.detail) ? body.detail.map((item: { msg: string }) => item.msg).join("; ") : body.detail;
    throw new Error(`${response.status}: ${detail ?? response.statusText}`);
  }
  return response;
}

export default function VoiceoverTester() {
  const [mode, setMode] = useState<Mode>("script");
  // Each tab keeps its own text.
  const [texts, setTexts] = useState<Record<Mode, string>>(EXAMPLES);
  const text = texts[mode];
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState("");
  const [audioUrl, setAudioUrl] = useState("");
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [now, setNow] = useState(0);
  const audio = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    if (!job || job.status === "done" || job.status === "failed") return;
    const timer = setTimeout(async () => {
      try {
        setJob(await (await call(`/voiceover/${job.id}`)).json());
      } catch (reason) {
        setError((reason as Error).message);
      }
    }, 1500);
    return () => clearTimeout(timer);
  }, [job]);

  useEffect(() => {
    if (job?.status !== "done") return;
    const audioName = job.files.find((name) => name.startsWith("audio."));
    let made = "";
    (async () => {
      if (audioName) {
        made = URL.createObjectURL(await (await call(`/voiceover/${job.id}/files/${audioName}`)).blob());
        setAudioUrl(made);
      }
      if (job.files.includes("transcript.json")) {
        setTranscript(await (await call(`/voiceover/${job.id}/files/transcript.json`)).json());
      }
    })().catch((reason: Error) => setError(reason.message));
    return () => {
      if (made) URL.revokeObjectURL(made);
    };
  }, [job?.status, job?.id, job?.files]);

  async function generate() {
    setError("");
    setJob(null);
    setAudioUrl("");
    setTranscript(null);
    // Everything else (voice, voice type, format) is the API's own setting, from .env.
    const body = mode === "script" ? { mode, script: text } : { mode, content: text };
    try {
      const response = await call("/voiceover", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      setJob(await response.json());
    } catch (reason) {
      setError((reason as Error).message);
    }
  }

  async function download(name: string) {
    if (!job) return;
    const blob = await (await call(`/voiceover/${job.id}/files/${name}`)).blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${job.id}-${name}`;
    link.click();
    URL.revokeObjectURL(url);
  }

  function seek(seconds: number) {
    if (!audio.current) return;
    audio.current.currentTime = seconds;
    void audio.current.play();
  }

  const running = job !== null && (job.status === "queued" || job.status === "running");

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8 space-y-6">
      <h1 className="text-2xl font-semibold">Voiceover test page</h1>

      <div className="flex gap-2 border-b border-neutral-400/40" role="tablist">
        {(["script", "content"] as Mode[]).map((tab) => (
          <button
            key={tab}
            role="tab"
            aria-selected={mode === tab}
            onClick={() => setMode(tab)}
            className={`px-3 py-2 text-sm ${mode === tab ? "border-b-2 border-current font-semibold" : "opacity-60"}`}
          >
            {tab === "script" ? "Script" : "Content"}
          </button>
        ))}
      </div>

      <label className="block space-y-1">
        <span className="text-sm opacity-70">
          {mode === "script"
            ? "A finished script (an example to start with: change it or press Generate). A blank line starts a new segment; [pause] puts a pause in."
            : "Raw material or a topic: the narration is written from it first (not available yet)."}
        </span>
        <textarea
          value={text}
          onChange={(event) => setTexts({ ...texts, [mode]: event.target.value })}
          rows={10}
          className="w-full rounded border border-neutral-400/50 bg-transparent px-3 py-2 text-sm leading-relaxed"
        />
      </label>

      <button
        onClick={generate}
        disabled={!text.trim() || running || mode === "content"}
        className="rounded bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-neutral-100 dark:text-neutral-900"
      >
        {running ? "Generating…" : "Generate"}
      </button>

      {error && <p className="rounded border border-red-500/50 px-3 py-2 text-sm text-red-600 dark:text-red-400">{error}</p>}

      {job && (
        <section className="space-y-2 text-sm">
          <p>
            <span className="font-mono">{job.id}</span>: <strong>{job.status}</strong>
            {job.step ? `, ${job.step}` : ""}
            {job.progress ? ` (${job.progress})` : ""}
          </p>
          <p className="opacity-70">
            ElevenLabs {job.voice_credits} credits · Claude ${job.claude_cost_usd.toFixed(2)}
            {job.duration ? ` · ${clock(job.duration)}` : ""}
            {job.loudness?.final_lufs != null ? ` · ${job.loudness.final_lufs} LUFS` : ""}
          </p>
          {job.error && <p className="text-red-600 dark:text-red-400">{job.error}</p>}
          {job.warnings.length > 0 && (
            <ul className="list-disc space-y-1 pl-5 opacity-80">
              {job.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          )}
        </section>
      )}

      {audioUrl && (
        <section className="space-y-3">
          <audio ref={audio} src={audioUrl} controls className="w-full" onTimeUpdate={(event) => setNow(event.currentTarget.currentTime)} />
          <div className="flex flex-wrap gap-2 text-sm">
            {job?.files.map((name) => (
              <button key={name} onClick={() => download(name)} className="rounded border border-neutral-400/50 px-2 py-1">
                {name}
              </button>
            ))}
          </div>
        </section>
      )}

      {transcript && (
        <section className="space-y-4">
          <h2 className="text-lg font-semibold">Transcript</h2>
          {transcript.segments.map((segment) => (
            <div key={segment.id} className="space-y-1">
              <p className="font-mono text-xs opacity-60">
                {segment.id} · {segment.kind}
              </p>
              {segment.sentences.map((sentence) => (
                <p key={`${segment.id}-${sentence.start}`} className="text-sm leading-relaxed">
                  <button onClick={() => seek(sentence.start)} className="mr-2 font-mono text-xs opacity-60 hover:opacity-100">
                    {clock(sentence.start)}
                  </button>
                  {sentence.words.map((word, index) => (
                    <span key={index} className={now > 0 && now >= word.start && now < word.end ? "rounded bg-yellow-300/60 dark:bg-yellow-500/40" : ""}>
                      {word.text}{" "}
                    </span>
                  ))}
                </p>
              ))}
            </div>
          ))}
        </section>
      )}
    </main>
  );
}
