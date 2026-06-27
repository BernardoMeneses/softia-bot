FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    GAME_STATE_PATH=/data/game_state.json \
    SERVER_SETTINGS_PATH=/data/server_settings.json \
    FFMPEG_EXECUTABLE=ffmpeg

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY discord/requirements.txt /app/discord/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/discord/requirements.txt

COPY discord /app/discord
RUN mkdir -p /data

WORKDIR /app/discord
CMD ["python", "-m", "bot"]
