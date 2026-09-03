FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    espeak-ng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt piper-tts

COPY . .

EXPOSE 8000

CMD ["python", "-m", "webagent.cli", "--host", "0.0.0.0", "--port", "8000", "--no-browser"]
