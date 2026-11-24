# The voiceover API (backend/) with FFmpeg, for Railway or any Docker host.
# The frontend (a test page) is deployed on its own.

# FFmpeg 9.0.2, a static build: the version the golden tests were made with.
FROM mwader/static-ffmpeg:9.0.2 AS ffmpeg

FROM python:3.13-slim
COPY --from=ffmpeg /ffmpeg /ffprobe /usr/local/bin/

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY config/ config/
COPY prompts/ prompts/
COPY assets/ assets/

# Jobs' files: mount a Railway volume at /data so they survive a redeploy.
ENV DATA_DIR=/data
WORKDIR /app/backend
EXPOSE 8000
# One process: jobs run in its background threads. Railway sets PORT.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
