from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata
from importlib.metadata import PackageNotFoundError, version as pkg_version
from json import JSONDecodeError
from pathlib import Path
from typing import Callable, Dict, Optional

from audio.exceptions import (
    TtsAuthenticationError,
    TtsDependencyError,
    TtsError,
    TtsFallbackError,
    TtsNetworkError,
    TtsRateLimitError,
)
from audio.logging_utils import finish_cli_progress, get_logger, render_cli_progress
from audio.pipeline.segment_planner import Segment, VoiceTag

logger = get_logger(__name__)

DEFAULT_EN_VOICE_NARRATOR = "en-US-AriaNeural"
DEFAULT_VOICE_NARRATOR = "vi-VN-HoaiMyNeural"

try:
    import edge_tts
except ImportError:
    edge_tts = None


def get_installed_edge_tts_version() -> Optional[str]:
    try:
        return pkg_version("edge-tts")
    except PackageNotFoundError:
        return None
    except (OSError, ValueError):
        return None


def _parse_version_tuple(raw: Optional[str]):
    if not raw:
        return tuple()
    parts = re.findall(r"\d+", str(raw))
    return tuple(int(p) for p in parts[:4])


def is_edge_tts_version_older_than(min_version: str) -> bool:
    current = _parse_version_tuple(get_installed_edge_tts_version())
    minimum = _parse_version_tuple(min_version)
    if not current or not minimum:
        return False
    max_len = max(len(current), len(minimum))
    current = current + (0,) * (max_len - len(current))
    minimum = minimum + (0,) * (max_len - len(minimum))
    return current < minimum


def build_edge_tts_upgrade_hint() -> str:
    detected = get_installed_edge_tts_version() or "unknown"
    return (
        "The Edge TTS service is returning a 403 handshake error. "
        f"Installed edge-tts version: {detected}. "
        "This repo pins edge-tts==7.2.7, but this kind of 403 error often happens when the endpoint/protocol has changed. "
        "Upgrade edge-tts and run again, for example:\n"
        "  pip install -U edge-tts\n"
        "or pin an explicit newer version:\n"
        "  pip install -U edge-tts==7.2.7"
    )


def warn_if_edge_tts_looks_outdated() -> None:
    detected = get_installed_edge_tts_version()
    if detected and is_edge_tts_version_older_than("7.2.6"):
        logger.warning("edge-tts may be outdated (detected=%s). Upgrade if you hit 403 Invalid response status.", detected)


def load_abbreviation_map(path: Path) -> Dict[str, str]:
    if not path.is_file():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except (OSError, UnicodeDecodeError, JSONDecodeError):
        return {}
    return {}


def apply_abbreviation_mapping(text: str, abbr_map: Dict[str, str]) -> str:
    if not text or not abbr_map:
        return text
    out = text
    for k, v in abbr_map.items():
        pattern = re.compile(rf"\b{re.escape(k)}\b", re.IGNORECASE)
        out = pattern.sub(v, out)
    return out


def is_english_like(text: str, threshold: float = 0.7) -> bool:
    if not text:
        return False
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    ascii_letters = sum(1 for ch in letters if "a" <= ch.lower() <= "z")
    ratio = ascii_letters / max(1, len(letters))
    common_en = [" the ", " and ", " you ", " of ", " to ", " is ", " in ", " i "]
    text_l = f" {text.lower()} "
    return ratio >= threshold or any(tok in text_l for tok in common_en)


def _sanitize_for_edge_tts(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    replacements = {
        "‘": "'", "’": "'", "“": '"', "”": '"',
        "–": "-", "—": "-", "…": "...", " ": " ",
        "​": "", "‌": "", "‍": "", "﻿": "",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    cleaned: list[str] = []
    for ch in text:
        cat = unicodedata.category(ch)
        if ch in "\n\r\t " or (not cat.startswith("C") and cat != "So"):
            cleaned.append(ch)
    text = "".join(cleaned)
    text = text.replace("\r\n", " ").replace("\n", " ")
    text = "".join(ch if (ord(ch) >= 32 or ch in "\t ") else " " for ch in text)
    return re.sub(r"\s+", " ", text).strip()


def _preview_text(text: str, limit: int = 120) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip()
    return value if len(value) <= limit else value[: limit - 3] + "..."


def run_edge_tts_cli_fallback(text: str, voice_name: str, rate: str, out_wav: Path) -> None:
    safe_text = text.replace("\r\n", " ").replace("\n", " ")
    safe_text = "".join(ch if (ord(ch) >= 32 or ch in "\t ") else " " for ch in safe_text)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".txt") as tf:
        tf.write(safe_text)
        tmp_path = tf.name
    cmd = [
        sys.executable, "-m", "edge_tts",
        "--voice", voice_name,
        "--file", tmp_path,
        "--write-media", str(out_wav),
    ]
    rate = (rate or "").strip()
    if rate and rate != "0%":
        cmd.append(f"--rate={rate}")
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        os.remove(tmp_path)
    except OSError:
        pass
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode("utf-8", errors="ignore") + "\n")
        raise TtsFallbackError("Fallback CLI edge-tts failed")


