from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_offline_e2e_runner(tmp_path: Path) -> None:
    report = tmp_path / "report.json"
    workspace = tmp_path / "bundle"
    subprocess.run(
        [sys.executable, "scripts/run_story_to_video_e2e.py", "--fixture", "--workspace", str(workspace), "--report", str(report)],
        check=True,
    )
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "passed"
    assert Path(payload["audio_manifest"]).is_file()
    assert Path(payload["image_manifest"]).is_file()
