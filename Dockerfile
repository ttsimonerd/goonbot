FROM python:3.10.13

# ffmpeg
RUN apt-get update && apt-get install -y ffmpeg build-essential libsndfile1 libopus-dev libffi-dev && apt-get clean

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The SQLite DB lives here. Mount a persistent volume at this exact path in
# Coolify (Storage tab -> Add Volume -> container path: /app/data), otherwise
# every redeploy wipes all balances/settings, same problem the JSON files had.
RUN mkdir -p /app/data
ENV GOONBOT_DB_PATH=/app/data/goonbot.db

# The dashboard's web server. In Coolify: set this app's "Port" to 8000 and
# attach your domain — this is what makes the dashboard reachable publicly.
ENV PORT=8000
EXPOSE 8000

CMD ["python3", "main.py"]
