#!/usr/bin/env python3
"""WebAgent — browser voice call backed by Cartesia STT + Groq + Cartesia/ElevenLabs TTS."""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import threading
from pathlib import Path
from typing import Optional

import httpx
import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

try:
    from webagent.cartesia_client import Cartesia, CartesiaError, TTS_RATE, pcm_to_wav
    from webagent.elevenlabs_client import ElevenLabs, ElevenLabsError
    from webagent.piper_client import PiperTTS, PiperError
except ImportError:
    from cartesia_client import Cartesia, CartesiaError, TTS_RATE, pcm_to_wav
    from elevenlabs_client import ElevenLabs, ElevenLabsError
    from piper_client import PiperTTS, PiperError

# ── env ──────────────────────────────────────────────────────────────────────

def load_env():
    for candidate in (HERE / ".env", HERE.parent / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

load_env()

# ── credit tracking (shared across all calls on this server process) ──────────

MIC_RATE = 16000

_credits = {
    "cartesia":   {"remaining": 10866.0, "max": 20000.0},
    "elevenlabs": {"remaining":  1712.0, "max": 10000.0},
}
_credits_lock = threading.Lock()


def deduct_credits(provider: str, reply_text: str, audio_dur_s: float):
    with _credits_lock:
        # STT always on Cartesia: 3 credits/sec
        _credits["cartesia"]["remaining"] = max(
            0.0, _credits["cartesia"]["remaining"] - audio_dur_s * 3.0
        )
        # TTS: 1 credit/char (Cartesia) or 0.5 credit/char (ElevenLabs Flash)
        tts_chars = len(reply_text)
        if provider == "car":
            _credits["cartesia"]["remaining"] = max(
                0.0, _credits["cartesia"]["remaining"] - tts_chars * 1.0
            )
        elif provider == "el":
            _credits["elevenlabs"]["remaining"] = max(
                0.0, _credits["elevenlabs"]["remaining"] - tts_chars * 0.5
            )
        # PiperTTS is local and unlimited (no credit deduction)


def credits_snapshot() -> dict:
    with _credits_lock:
        return {
            "type": "credits",
            "cartesia":   {"remaining": round(_credits["cartesia"]["remaining"]),
                           "max":       int(_credits["cartesia"]["max"])},
            "elevenlabs": {"remaining": round(_credits["elevenlabs"]["remaining"]),
                           "max":       int(_credits["elevenlabs"]["max"])},
            "piper":      {"remaining": "∞",
                           "max":       "Local"},
        }


# ── system prompt ─────────────────────────────────────────────────────────────

SYSTEM = (
    "You are a voice assistant. Rules you must never break:\n"
    "1. ONE sentence only. Never two.\n"
    "2. Under 12 words. Shorter is always better.\n"
    "3. No greetings, no filler ('sure!', 'of course!', 'great question!'), no sign-offs.\n"
    "4. No lists, no markdown, no emoji.\n"
    "Answer the question and stop."
)

# ── global clients (initialised once at startup) ──────────────────────────────

_car:   Optional[Cartesia] = None
_el:    Optional[ElevenLabs] = None
_piper: Optional[PiperTTS] = None


def get_car() -> Cartesia:
    global _car
    if _car is None:
        _car = Cartesia()
    return _car


def get_el() -> Optional[ElevenLabs]:
    global _el
    if _el is None:
        try:
            _el = ElevenLabs()
        except Exception as e:
            print("ElevenLabs unavailable:", e)
    return _el


def get_piper() -> Optional[PiperTTS]:
    global _piper
    if _piper is None:
        try:
            _piper = PiperTTS()
        except Exception as e:
            print("PiperTTS unavailable:", e)
    return _piper

# ── groq + gemini fallback ────────────────────────────────────────────────────

GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL   = "qwen/qwen3.6-27b"
GEMINI_URL   = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
GEMINI_MODEL = "gemini-3.6-flash"


class _RateLimitError(Exception):
    pass

SENTENCE_END = re.compile(r"[.!?؟۔\n]")
CLAUSE_END   = re.compile(r"[,،;:]")
ARABIC       = re.compile(r"[؀-ۿݐ-ݿ]")


def script_lang(text: str, default: str = "en") -> str:
    if not text.strip():
        return default
    urdu  = len(ARABIC.findall(text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if urdu == 0:
        return "en"
    if latin == 0:
        return "ur"
    return "ur" if urdu >= latin * 0.4 else "en"


def _groq_stream_sync(http: httpx.Client, messages: list):
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY missing")

    payload = {
        "model": GROQ_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 200,
        "stream": True,
        "reasoning_effort": "none",
    }

    def attempt(body):
        with http.stream(
            "POST", GROQ_URL,
            headers={"Authorization": "Bearer " + key},
            json=body, timeout=30.0,
        ) as resp:
            if resp.status_code >= 400:
                resp.read()
                if resp.status_code == 429:
                    raise _RateLimitError()
                if resp.status_code == 400 and "reasoning_effort" in body:
                    return 400
                raise RuntimeError("Groq %s: %s" % (resp.status_code, resp.text[:200]))
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if not chunk or chunk == "[DONE]":
                    continue
                try:
                    ev = json.loads(chunk)
                except ValueError:
                    continue
                for c in ev.get("choices", []):
                    p = (c.get("delta") or {}).get("content")
                    if p:
                        yield p
        return None

    if (yield from attempt(payload)) == 400:
        payload.pop("reasoning_effort")
        yield from attempt(payload)

def _gemini_stream_sync(http: httpx.Client, messages: list):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY missing — add it to .env to enable Gemini fallback")

    payload = {
        "model": GEMINI_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 200,
        "stream": True,
    }
    with http.stream(
        "POST", GEMINI_URL,
        headers={"Authorization": "Bearer " + key},
        json=payload, timeout=30.0,
    ) as resp:
        if resp.status_code >= 400:
            resp.read()
            raise RuntimeError("Gemini %s: %s" % (resp.status_code, resp.text[:200]))
        for line in resp.iter_lines():
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if not chunk or chunk == "[DONE]":
                continue
            try:
                ev = json.loads(chunk)
            except ValueError:
                continue
            for c in ev.get("choices", []):
                p = (c.get("delta") or {}).get("content")
                if p:
                    yield p


# ── audio helpers ─────────────────────────────────────────────────────────────

MIC_RATE       = 16000
THRESHOLD      = 0.045   # raised — office background noise sits around 0.01–0.025
SILENCE_FRAMES = 38      # 38 × 32 ms ≈ 1.2 s of quiet → end of turn
MAX_PREROLL    = 10      # ~320 ms of audio kept before speech trigger
MIN_SPEECH_RUN = 6       # need 6 consecutive loud frames (~190 ms) to confirm real speech
MIN_AUDIO_S    = 0.8     # discard clips shorter than 0.8 s — almost always noise
MIN_TEXT_CHARS = 8       # discard STT results shorter than this — noise hallucination


async def collect_utterance(ws: WebSocket) -> Optional[bytes]:
    frames      = []
    preroll     = []
    speaking    = False
    silence     = 0
    speech_run  = 0      # consecutive frames above threshold

    while True:
        try:
            msg = await asyncio.wait_for(ws.receive(), timeout=15.0)
        except asyncio.TimeoutError:
            return None

        if "text" in msg:
            try:
                ctrl = json.loads(msg["text"])
                if ctrl.get("type") == "end_call":
                    return None
            except Exception:
                pass
            continue

        raw   = msg.get("bytes") or msg.get("data")
        if raw is None:
            continue
        audio = np.frombuffer(raw, dtype=np.int16)
        rms   = float(np.sqrt(np.mean((audio.astype(np.float32) / 32768.0) ** 2)))

        if not speaking:
            preroll.append(audio.copy())
            if len(preroll) > MAX_PREROLL:
                preroll.pop(0)

            if rms > THRESHOLD:
                speech_run += 1
            else:
                speech_run = 0   # reset — brief spike, not real speech

            if speech_run >= MIN_SPEECH_RUN:
                speaking = True
                speech_run = 0
                frames.extend(preroll)
                frames.append(audio.copy())
        else:
            frames.append(audio.copy())
            if rms < THRESHOLD:
                silence += 1
                if silence >= SILENCE_FRAMES:
                    break
            else:
                silence = 0

    if not frames:
        return None
    audio = np.concatenate(frames)
    if len(audio) < int(MIN_AUDIO_S * MIC_RATE):
        return None
    return pcm_to_wav(audio.tobytes(), rate=MIC_RATE)


async def stream_reply(ws: WebSocket, tts, messages: list) -> str:
    """Run Groq + TTS in a background thread; stream PCM audio back over WebSocket."""
    loop       = asyncio.get_event_loop()
    audio_q: asyncio.Queue = asyncio.Queue()
    reply_parts: list[str] = []

    def producer():
        http = httpx.Client()
        try:
            pending  = ""
            first    = True
            thinking = False

            def _iter_brain():
                try:
                    yield from _groq_stream_sync(http, messages)
                except _RateLimitError:
                    asyncio.run_coroutine_threadsafe(
                        ws.send_json({"type": "info", "msg": "Groq rate limit - switching to Gemini"}), loop
                    )
                    yield from _gemini_stream_sync(http, messages)

            for piece in _iter_brain():
                if not reply_parts and not thinking and (pending + piece).lstrip().startswith("<think"):
                    thinking = True
                if thinking:
                    pending += piece
                    end = pending.find("</think>")
                    if end >= 0:
                        pending  = pending[end + 8:].lstrip()
                        thinking = False
                    continue

                pending += piece
                reply_parts.append(piece)

                while True:
                    match = SENTENCE_END.search(pending)
                    cut   = None
                    if match and match.end() >= 8:
                        cut = match.end()
                    elif first and len(pending) >= 25:
                        cl  = CLAUSE_END.search(pending)
                        cut = cl.end() if cl else (pending.rfind(" ", 0, 60) or None)

                    if not cut:
                        break

                    sentence = pending[:cut].strip()
                    pending  = pending[cut:]
                    first    = False
                    if not sentence:
                        continue

                    _tts_sentence(tts, sentence, audio_q, loop)

            if pending.strip():
                _tts_sentence(tts, pending.strip(), audio_q, loop)

        except Exception as exc:
            asyncio.run_coroutine_threadsafe(
                audio_q.put({"error": str(exc)}), loop
            )
        finally:
            asyncio.run_coroutine_threadsafe(audio_q.put(None), loop)
            http.close()

    t = threading.Thread(target=producer, daemon=True)
    t.start()

    while True:
        item = await audio_q.get()
        if item is None:
            break
        if isinstance(item, dict):
            await ws.send_json({"type": "error", "msg": item.get("error", "TTS error")})
            continue
        await ws.send_bytes(item)

    t.join()
    return "".join(reply_parts).strip()


def _tts_sentence(tts, sentence: str, q: asyncio.Queue, loop):
    lang     = script_lang(sentence)
    leftover = b""
    try:
        for pcm in tts.speak_stream(sentence, lang):
            pcm = leftover + pcm
            if len(pcm) % 2:
                leftover = pcm[-1:]
                pcm      = pcm[:-1]
            else:
                leftover = b""
            if pcm:
                asyncio.run_coroutine_threadsafe(q.put(pcm), loop)
    except Exception as exc:
        piper = get_piper()
        if piper and tts is not piper:
            asyncio.run_coroutine_threadsafe(
                q.put({"type": "info", "msg": f"TTS error — switching to PiperTTS fallback"}), loop
            )
            try:
                for pcm in piper.speak_stream(sentence, lang):
                    pcm = leftover + pcm
                    if len(pcm) % 2:
                        leftover = pcm[-1:]
                        pcm      = pcm[:-1]
                    else:
                        leftover = b""
                    if pcm:
                        asyncio.run_coroutine_threadsafe(q.put(pcm), loop)
                return
            except Exception as p_exc:
                exc = p_exc
        asyncio.run_coroutine_threadsafe(q.put({"error": str(exc)}), loop)

# ── FastAPI ───────────────────────────────────────────────────────────────────

app = FastAPI()
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")


def mask_secret(s: str) -> str:
    if not s:
        return ""
    if len(s) < 8:
        return "••••••••"
    return s[:4] + "••••••••" + s[-4:]


def update_env_file(new_keys: dict):
    env_path = HERE / ".env"
    existing_lines = []
    if env_path.exists():
        existing_lines = env_path.read_text(encoding="utf-8").splitlines()
    
    updated_keys = set()
    new_lines = []
    
    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            k, _, _ = line.partition("=")
            key_name = k.strip()
            if key_name in new_keys:
                val = new_keys[key_name]
                new_lines.append(f"{key_name}={val}")
                os.environ[key_name] = val
                updated_keys.add(key_name)
                continue
        new_lines.append(line)
    
    for k, v in new_keys.items():
        if k not in updated_keys and v:
            new_lines.append(f"{k}={v}")
            os.environ[k] = v
            
    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


@app.get("/")
async def index():
    return FileResponse(HERE / "static" / "index.html")


@app.get("/credits")
async def get_credits():
    return JSONResponse(credits_snapshot())


@app.get("/settings")
async def get_settings():
    return JSONResponse({
        "cartesia_key": mask_secret(os.environ.get("CARTESIA_API_KEY", "")),
        "elevenlabs_key": mask_secret(os.environ.get("ELEVENLABS_API_KEY", "")),
        "groq_key": mask_secret(os.environ.get("GROQ_API_KEY", "")),
        "gemini_key": mask_secret(os.environ.get("GEMINI_API_KEY", "")),
        "has_cartesia": bool(os.environ.get("CARTESIA_API_KEY")),
        "has_elevenlabs": bool(os.environ.get("ELEVENLABS_API_KEY")),
        "has_groq": bool(os.environ.get("GROQ_API_KEY")),
        "has_gemini": bool(os.environ.get("GEMINI_API_KEY")),
    })


@app.post("/settings")
async def save_settings(req: Request):
    data = await req.json()
    new_keys = {}
    
    c_key = data.get("cartesia_key", "").strip()
    if c_key and "•" not in c_key:
        new_keys["CARTESIA_API_KEY"] = c_key
        
    e_key = data.get("elevenlabs_key", "").strip()
    if e_key and "•" not in e_key:
        new_keys["ELEVENLABS_API_KEY"] = e_key
        
    g_key = data.get("groq_key", "").strip()
    if g_key and "•" not in g_key:
        new_keys["GROQ_API_KEY"] = g_key
        
    gem_key = data.get("gemini_key", "").strip()
    if gem_key and "•" not in gem_key:
        new_keys["GEMINI_API_KEY"] = gem_key

    if new_keys:
        update_env_file(new_keys)
        global _car, _el
        _car = None
        _el = None

    return JSONResponse({"status": "ok", "saved_count": len(new_keys)})


@app.get("/voices")
async def get_voices():
    out = {"cartesia": [], "elevenlabs": [], "piper": []}
    try:
        out["cartesia"] = [
            {"id": v.get("id", ""), "name": v.get("name", "?")}
            for v in get_car().voices(limit=20)
        ]
    except Exception as e:
        out["cartesia_error"] = str(e)

    el = get_el()
    if el:
        try:
            out["elevenlabs"] = [
                {"id": v.get("voice_id", ""), "name": v.get("name", "?")}
                for v in el.voices(limit=20)
            ]
        except Exception as e:
            out["elevenlabs_error"] = str(e)

    piper = get_piper()
    if piper:
        try:
            out["piper"] = piper.voices()
        except Exception as e:
            out["piper_error"] = str(e)

    return JSONResponse(out)


def select_tts_engine(provider: str, voice_id: Optional[str] = None):
    piper = get_piper()
    
    if provider in ("piper", "pip"):
        if piper:
            return piper, "piper"
        return get_car(), "car"
    
    if provider == "el":
        if _credits["elevenlabs"]["remaining"] > 0:
            el = get_el()
            if el:
                return (ElevenLabs(voice=voice_id) if voice_id else el), "el"
        if piper:
            return piper, "piper"
        return get_car(), "car"
    
    # cartesia (default)
    if _credits["cartesia"]["remaining"] > 0:
        return (Cartesia(voice=voice_id) if voice_id else get_car()), "car"
    
    if piper:
        return piper, "piper"
    return get_car(), "car"


@app.websocket("/call")
async def call_ws(ws: WebSocket):
    await ws.accept()
    history = [{"role": "system", "content": SYSTEM}]

    try:
        cfg      = await asyncio.wait_for(ws.receive_json(), timeout=10.0)
        provider = cfg.get("provider", "car")
        voice_id = cfg.get("voice_id")

        await ws.send_json({"type": "status", "value": "listening"})

        while True:
            wav = await collect_utterance(ws)
            if wav is None:
                break

            await ws.send_json({"type": "status", "value": "thinking"})

            audio_dur_s = (len(wav) - 44) / 2 / MIC_RATE

            try:
                text, _ = await asyncio.to_thread(
                    lambda: get_car().transcribe(wav, language="ur")
                )
            except CartesiaError as e:
                await ws.send_json({"type": "error", "msg": str(e)})
                await ws.send_json({"type": "status", "value": "listening"})
                continue

            # Select active TTS engine (auto fallback to Piper if credits exhausted)
            tts, active_provider = select_tts_engine(provider, voice_id)
            if active_provider == "piper" and provider != "piper":
                await ws.send_json({
                    "type": "info", 
                    "msg": "Credits exhausted — automatically using local PiperTTS"
                })

            # deduct STT cost immediately after transcription
            deduct_credits(active_provider, "", audio_dur_s)
            await ws.send_json(credits_snapshot())

            if len(text.strip()) < MIN_TEXT_CHARS:
                # too short — noise or silence hallucination, skip silently
                await ws.send_json({"type": "status", "value": "listening"})
                continue

            history.append({"role": "user", "content": text})
            await ws.send_json({"type": "status", "value": "speaking"})

            try:
                reply = await stream_reply(ws, tts, history)
            except Exception as e:
                await ws.send_json({"type": "error", "msg": str(e)})
                await ws.send_json({"type": "status", "value": "listening"})
                continue

            if reply:
                history.append({"role": "assistant", "content": reply})
                if len(history) > 11:
                    history = [history[0]] + history[-10:]
                # deduct TTS cost after full reply is known
                deduct_credits(active_provider, reply, 0.0)
                await ws.send_json(credits_snapshot())

            await ws.send_json({"type": "status", "value": "listening"})

    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception as e:
        try:
            await ws.send_json({"type": "error", "msg": str(e)})
        except Exception:
            pass
