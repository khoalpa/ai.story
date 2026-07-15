from __future__ import annotations

import argparse
import json
import tempfile
import wave
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _fixture(root: Path) -> dict[str, object]:
    """Exercise portable public handoff contracts without network credentials."""
    from PIL import Image
    from audio.app_api import write_video_handoff as write_audio_handoff
    from image.app_api import write_video_handoff as write_image_handoff
    from video.app_api import read_audio_handoff, read_image_handoff

    root.mkdir(parents=True, exist_ok=True)
    audio = root / "audio.wav"
    with wave.open(str(audio), "wb") as stream:
        stream.setparams((1, 2, 8000, 0, "NONE", "not compressed"))
        stream.writeframes(b"\0\0" * 800)
    scenes = root / "scenes"
    scenes.mkdir(exist_ok=True)
    Image.new("RGB", (360, 640), "navy").save(scenes / "01_opening.png")
    audio_manifest = write_audio_handoff(root / "audio_video_handoff.json", audio=audio)
    image_manifest = write_image_handoff(root / "image_video_handoff.json", cover=None, scenes=scenes)
    audio_bundle = read_audio_handoff(audio_manifest)
    image_bundle = read_image_handoff(image_manifest)
    return {
        "status": "passed",
        "mode": "fixture",
        "audio_manifest": str(audio_manifest),
        "image_manifest": str(image_manifest),
        "audio": str(audio_bundle.audio),
        "scenes": str(image_bundle.scenes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Story-to-Video E2E contract runner")
    parser.add_argument("--workspace", type=Path, help="Keep generated fixture files here")
    parser.add_argument("--report", type=Path, default=Path("e2e-report.json"))
    parser.add_argument("--dry-run", action="store_true", help="Validate the plan without providers")
    parser.add_argument("--fixture", action="store_true", help="Run deterministic offline handoffs")
    parser.add_argument("--skip-story", action="store_true")
    parser.add_argument("--skip-audio", action="store_true")
    parser.add_argument("--skip-image", action="store_true")
    parser.add_argument("--skip-video", action="store_true")
    args = parser.parse_args()
    started = datetime.now(timezone.utc).isoformat()
    if not args.fixture:
        result: dict[str, object] = {
            "status": "planned" if args.dry_run else "skipped",
            "mode": "dry-run" if args.dry_run else "provider",
            "reason": "Provider E2E requires explicit project inputs and credentials; use --fixture for offline CI.",
            "stages": {
                name: not getattr(args, f"skip_{name}")
                for name in ("story", "audio", "image", "video")
            },
        }
    elif args.workspace:
        result = _fixture(args.workspace.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="ai-story-e2e-") as temporary:
            result = _fixture(Path(temporary))
            result["ephemeral_workspace"] = True
    result["started_at"] = started
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] in {"passed", "planned"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
