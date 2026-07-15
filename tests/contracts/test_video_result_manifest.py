from __future__ import annotations

import hashlib
import json
from pathlib import Path

from video.app_api import write_result_manifest


def test_video_result_manifest_has_integrity_and_provenance(tmp_path: Path) -> None:
    video = tmp_path / "result.mp4"
    video.write_bytes(b"fixture-mp4")
    source = tmp_path / "audio.json"
    source.write_text("{}", encoding="utf-8")
    manifest = write_result_manifest(tmp_path / "result.json", video=video, input_manifests=[source], resolution="9x16")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["kind"] == "video.result-manifest"
    assert payload["artifacts"]["video"]["sha256"] == hashlib.sha256(video.read_bytes()).hexdigest()
    assert payload["metadata"]["resolution"] == "9x16"
    assert payload["provenance"]["input_manifests"] == [str(source.resolve())]
