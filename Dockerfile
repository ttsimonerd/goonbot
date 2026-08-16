FROM python:3.10.13

# ffmpeg
RUN apt-get update && apt-get install -y ffmpeg build-essential libsndfile1 libopus-dev libffi-dev && apt-get clean

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# yt-dlp's extractors (YouTube/Spotify) break frequently, so always upgrade to
# the latest on rebuild. Placed after `COPY . .` so this layer is invalidated
# whenever the source changes instead of being served from Docker's cache.
RUN pip install --no-cache-dir -U yt-dlp

# The SQLite DB lives here. Mount a persistent volume at this exact path in
# Coolify (Storage tab -> Add Volume -> container path: /app/data)
RUN mkdir -p /app/data
ENV GOONBOT_DB_PATH=/app/data/goonbot.db

# The dashboard web server listens on this port
ENV PORT=3000
EXPOSE 3000

# --- Required secrets (set these in Coolify's Environment Variables tab) ---
ENV DISCORD_TOKEN=""
ENV SESSION_SECRET=""
ENV REDEPLOY_PASSWORD=""
ENV WEBHOOK_DEP=""
ENV NUKE_PASSWORD=""

CMD ["python3", "main.py"]
