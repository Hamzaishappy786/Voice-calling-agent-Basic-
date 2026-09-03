# 🎙️ WebAgent — Real-Time Voice Assistant & Web Client

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**WebAgent** is a high-speed, real-time AI voice calling web application. It features streaming speech-to-text with **Cartesia Ink Whisper**, LLM intelligence with **Groq** (with **Gemini** fallback), and low-latency voice synthesis via **Cartesia / ElevenLabs / PiperTTS**.

---

## ✨ Highlights

- ⚡ **Real-Time Voice Calls**: Full-duplex WebSocket audio streaming (`16 kHz` mic capture, `24 kHz` raw PCM playback).
- 🧠 **Dual LLM Pipeline**: Fast Groq intelligence (`qwen/qwen3.6-27b`) with automatic failover to Google Gemini (`gemini-3.6-flash`).
- 🗣️ **Multi-Engine TTS**:
  - **Cartesia Sonic 3.6**
  - **ElevenLabs Flash v2.5**
  - **PiperTTS**: Fast local offline speech synthesis (**0 credit cost, 100% private**).
- 🛡️ **Offline Fallback**: Automatically switches voice generation to local **PiperTTS** if Cartesia or ElevenLabs API credits are exhausted.
- ⚙️ **In-App API Key Configuration**: Input and save API keys directly in the Web UI — no manual file editing required. Keys are stored locally in `.env`.
- 📊 **Live Credit Metering**: Real-time visual progress meters tracking available API credits.

---

## 🚀 Quick Start & Installation

### Option 1: 1-Click Launchers (Recommended)

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Hamzaishappy786/Voice-calling-agent-Basic-.git
   cd Voice-calling-agent-Basic-
   ```

2. **Run the launcher for your OS**:
   - **Windows**: Double-click `run.bat` or run:
     ```cmd
     .\run.bat
     ```
   - **Linux / macOS**:
     ```bash
     chmod +x run.sh
     ./run.sh
     ```

3. **Open Web UI**:
   Navigate to **`http://localhost:8000`** in your browser.

---

### Option 2: Manual Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Hamzaishappy786/Voice-calling-agent-Basic-.git
   cd Voice-calling-agent-Basic-
   ```

2. **Create virtual environment & install dependencies**:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux / macOS:
   source .venv/bin/activate

   pip install -r requirements.txt piper-tts
   ```

3. **Launch WebAgent server**:
   ```bash
   python app.py
   ```

4. **Access in Browser**:
   Open **`http://localhost:8000`**.

---

## ⚙️ In-App API Key Configuration

When you open **WebAgent** in your browser:
1. Click the **⚙️ API Keys** gear button in the top right corner.
2. Enter your API keys:
   - **Cartesia API Key** (`CARTESIA_API_KEY`)
   - **ElevenLabs API Key** (`ELEVENLABS_API_KEY`)
   - **Groq API Key** (`GROQ_API_KEY`)
   - **Gemini API Key** (`GEMINI_API_KEY`)
3. Click **Save & Apply Keys**. Keys will be saved locally to `.env` on disk and will automatically load on future runs.

---

## 📁 Repository Overview

```
Voice-calling-agent-Basic-/
├── app.py                # FastAPI server, WebSocket stream & fallback engine
├── cartesia_client.py    # Cartesia STT (Ink Whisper) & TTS (Sonic) client
├── elevenlabs_client.py  # ElevenLabs Flash v2.5 TTS client
├── piper_client.py       # PiperTTS local offline voice client & resampler
├── static/
│   └── index.html        # Web interface, AudioWorklet mic & player
├── run.bat               # Windows 1-click launcher
├── run.sh                # Linux/macOS 1-click launcher
├── .env.example          # Environment variables template
├── .gitignore            # Git exclusion rules
└── requirements.txt      # Python dependencies
```

---

## 📜 License

Distributed under the [MIT License](LICENSE).
