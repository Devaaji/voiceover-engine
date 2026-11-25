"""The API: the key on every endpoint, a job from request to files, with the silent mock voice (no credits)."""

import json
import time

import pytest
from fastapi.testclient import TestClient

import main
from voiceover.core import config

KEY = {"X-API-Key": "test-key"}


@pytest.fixture()
def client():
    with TestClient(main.app) as test_client:
        yield test_client


def wait_for(client: TestClient, job_id: str, seconds: float = 120) -> dict:
    deadline = time.time() + seconds
    while time.time() < deadline:
        job = client.get(f"/voiceover/{job_id}", headers=KEY).json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.5)
    raise AssertionError(f"the job did not finish in {seconds} s")


def test_every_endpoint_needs_the_key(client: TestClient) -> None:
    for method, url in [("post", "/voiceover"), ("get", "/voiceover/x"), ("get", "/voiceover/x/files/audio.mp3"), ("get", "/voice-types")]:
        assert getattr(client, method)(url).status_code == 401, url
        assert getattr(client, method)(url, headers={"X-API-Key": "wrong"}).status_code == 401, url
    assert client.get("/docs").status_code == 404


def test_without_api_key_on_the_server_everything_is_refused(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "API_KEY", "")
    assert client.get("/voice-types", headers=KEY).status_code == 503


def test_cors_lets_the_test_page_send_the_key(client: TestClient) -> None:
    preflight = client.options(
        "/voiceover",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "x-api-key,content-type"},
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_the_voice_type_from_env_is_marked_as_the_default(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    types = client.get("/voice-types", headers=KEY).json()
    assert [voice_type["id"] for voice_type in types if voice_type["default"]] == ["teacher"]
    monkeypatch.setattr(config, "VOICE_TYPE", "steady")
    types = client.get("/voice-types", headers=KEY).json()
    assert [voice_type["id"] for voice_type in types if voice_type["default"]] == ["steady"]


def test_bad_requests_are_explained(client: TestClient) -> None:
    assert client.post("/voiceover", headers=KEY, json={"mode": "script"}).status_code == 422
    assert client.post("/voiceover", headers=KEY, json={"script": "Hi.", "voiceType": "nope"}).status_code == 400
    content = client.post("/voiceover", headers=KEY, json={"mode": "content", "content": "Robots."})
    assert content.status_code == 400 and "not available yet" in content.json()["detail"]
    assert client.get("/voiceover/vo-nothing", headers=KEY).status_code == 404


def test_a_script_becomes_audio_and_a_timed_transcript(client: TestClient) -> None:
    script = "So this robot arm has three joints. Each one turns on its own motor.\n\nCan you guess which joint moves first? [pause] It's the base."
    created = client.post("/voiceover", headers=KEY, json={"script": script, "format": "wav"})
    assert created.status_code == 202
    job = wait_for(client, created.json()["id"])
    assert job["status"] == "done", job.get("error")
    assert job["voice"]["voice_type"] == "teacher" and "elevenlabs_api_key" not in job["voice"]
    assert set(job["files"]) == {"audio.wav", "transcript.json", "subtitles.srt", "subtitles.vtt"}

    audio = client.get(f"/voiceover/{job['id']}/files/audio.wav", headers=KEY)
    assert audio.status_code == 200 and audio.content[:4] == b"RIFF"
    transcript = json.loads(client.get(job["fileUrls"]["transcript.json"], headers=KEY).content)
    assert [segment["id"] for segment in transcript["segments"]] == ["s01", "s02"]
    # The script's words, without the mark; the pause is in the times.
    assert transcript["segments"][1]["text"] == "Can you guess which joint moves first? It's the base."
    sentences = [sentence for segment in transcript["segments"] for sentence in segment["sentences"]]
    starts = [sentence["start"] for sentence in sentences]
    assert starts == sorted(starts) and transcript["duration"] >= sentences[-1]["end"]
    assert all(sentence["words"] for sentence in sentences)
    vtt = client.get(f"/voiceover/{job['id']}/files/subtitles.vtt", headers=KEY).text
    assert vtt.startswith("WEBVTT") and "It's the base." in vtt
    assert client.get(f"/voiceover/{job['id']}/files/../job.json", headers=KEY).status_code == 404


def test_rewrite_puts_the_script_in_the_teachers_way_of_talking(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from voiceover.providers.script.writer import LLMResponse
    from writing import restyle

    class Writer:
        def complete_json(self, system: str, request: str, effort: str, model=None) -> LLMResponse:
            assert "the way the teacher talks" in system and effort == "medium"
            sent = json.loads(request)["scenes"]
            assert sent[0]["keep"] == ["Hey guys! This is Ed Roh."]
            answer = {"scenes": [{"id": "s01", "narration": "Hey guys! This is Ed Roh. So today we're gonna look at a robot arm with three joints."}]}
            return LLMResponse(json.dumps(answer), "claude-sonnet-5-5", 1000, 200, 0, 0, 0, "{}")

    monkeypatch.setattr(restyle, "writer", Writer)
    body = {"script": "Today we look at a robot arm. It has three joints.", "rewrite": True, "opening": True}
    job = wait_for(client, client.post("/voiceover", headers=KEY, json=body).json()["id"])
    assert job["status"] == "done", job.get("error")
    assert [call["purpose"] for call in job["claude_calls"]] == ["style"] and job["claude_cost_usd"] > 0
    transcript = json.loads(client.get(job["fileUrls"]["transcript.json"], headers=KEY).content)
    assert transcript["text"].startswith("Hey guys! This is Ed Roh. So today we're gonna")


def test_the_script_is_spoken_word_for_word_unless_rewrite_is_sent(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    from writing import restyle

    def no_claude():
        raise AssertionError("Claude was called without rewrite: true")

    monkeypatch.setattr(restyle, "writer", no_claude)
    created = client.post("/voiceover", headers=KEY, json={"segments": [{"text": "Wurds stay as they are.", "kind": "plain"}]})
    job = wait_for(client, created.json()["id"])
    assert job["status"] == "done", job.get("error")
    assert job["claude_calls"] == []
    transcript = json.loads(client.get(job["fileUrls"]["transcript.json"], headers=KEY).content)
    assert transcript["text"] == "Wurds stay as they are."
