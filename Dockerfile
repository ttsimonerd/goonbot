FROM python:3.10.13

# ffmpeg
RUN apt-get update && apt-get install -y ffmpeg build-essential libsndfile1 libopus-dev libffi-dev && apt-get clean

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

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
ENV SECRET_CMD_PASSWORD=""
ENV REDEPLOY_PASSWORD=""
ENV WEBHOOK_DEP=""
ENV NUKE_PASSWORD=""

# --- Optional: ClickUp integration ---
ENV CLICKUP_API_TOKEN=""
ENV CLICKUP_WORKSPACE_ID=""
ENV CLICKUP_DOC_ID=""
ENV CLICKUP_PAGE_ID=""

# --- Optional: n8n integration ---
ENV N8N_WEBHOOK_URL=""

# --- Ollama Local AI (defaults work if Ollama is on the same host) ---
ENV OLLAMA_URL=http://localhost:11434
ENV OLLAMA_MODEL=qwen2.5:0.5b
ENV OLLAMA_SYSTEM_PROMPT=""

CMD ["python3", "main.py"]
