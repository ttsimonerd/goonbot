FROM python:3.10.13

RUN apt-get update && apt-get install -y ffmpeg build-essential libsndfile1 && apt-get clean

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ..

CMD ["python3", "main.py"]
