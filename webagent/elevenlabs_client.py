#!/usr/bin/env python3
"""Thin ElevenLabs TTS client — Flash v2.5 streaming only.

Only text-to-speech is implemented here. STT stays on Cartesia Ink Whisper
for both providers so the comparison is apples-to-apples (TTS leg only).
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

API = "https://api.elevenlabs.io"

# Flash v2.5 — 0.5 credits/char on the free tier (so 20K chars free/month).
DEFAULT_MODEL = "eleven_flash_v2_5"

# No hardcoded voice — free accounts cannot use library voices via API.
# ElevenLabs() picks from the account's available premade voices at startup,
# preferring neutral/informative voices good for a call center context.
DEFAULT_VOICE = None

# Preferred premade voice IDs, in priority order (all confirmed free-tier):
# River → Daniel → Sarah → Jessica → any premade → whatever is first.
PREFERRED_VOICES = [
    "SAz9YHcvj6GT2YYXdXww",  # River   — Relaxed, Neutral, Informative
    "onwK4e9ZLuTAKqWW03F9",  # Daniel  — Steady Broadcaster
    "EXAVITQu4vr4xnSDxMaL",  # Sarah   — Mature, Reassuring
    "cgSgspJ2msm6clMCkdW9",  # Jessica — Playful, Bright, Warm
]

# Match Cartesia's output rate so the same sounddevice stream can play both.
TTS_RATE = 24000


class ElevenLabsError(RuntimeError):
    pass


def load_key(explicit=None):
    if explicit:
        return explicit.strip()
    if os.environ.get("ELEVENLABS_API_KEY"):
        return os.environ["ELEVENLABS_API_KEY"].strip()

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
                if key.strip() == "ELEVENLABS_API_KEY" and value.strip():
                    return value.strip()
    raise ElevenLabsError(
        "No ElevenLabs key. Put ELEVENLABS_API_KEY=sk_... in TTS-Compare/.env"
    )


class ElevenLabs:
    def __init__(self, key=None, voice=None, model=None, timeout=30.0):
        self.key = load_key(key)
        self.model = model or DEFAULT_MODEL
        self._http = httpx.Client(timeout=timeout)
        # Resolve voice: explicit > env/arg > first voice on the account.
        # Library voices are paid-only; auto-pick uses whatever the account owns.
        self.voice = voice or self._pick_voice()

    def _pick_voice(self):
        """Pick the best available voice: preferred list → any premade → first."""
        try:
            available = self.voices(limit=50)
        except Exception:
            raise ElevenLabsError(
                "Could not list ElevenLabs voices — check your API key."
            )
        if not available:
            raise ElevenLabsError(
                "No ElevenLabs voices found on this account. "
                "Log in at elevenlabs.io, create or clone a voice, then retry."
            )

        by_id = {v["voice_id"]: v for v in available}

        # Try preferred list first.
        for vid in PREFERRED_VOICES:
            if vid in by_id:
                v = by_id[vid]
                print("  ElevenLabs voice: %s — %s" % (v.get("name", "?"), vid))
                return vid

        # Fall back to any premade voice, then literally anything.
        premade = [v for v in available if v.get("category") == "premade"]
        chosen = (premade or available)[0]
        print(
            "  ElevenLabs voice: %s — %s"
            % (chosen.get("name", "?"), chosen.get("voice_id", "?"))
        )
        return chosen["voice_id"]

    def _headers(self):
        return {
            "xi-api-key": self.key,
            "Content-Type": "application/json",
        }

    def close(self):
        self._http.close()

    def speak_stream(self, text, language="en"):
        """Stream TTS audio, yielding raw pcm_s16le chunks at TTS_RATE.

        output_format is a query parameter, not a body field — if it ends up
        in the JSON body ElevenLabs ignores it and returns MP3 by default,
        which sounds like static when played as raw PCM.
        """
        url = "%s/v1/text-to-speech/%s/stream" % (API, self.voice)
        params = {"output_format": "pcm_%d" % TTS_RATE}
        body = {
            "text": text,
            "model_id": self.model,
        }
        with self._http.stream(
            "POST", url, headers=self._headers(), params=params, json=body
        ) as resp:
            if resp.status_code >= 400:
                resp.read()
                raise ElevenLabsError(
                    "EL TTS HTTP %s: %s" % (resp.status_code, resp.text[:300])
                )
            for chunk in resp.iter_bytes(chunk_size=4096):
                if chunk:
                    yield chunk

    def speak_bytes(self, text, language="en"):
        """One-shot synth — returns all PCM at once (slower, for benchmarks)."""
        url = "%s/v1/text-to-speech/%s" % (API, self.voice)
        params = {"output_format": "pcm_%d" % TTS_RATE}
        body = {"text": text, "model_id": self.model}
        resp = self._http.post(url, headers=self._headers(), params=params, json=body)
        if resp.status_code >= 400:
            raise ElevenLabsError(
                "EL TTS HTTP %s: %s" % (resp.status_code, resp.text[:300])
            )
        return resp.content

    def voices(self, limit=20):
        resp = self._http.get(
            "%s/v1/voices" % API,
            headers=self._headers(),
        )
        if resp.status_code >= 400:
            raise ElevenLabsError(
                "EL voices HTTP %s: %s" % (resp.status_code, resp.text[:300])
            )
        return resp.json().get("voices", [])[:limit]


if __name__ == "__main__":
    import time
    el = ElevenLabs()
    print("key ok:", el.key[:8] + "...")
    t0 = time.perf_counter()
    audio = el.speak_bytes("ElevenLabs is connected.")
    print(
        "tts/bytes: %d bytes (%.2f s) in %.0f ms"
        % (len(audio), len(audio) / 2 / TTS_RATE, (time.perf_counter() - t0) * 1000)
    )
