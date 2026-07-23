FROM python:3.10.13

# ffmpeg
RUN apt-get update && apt-get install -y ffmpeg build-essential libsndfile1 libopus-dev libffi-dev && apt-get clean

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Coolify (Storage tab -> Add Volume -> container path: /app/data)
RUN mkdir -p /app/data
ENV GOONBOT_DB_PATH=/app/data/goonbot.db

ENV PORT=3000
EXPOSE 3000

ENV OLLAMA_URL=http://localhost:11434
ENV OLLAMA_MODEL=qwen2.5:0.5b
ENV OLLAMA_SYSTEM_PROMPT=""

CMD ["python3", "main.py"]
