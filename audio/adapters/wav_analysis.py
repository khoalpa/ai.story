from __future__ import annotations

import math
import struct
from pathlib import Path


def get_wav_duration_seconds(audio_path: Path) -> float | None:
    """Read WAV/RF64 duration without launching FFprobe.

    Supports PCM and IEEE-float WAV containers used by the render pipeline.
    """
    try:
        with audio_path.open("rb") as handle:
            header = handle.read(12)
            if len(header) != 12 or header[:4] not in {b"RIFF", b"RF64"} or header[8:12] != b"WAVE":
                return None
            byte_rate = 0
            data_size: int | None = None
            rf64_data_size: int | None = None
            while True:
                chunk_header = handle.read(8)
                if len(chunk_header) != 8:
                    break
                chunk_id, chunk_size = struct.unpack("<4sI", chunk_header)
                if chunk_id == b"ds64" and chunk_size >= 16:
                    payload = handle.read(chunk_size)
                    if len(payload) >= 16:
                        rf64_data_size = int(struct.unpack_from("<Q", payload, 8)[0])
                elif chunk_id == b"fmt " and chunk_size >= 16:
                    payload = handle.read(chunk_size)
                    if len(payload) >= 12:
                        byte_rate = int(struct.unpack_from("<I", payload, 8)[0])
                elif chunk_id == b"data":
                    data_size = rf64_data_size if chunk_size == 0xFFFFFFFF and rf64_data_size is not None else chunk_size
                    break
                else:
                    handle.seek(chunk_size, 1)
                if chunk_size & 1:
                    handle.seek(1, 1)
            if byte_rate <= 0 or data_size is None or data_size <= 0:
                return None
            return data_size / float(byte_rate)
    except (OSError, EOFError, struct.error):
        return None


def measure_wav_edge_silence(
    audio_path: Path,
    *,
    threshold_dbfs: float = -45.0,
    window_ms: int = 10,
) -> tuple[float, float]:
    """Measure leading and trailing silence in PCM or float WAV files."""
    try:
        raw = audio_path.read_bytes()
    except OSError:
        return 0.0, 0.0
    if len(raw) < 44 or raw[:4] not in {b"RIFF", b"RF64"} or raw[8:12] != b"WAVE":
        return 0.0, 0.0

    fmt: bytes | None = None
    data: bytes | None = None
    offset = 12
    while offset + 8 <= len(raw):
        chunk_id = raw[offset:offset + 4]
        chunk_size = struct.unpack_from("<I", raw, offset + 4)[0]
        chunk_start = offset + 8
        chunk_end = min(len(raw), chunk_start + chunk_size)
        if chunk_id == b"fmt ":
            fmt = raw[chunk_start:chunk_end]
        elif chunk_id == b"data":
            data = raw[chunk_start:chunk_end]
            break
        offset = chunk_start + chunk_size + (chunk_size & 1)

    if fmt is None or data is None or len(fmt) < 16:
        return 0.0, 0.0
    format_tag, channels, sample_rate, _byte_rate, block_align, bits = struct.unpack_from("<HHIIHH", fmt, 0)
    if format_tag == 0xFFFE and len(fmt) >= 26:
        format_tag = struct.unpack_from("<H", fmt, 24)[0]
    bytes_per_sample = bits // 8
    if channels <= 0 or sample_rate <= 0 or block_align <= 0 or bytes_per_sample not in {1, 2, 3, 4}:
        return 0.0, 0.0
    frame_count = len(data) // block_align
    if frame_count <= 0:
        return 0.0, 0.0

    def sample_value(sample: bytes) -> float:
        if format_tag == 3 and bits == 32:
            return float(struct.unpack("<f", sample)[0])
        if format_tag != 1:
            return 0.0
        if bits == 8:
            return (sample[0] - 128) / 128.0
        value = int.from_bytes(sample, byteorder="little", signed=True)
        return value / float(1 << (bits - 1))

    window_frames = max(1, int(sample_rate * max(1, window_ms) / 1000))
    threshold = 10.0 ** (float(threshold_dbfs) / 20.0)

    def window_is_active(first_frame: int, last_frame: int) -> bool:
        energy = 0.0
        count = 0
        for frame in range(first_frame, last_frame):
            frame_offset = frame * block_align
            for channel in range(channels):
                sample_offset = frame_offset + channel * bytes_per_sample
                value = sample_value(data[sample_offset:sample_offset + bytes_per_sample])
                energy += value * value
                count += 1
        return count > 0 and math.sqrt(energy / count) > threshold

    leading_frames = frame_count
    for first in range(0, frame_count, window_frames):
        last = min(frame_count, first + window_frames)
        if window_is_active(first, last):
            leading_frames = first
            break

    trailing_frames = frame_count
    last = frame_count
    while last > 0:
        first = max(0, last - window_frames)
        if window_is_active(first, last):
            trailing_frames = frame_count - last
            break
        last = first

    return leading_frames / float(sample_rate), trailing_frames / float(sample_rate)
