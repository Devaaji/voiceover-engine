"""Test settings, set before the engine reads them (python-dotenv never overrides a variable that is set): a jobs
folder of the tests' own, the silent mock voice, a known API key, and the voice settings the golden fixtures were
made with."""

import os
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="voiceover-tests-")
os.environ["TTS_PROVIDER"] = "mock"
os.environ["API_KEY"] = "test-key"
os.environ["VOICE_TYPE"] = "teacher"
os.environ["VOICE_LEVELER"] = ""
os.environ["PAUSE_RHYTHM"] = "human"
os.environ["APPROVED_OPENING"] = ""
os.environ["CORS_ORIGINS"] = "http://localhost:3000"
os.environ["API_DOCS"] = "off"
os.environ["OPENING_LINE"] = "Hey guys! This is Ed Roh."
