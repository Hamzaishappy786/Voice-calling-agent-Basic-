#!/usr/bin/env python3
"""Thin Cartesia client: speech-to-text (Ink Whisper) and text-to-speech (Sonic).

Nothing here touches the desk package -- it is a standalone probe so we can
measure Cartesia's real latency before wiring it into the pipeline.
"""

from __future__ import annotations

import base64
import io
import json
import os
import time
import wave
from pathlib import Path

import httpx
from concurrent.futures import ThreadPoolExecutor

API = "https://api.cartesia.ai"
VERSION = "2026-08-14"

# Sonic voice from the Cartesia docs; swap with `python talk.py voices`.
DEFAULT_VOICE = "db6b0ed5-d5d3-463d-ae85-518a07d3c2b4"
DEFAULT_TTS_MODEL = "sonic-3.6"
STT_MODEL = "ink-whisper"

# Sonic speaks back as raw signed 16-bit PCM so we can hand it straight to the
# sound card -- no mp3 decode step in the hot path.
TTS_RATE = 24000


class CartesiaError(RuntimeError):
    pass


def load_key(explicit=None):
    """Find the API key.

    The .env beside this file may hold either `CARTESIA_API_KEY=sk_car_...`
    or just the bare token on its own line.
    """
    if explicit:
        return explicit.strip()
    if os.environ.get("CARTESIA_API_KEY"):
        return os.environ["CARTESIA_API_KEY"].strip()

    here = Path(__file__).resolve().parent
    for candidate in (here / ".env", here.parent / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                if key.strip() == "CARTESIA_API_KEY" and value.strip():
                    return value.strip()
            elif line.startswith("sk_car_"):
                return line
    raise CartesiaError(
        "No Cartesia key. Put CARTESIA_API_KEY=sk_car_... in Cartesia/.env"
    )


class Cartesia:
    def __init__(self, key=None, voice=None, model=None, timeout=30.0):
        self.key = load_key(key)
        self.voice = voice or DEFAULT_VOICE
        self.model = model or DEFAULT_TTS_MODEL
        # One pooled client: reusing the TLS connection saves ~100 ms a turn.
        self._http = httpx.Client(timeout=timeout)

    def _headers(self, json_body=False):
        head = {
            "Cartesia-Version": VERSION,
            "Authorization": "Bearer %s" % self.key,
        }
        if json_body:
            head["Content-Type"] = "application/json"
        return head

    def close(self):
        self._http.close()

    # ---------------------------------------------------------------- STT

    def transcribe(self, wav_bytes, language="en", words=False):
        """Send a wav blob to Ink Whisper, get text back.

        Note there is no auto-detect: omitting `language`, or passing
        anything the API does not recognise, silently falls back to English.
        """
        files = {"file": ("speech.wav", wav_bytes, "audio/wav")}
        data = {"model": STT_MODEL}
        if language and language != "auto":
            data["language"] = language
        if words:
            data["timestamp_granularities[]"] = "word"

        resp = self._http.post(
            API + "/stt", headers=self._headers(), files=files, data=data
        )
        if resp.status_code >= 400:
            raise CartesiaError("STT HTTP %s: %s" % (resp.status_code, resp.text[:300]))
        body = resp.json()
        return (body.get("text") or "").strip(), body

    # ------------------------------------------------------ language pick

    def transcribe_auto(self, wav_bytes, languages=("en", "ur")):
        """Decode the clip in both languages at once and keep the better one.

        Ink Whisper has no auto-detect, and the two failure modes are ugly:
        forcing `en` on Urdu speech makes Whisper *translate* instead of
        transcribe, and forcing `ur` on English speech produces gibberish.

        So run both in parallel -- it costs one round trip, not two -- and then
        decide. The only signal that survives real use is a *looping* Urdu
        decode: the same token repeated over and over, which never happens on
        genuine Urdu speech.

        Two other signals were tried and dropped:

        * Word-timestamp coverage. Translation mode makes the timings collapse,
          which looked clean at first, but the range for real Urdu overlaps
          real English too much to threshold on. Reported for diagnostics only.
        * Length ratio (Urdu decode much shorter than the English one). This
          backfired on code-switched speech. "Hi, mein basta lena chah raha
          hoon" gave ur="مجھے" and en="Hi, may I be a secret?" -- one word
          against five, so the rule chose English, and English was a
          hallucination. A genuinely English clip produces the same signature,
          so the lengths carry no information either way.

        The tie therefore goes to Urdu. That is the deliberate bias: this desk
        serves Pakistani callers who code-switch constantly, and answering an
        English speaker in Urdu is a far smaller failure than the reverse.
        """
        with ThreadPoolExecutor(max_workers=len(languages)) as pool:
            jobs = {
                lang: pool.submit(self.transcribe, wav_bytes, lang, True)
                for lang in languages
            }
            results = {lang: job.result() for lang, job in jobs.items()}

        primary, secondary = languages[0], languages[1]
        (text_a, body_a), (text_b, body_b) = results[primary], results[secondary]

        cover_a = _coverage(body_a)
        loops_b = _repetition(text_b)
        ratio_b = len(text_b.split()) / max(1, len(text_a.split()))

        if loops_b > 0.4:
            chosen = primary
        else:
            chosen = secondary

        text = results[chosen][0]
        detail = {
            "chosen": chosen,
            "coverage_%s" % primary: round(cover_a, 2),
            "repetition_%s" % secondary: round(loops_b, 2),
            "length_ratio": round(ratio_b, 2),
            "candidates": {lang: results[lang][0] for lang in languages},
        }
        return text, chosen, detail

    # ---------------------------------------------------------------- TTS

    def _tts_body(self, text, language):
        return {
            "model_id": self.model,
            "transcript": text,
            "voice": self.voice,
            "language": language,
            "output_format": {
                "container": "raw",
                "encoding": "pcm_s16le",
                "sample_rate": TTS_RATE,
            },
        }

    def speak_bytes(self, text, language="en"):
        """One-shot synth. Returns raw pcm_s16le at TTS_RATE."""
        resp = self._http.post(
            API + "/tts/bytes",
            headers=self._headers(json_body=True),
            json=self._tts_body(text, language),
        )
        if resp.status_code >= 400:
            raise CartesiaError("TTS HTTP %s: %s" % (resp.status_code, resp.text[:300]))
        return resp.content

    def speak_stream(self, text, language="en"):
        """Synth over SSE, yielding pcm as it is generated.

        This is the latency win: audio starts flowing before the sentence has
        finished rendering server-side.
        """
        with self._http.stream(
            "POST",
            API + "/tts/sse",
            headers=self._headers(json_body=True),
            json=self._tts_body(text, language),
        ) as resp:
            if resp.status_code >= 400:
                resp.read()
                raise CartesiaError(
                    "TTS HTTP %s: %s" % (resp.status_code, resp.text[:300])
                )
            for line in resp.iter_lines():
                if not line or not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                try:
                    event = json.loads(payload)
                except ValueError:
                    continue
                if event.get("type") == "error":
                    raise CartesiaError("TTS stream error: %s" % event)
                chunk = event.get("data")
                if chunk:
                    yield base64.b64decode(chunk)

    # -------------------------------------------------------------- voices

    def voices(self, limit=20):
        resp = self._http.get(
            API + "/voices/", headers=self._headers(), params={"limit": limit}
        )
        if resp.status_code >= 400:
            raise CartesiaError(
                "voices HTTP %s: %s" % (resp.status_code, resp.text[:300])
            )
        body = resp.json()
        return body.get("data", body if isinstance(body, list) else [])


# ---------------------------------------------------------------- signals


def _coverage(body):
    """How much of the clip the word timestamps actually account for.

    Near 1.0 when Whisper transcribed. Drops toward 0 when it translated,
    because the words stop lining up with the audio.
    """
    words = body.get("words") or []
    duration = body.get("duration") or 0
    if not words or duration <= 0:
        return 0.0
    span = words[-1].get("end", 0) - words[0].get("start", 0)
    return max(0.0, min(1.0, span / duration))


def _repetition(text):
    """Fraction of words that are duplicates -- a stuck decoder loops."""
    tokens = text.split()
    if len(tokens) < 4:
        return 0.0
    return 1.0 - (len(set(tokens)) / len(tokens))


# -------------------------------------------------------------------- wav


def pcm_to_wav(pcm, rate=16000, channels=1, width=2):
    """Wrap raw pcm_s16le in a wav container (stdlib only)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        out.writeframes(pcm)
    return buf.getvalue()


if __name__ == "__main__":
    # Smoke test: confirm the key works and time a short synth.
    car = Cartesia()
    print("key ok:", car.key[:12] + "...")
    start = time.perf_counter()
    audio = car.speak_bytes("Cartesia is connected.")
    print(
        "tts/bytes: %d bytes (%.2f s of audio) in %.0f ms"
        % (len(audio), len(audio) / 2 / TTS_RATE, (time.perf_counter() - start) * 1000)
    )
