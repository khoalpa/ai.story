from __future__ import annotations

import argparse
import os


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate canonical Audio Story authoring JSON and plain script for fictional story modes. "
            "Supports trend and calm modes, with trend as the default repo mode. "
            "Not for book-summary, factual explainer, self-help lesson, or case-study generation."
        ),
        epilog=(
            "Use --mode trend or --mode calm. If --brief is omitted, the CLI auto-loads the matching deterministic base-mode brief contract. "
            "If --system-prompt is omitted, the CLI auto-loads the matching base-mode prompt contract."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["trend", "calm"],
        default=os.getenv("AUDIO_STORY_MODE", "trend"),
        help="Base story mode. Controls deterministic default brief and default system prompt selection via this module's bundled assets.",
    )
    parser.add_argument("--brief", required=False, help="Path to brief .yml. Optional when using committed mode defaults.")
    parser.add_argument(
        "--output",
        required=True,
        help="Output base path without extension, e.g. stories/random_story (neutral fictional story output).",
    )
    parser.add_argument(
        "--system-prompt",
        default=None,
        help=(
            "Path to system prompt .txt (optional). "
            "If omitted, uses env AUDIO_STORY_SYSTEM_PROMPT, otherwise defaults to the selected --mode prompt file."
        ),
    )
    parser.add_argument("--validate", action="store_true", help="Run validate_plain_script.py on the generated plain script (.txt).")
    parser.add_argument("--retries", type=int, default=2, help="LLM retries if JSON/format violations occur during story generation.")
    parser.add_argument(
        "--chunked",
        action="store_true",
        help="Generate the story in chunks (recommended for local models with short output limits).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=60,
        help="Number of canonical script items to request per chunk when using --chunked.",
    )
    return parser
