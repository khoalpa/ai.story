from __future__ import annotations

import math
import struct
import wave
from pathlib import Path


def create_test_wav(
    path: str | Path,
    duration_sec: float = 0.5,
    sample_rate: int = 16_000,
    freq: float = 440.0,
    amplitude: float = 0.3,
) -> Path:
    """Create a small mono 16-bit PCM sine-wave WAV file for tests."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    safe_duration = max(0.0, float(duration_sec))
    safe_sample_rate = max(1, int(sample_rate))
    total_frames = int(round(safe_duration * safe_sample_rate))

    amp = max(0.0, min(1.0, float(amplitude)))
    peak = int(32767 * amp)

    with wave.open(str(out), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(safe_sample_rate)

        frames = bytearray()
        for i in range(total_frames):
            value = int(peak * math.sin(2.0 * math.pi * float(freq) * (i / safe_sample_rate)))
            frames.extend(struct.pack("<h", value))
        wf.writeframes(frames)

    return out



def create_test_ppm(path: str | Path, width: int = 16, height: int = 16) -> Path:
    """Create a tiny binary PPM image (P6) for smoke/integration tests."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    w = max(1, int(width))
    h = max(1, int(height))
    header = f"P6\n{w} {h}\n255\n".encode("ascii")

    pixels = bytearray()
    for y in range(h):
        for x in range(w):
            r = int((x / max(1, w - 1)) * 255) if w > 1 else 0
            g = int((y / max(1, h - 1)) * 255) if h > 1 else 0
            b = 128
            pixels.extend((r, g, b))

    out.write_bytes(header + pixels)
    return out
