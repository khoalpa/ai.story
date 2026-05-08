from pathlib import Path

APP_TITLE = "Render Audio Studio"
PHASE_ORDER = ["parse", "prepare", "tts", "mix", "subtitle"]
PHASE_LABELS = {
    "parse": "Parse script",
    "prepare": "Prepare segments",
    "tts": "Render TTS",
    "mix": "Mix audio",
    "subtitle": "Write subtitles",
}
DEFAULT_STORE_PATH = Path(".render_audio_gui/jobs.json")
DEFAULT_DOWNLOAD_NAME = "render_audio_outputs.zip"
