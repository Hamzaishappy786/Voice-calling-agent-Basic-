# 🎙️ Voice Calling Agent — Real-Time AI Voice Assistant

[![PyPI / pip install](https://img.shields.io/badge/pip%20install-voice--calling--agent-brightgreen.svg)](https://github.com/Hamzaishappy786/Voice-calling-agent-Basic-)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Universal Wheel](https://img.shields.io/badge/wheel-py3--none--any-success.svg)](https://github.com/Hamzaishappy786/Voice-calling-agent-Basic-/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Voice Calling Agent** (`voice-calling-agent`) is a universal Python package and web app for real-time AI voice calling. It features speech-to-text with **Cartesia Ink Whisper**, fast LLM response generation with **Groq** (plus **Gemini** fallback), and streaming voice synthesis with **Cartesia / ElevenLabs / PiperTTS**.

> 💡 **Universal Python Compatibility**: The package is built as a universal wheel (`py3-none-any`), making it compatible with Python **3.8, 3.9, 3.10, 3.11, 3.12, and 3.13+** across Windows, Linux, and macOS.

---

## ⚡ Instant Installation & Run

Install directly from GitHub via `pip`:

```bash
pip install git+https://github.com/Hamzaishappy786/Voice-calling-agent-Basic-.git
```

Then run the application from any terminal:

```bash
voice-agent
```
*(Or alias: `webagent` or `python -m webagent`)*

This command starts the local backend server and **automatically opens your web browser** at `http://localhost:8000`.

---

## ✨ Features

- ⚡ **Real-Time Voice Calls**: Full-duplex WebSocket audio streaming (`16 kHz` mic input, `24 kHz` raw PCM playback).
- 🧠 **Dual LLM Engine**: High-speed Groq (`qwen/qwen3.6-27b`) with automatic failover to Google Gemini (`gemini-3.6-flash`).
- 🗣️ **Multi-Engine Voice Synthesis**:
  - **Cartesia Sonic 3.6**
  - **ElevenLabs Flash v2.5**
  - **PiperTTS**: Fast local offline speech synthesis (**0 credit cost, 100% private**).
- 🛡️ **Offline Failover**: Automatically switches to local **PiperTTS** if Cartesia or ElevenLabs API credits run out during a call.
- ⚙️ **In-App API Key Configuration**: Paste and save your API keys directly inside the Web UI — no manual file editing needed. Keys are saved locally in `.env`.
- 📊 **Live Credit Metering**: Real-time progress bars showing remaining API credits.

---

## ⚙️ In-App API Key Configuration

1. Launch `voice-agent` in your terminal.
2. When the web browser opens, click the **⚙️ API Keys** gear button in the top right corner.
3. Paste your API keys:
   - **Cartesia API Key** (`CARTESIA_API_KEY`)
   - **ElevenLabs API Key** (`ELEVENLABS_API_KEY`)
   - **Groq API Key** (`GROQ_API_KEY`)
   - **Gemini API Key** (`GEMINI_API_KEY`)
4. Click **Save & Apply Keys**. Keys are stored locally in `.env` and persist across restarts.

---

## 🛠️ Advanced CLI Options

```bash
# Run on a custom port
voice-agent --port 9000

# Run without automatically launching browser
voice-agent --no-browser

# Bind to a custom host
voice-agent --host 127.0.0.1 --port 8000
```

---

## 📁 Repository Structure

```
Voice-calling-agent-Basic-/
├── pyproject.toml        # Modern Python build & dependency spec
├── setup.py              # Packaging configuration & CLI entrypoints
├── webagent/
│   ├── __init__.py       # Package metadata
│   ├── __main__.py       # Module runner (`python -m webagent`)
│   ├── cli.py            # CLI command launcher (`voice-agent`)
│   ├── app.py            # FastAPI server & route handlers
│   ├── cartesia_client.py# Cartesia API integration
│   ├── elevenlabs_client.py# ElevenLabs API integration
│   ├── piper_client.py   # PiperTTS local integration
│   └── static/
│       └── index.html    # Glassmorphic Web App UI
├── run.bat               # Windows 1-click launcher
├── run.sh                # Linux/macOS 1-click launcher
└── README.md
```

---

## 📜 License

Distributed under the [MIT License](LICENSE).
