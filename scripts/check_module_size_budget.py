from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# These are ceilings, not targets. Reduce them whenever responsibilities move to
# dedicated modules; never raise one without an architecture review.
LINE_BUDGETS = {
    "audio/adapters/tts_core.py": 1360,
    "audio/adapters/ffmpeg_audio_mixer.py": 900,
    "audio/gui/settings.py": 1030,
    "video/gui/tabs.py": 1225,
}


def main() -> int:
    failures: list[str] = []
    for relative_path, budget in LINE_BUDGETS.items():
        path = ROOT / relative_path
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > budget:
            failures.append(f"{relative_path}: {line_count} lines exceeds budget {budget}")
    if failures:
        print("Module size budget failed:\n" + "\n".join(failures))
        return 1
    print(f"Module size budget passed for {len(LINE_BUDGETS)} modules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
