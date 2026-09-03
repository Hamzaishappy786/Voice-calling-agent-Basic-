#!/usr/bin/env python3
"""Thin PiperTTS client — local offline voice synthesis.

Loads local ONNX Piper models (e.g. ur_PK-fasih-medium.onnx) and streams raw
pcm_s16le audio resampled to 24000 Hz to match WebAgent audio player requirements.
"""

from __future__ import annotations

import io
import os
import sys
import wave
from pathlib import Path
from typing import Iterator, Optional, List, Dict

import numpy as np

try:
    from piper import PiperVoice, SynthesisConfig
    PIPER_AVAILABLE = True
except ImportError:
    PIPER_AVAILABLE = False
    PiperVoice = None
    SynthesisConfig = None

TTS_RATE = 24000

# Search paths for local Piper ONNX voice models
SEARCH_PATHS = [
    Path(r"D:\Pipecat replica - ticket lodging system\full sentence\models\piper"),
    Path(r"D:\Pipecat replica - ticket lodging system\Let's get it done\dist\BilingualDesk\_internal\models\piper"),
    Path(__file__).resolve().parent / "models",
    Path(__file__).resolve().parent,
]

class PiperError(RuntimeError):
    pass


def find_piper_models() -> List[Path]:
    """Find all local .onnx Piper voice model files."""
    models = []
    for path in SEARCH_PATHS:
        if path.exists():
            for f in path.glob("*.onnx"):
                if not f.name.endswith(".onnx.json"):
                    models.append(f)
    return models


def resample_pcm(pcm_int16: np.ndarray, orig_sr: int, target_sr: int = TTS_RATE) -> bytes:
    """Resample 1D int16 PCM array from orig_sr to target_sr using fast linear interpolation."""
    if orig_sr == target_sr or len(pcm_int16) == 0:
        return pcm_int16.tobytes()
    num_orig = len(pcm_int16)
    num_target = int(round(num_orig * target_sr / orig_sr))
    orig_indices = np.linspace(0, num_orig - 1, num_orig)
    target_indices = np.linspace(0, num_orig - 1, num_target)
    resampled = np.interp(target_indices, orig_indices, pcm_int16.astype(np.float32))
    return np.clip(resampled, -32768, 32767).astype(np.int16).tobytes()


class PiperTTS:
    def __init__(self, model_path: Optional[str | Path] = None, use_cuda: bool = False):
        if not PIPER_AVAILABLE:
            raise PiperError("piper-tts package is not installed. Install with 'pip install piper-tts'")
        
        self.model_path = self._resolve_model_path(model_path)
        try:
            self.voice = PiperVoice.load(str(self.model_path), use_cuda=use_cuda)
        except Exception as e:
            raise PiperError(f"Failed to load Piper model from {self.model_path}: {e}")
        
        self.orig_rate = self.voice.config.sample_rate

    def _resolve_model_path(self, explicit: Optional[str | Path]) -> Path:
        if explicit and Path(explicit).exists():
            return Path(explicit)
        
        available = find_piper_models()
        if available:
            return available[0]
            
        raise PiperError("No Piper .onnx voice model found in search paths.")

    def speak_stream(self, text: str, language: str = "ur") -> Iterator[bytes]:
        """Stream TTS audio chunks as pcm_s16le at 24000 Hz."""
        if not text.strip():
            return

        syn_config = SynthesisConfig() if SynthesisConfig else None
        
        try:
            for chunk in self.voice.synthesize(text, syn_config=syn_config):
                audio = chunk.audio_int16_array
                resampled_bytes = resample_pcm(audio, self.orig_rate, TTS_RATE)
                if resampled_bytes:
                    yield resampled_bytes
        except Exception as e:
            raise PiperError(f"Piper synthesis error: {e}")

    def speak_bytes(self, text: str, language: str = "ur") -> bytes:
        """One-shot synthesis returning all PCM bytes at 24000 Hz."""
        return b"".join(self.speak_stream(text, language))

    def voices(self) -> List[Dict[str, str]]:
        models = find_piper_models()
        out = []
        for m in models:
            name = m.stem.replace("-", " ").replace("_", " ").title()
            out.append({"id": str(m), "name": f"{name} (Local Piper)"})
        if not out:
            out.append({"id": str(self.model_path), "name": f"{self.model_path.stem} (Local Piper)"})
        return out

    def close(self):
        pass


if __name__ == "__main__":
    import time
    print("Testing PiperTTS...")
    try:
        piper = PiperTTS()
        print(f"Loaded Piper model: {piper.model_path} (Sample rate: {piper.orig_rate} Hz)")
        t0 = time.perf_counter()
        pcm = piper.speak_bytes("سلام، آپ کیسے ہیں؟")
        dur_s = len(pcm) / 2 / TTS_RATE
        print(f"Synthesized {len(pcm)} bytes ({dur_s:.2f} s of 24kHz audio) in {(time.perf_counter() - t0)*1000:.0f} ms")
    except Exception as err:
        print("Error testing PiperTTS:", err)