async def tts_segment_to_file(
    seg: Segment,
    out_wav: Path,
    voice_map_vi: Dict[VoiceTag, str],
    voice_map_en: Dict[VoiceTag, str],
    abbr_map: Dict[str, str],
    auto_en_lines: bool = False,
) -> None:
    if not seg.text.strip("-–—*_ .·"):
        with open(out_wav, "wb") as f:
            f.write(b"")
        return

    effective_lang = seg.lang
    if auto_en_lines and not seg.lang_from_tag and is_english_like(seg.text):
        effective_lang = "en"

    voice_name = (
        voice_map_en.get(seg.voice, DEFAULT_EN_VOICE_NARRATOR)
        if effective_lang == "en"
        else voice_map_vi.get(seg.voice, DEFAULT_VOICE_NARRATOR)
    )
    rate = seg.rate or "0%"

    if edge_tts is None:
        raise TtsDependencyError("edge_tts is not installed. Run: pip install edge-tts")

    text_for_tts = apply_abbreviation_mapping(seg.text, abbr_map) if effective_lang == "en" else seg.text
    safe_text = _sanitize_for_edge_tts(text_for_tts)

    try:
        from edge_tts.exceptions import NoAudioReceived
    except (ImportError, AttributeError):
        class NoAudioReceived(Exception):
            pass

    async def _render_once(text_value: str) -> None:
        max_retries = 6
        backoff_sec = 2.0
        for attempt in range(1, max_retries + 1):
            try:
                communicate = edge_tts.Communicate(text=text_value, voice=voice_name, rate=rate)
                with open(out_wav, "wb") as f:
                    async for chunk in communicate.stream():
                        if chunk["type"] == "audio":
                            f.write(chunk["data"])
                return
            except (asyncio.TimeoutError, ConnectionError, OSError, RuntimeError, NoAudioReceived) as _e:
                msg = str(_e)
                transient = (
                    "503" in msg or "429" in msg or "Invalid response status" in msg or
                    "WSServerHandshakeError" in msg or "Timeout" in msg or "timed out" in msg
                )
                if transient and attempt < max_retries:
                    wait = backoff_sec * (2 ** (attempt - 1))
                    logger.warning("edge-tts transient error on attempt %s/%s: %s. Retry in %.1fs", attempt, max_retries, msg, wait)
                    await asyncio.sleep(wait)
                    continue
                raise

    try:
        await _render_once(safe_text)
    except (asyncio.TimeoutError, ConnectionError, OSError, RuntimeError, NoAudioReceived) as e:
        msg = str(e)
        if "No audio was received" in msg or isinstance(e, NoAudioReceived):
            normalized_text = _sanitize_for_edge_tts(seg.text)
            logger.warning(
                "edge_tts.Communicate returned no audio; segment preview=%r voice=%s rate=%s len=%s",
                _preview_text(seg.text),
                voice_name,
                rate,
                len(normalized_text),
            )
            if normalized_text and normalized_text != safe_text:
                try:
                    logger.info("Retry edge-tts with normalized text for segment preview=%r", _preview_text(normalized_text))
                    await _render_once(normalized_text)
                    return
                except (asyncio.TimeoutError, ConnectionError, OSError, RuntimeError, NoAudioReceived):
                    pass
            try:
                logger.warning("Falling back to CLI edge-tts renderer")
                run_edge_tts_cli_fallback(normalized_text or safe_text, voice_name, rate, out_wav)
                return
            except TtsFallbackError as fallback_exc:
                raise TtsFallbackError(
                    f"CLI edge-tts fallback failed for segment preview={_preview_text(seg.text)!r}"
                ) from fallback_exc
        elif "403" in msg and "Invalid response status" in msg:
            raise TtsAuthenticationError(build_edge_tts_upgrade_hint()) from e
        elif "429" in msg:
            raise TtsRateLimitError(msg) from e
        elif any(token in msg for token in ("503", "Timeout", "timed out", "WSServerHandshakeError", "Invalid response status")):
            raise TtsNetworkError(msg) from e
        else:
            raise


async def render_tts_all(
    segments,
    wav_dir: Path,
    voice_map_vi: Dict[VoiceTag, str],
    voice_map_en: Dict[VoiceTag, str],
    abbr_map: Dict[str, str],
    auto_en_lines: bool,
    max_concurrent_tts: int,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> None:
    total = len(segments)
    if total <= 0:
        logger.info("[TTS]   0%% (0 segments )")
        if progress_callback:
            progress_callback(0, 0)
        return

    sem = asyncio.Semaphore(max(1, int(max_concurrent_tts or 1)))
    progress_lock = asyncio.Lock()
    done = 0

    def _report_progress(done_count: int) -> None:
        pct = int(done_count * 100 / max(1, total))
        line = f"[TTS] {pct:3d}% ({done_count:3d}/{total:3d} segments)"
        if not render_cli_progress("TTS", line):
            logger.info("%s", line)
        if progress_callback:
            progress_callback(done_count, total)

    _report_progress(0)

    async def process_one(idx: int, seg: Segment) -> None:
        nonlocal done
        out_wav = wav_dir / f"seg_{idx:03d}.wav"
        async with sem:
            try:
                await tts_segment_to_file(
                    seg,
                    out_wav,
                    voice_map_vi,
                    voice_map_en,
                    abbr_map,
                    auto_en_lines=auto_en_lines,
                )
            except (TtsError, OSError, RuntimeError, asyncio.TimeoutError) as e:
                async with progress_lock:
                    pass
                logger.error("TTS failed at segment %s: %s", idx + 1, e)
                raise
        async with progress_lock:
            done += 1
            _report_progress(done)

    tasks = [asyncio.create_task(process_one(i, s)) for i, s in enumerate(segments)]
    try:
        await asyncio.gather(*tasks)
    finally:
        finish_cli_progress()
    logger.debug("TTS rendering completed for %s segments", total)
