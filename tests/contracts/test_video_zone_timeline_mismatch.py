import json
from pathlib import Path

import pytest

from video.zone_timeline import build_zone_segments


def test_zone_timeline_rejects_unrelated_story_and_subtitles(tmp_path: Path) -> None:
    timeline = tmp_path / "story.json"
    timeline.write_text(
        json.dumps(
            {
                "script": [
                    {"zone": "LỜI CHÀO", "text": "A shared opening sentence."},
                    {"zone": "MỞ TRUYỆN", "text": "Story A sentence two."},
                    {"zone": "KẾT TRUYỆN", "text": "Story A sentence three."},
                ]
            }
        ),
        encoding="utf-8",
    )
    subtitle = tmp_path / "story.srt"
    subtitle.write_text(
        "1\n00:00:09,000 --> 00:00:15,992\nA shared opening sentence.\n\n"
        "2\n00:00:15,992 --> 00:03:00,000\nAn unrelated story.\n",
        encoding="utf-8",
    )
    (tmp_path / "greeting.png").write_bytes(b"image")

    with pytest.raises(ValueError, match=r"different scripts.*matched only 1/3"):
        build_zone_segments(
            timeline_json=timeline,
            subtitle=subtitle,
            scenes_dir=tmp_path,
        )
