from __future__ import annotations

import zipfile
import shutil
from io import BytesIO
from pathlib import Path


def test_story_output_bundle_can_be_story_only() -> None:
    from story.gui.split_jobs import build_story_output_bundle

    result = {
        "authoring": {"meta": {"title": "Split Story"}, "script": []},
        "plain_script": "TITLE: Split Story",
    }

    bundle = build_story_output_bundle(result)
    names = set(zipfile.ZipFile(BytesIO(bundle)).namelist())

    assert "story_authoring.json" in names
    assert "story_plain_script.txt" in names
    assert "cover_prompt.json" not in names
    assert "scene_prompt.json" not in names


def test_image_prompt_job_attaches_prompts_and_handoff(monkeypatch, tmp_path: Path) -> None:
    from story.gui import split_jobs

    result = {"authoring": {"meta": {"title": "Split Story"}}, "plain_script": "TITLE: Split Story"}
    prompts = {"cover": {"prompt": "cover"}, "scene": {"prompt": "scene"}}

    monkeypatch.setattr(split_jobs, "build_image_prompts", lambda authoring: prompts)
    monkeypatch.setattr(split_jobs, "materialize_story_handoff_bundle", lambda **kwargs: tmp_path / "bundle")

    bundle_dir = split_jobs.attach_image_prompts_and_handoff(result)

    assert bundle_dir == tmp_path / "bundle"
    assert result["image_prompts"] == prompts
    assert result["image_handoff_dir"] == str(tmp_path / "bundle")
    assert result["video_handoff_dir"] == str(tmp_path / "bundle")


def test_story_handoff_bundle_output_is_project_root_relative(monkeypatch) -> None:
    from story.gui.video_handoff import materialize_story_handoff_bundle
    from story.paths import PROJECT_ROOT

    monkeypatch.chdir(PROJECT_ROOT / "studio")

    bundle_dir = PROJECT_ROOT / "output" / "story" / "video_handoff" / "root-output-story"
    shutil.rmtree(bundle_dir, ignore_errors=True)
    try:
        actual_dir = materialize_story_handoff_bundle(
            authoring={"meta": {"title": "Root Output Story"}},
            image_prompts={"cover": {"prompt": "cover"}, "scene": {"prompt": "scene"}},
        )

        assert actual_dir == bundle_dir
        assert not str(actual_dir).startswith(str(PROJECT_ROOT / "studio" / "output"))
    finally:
        shutil.rmtree(bundle_dir, ignore_errors=True)


def test_story_image_prompts_use_canonical_outline_and_standard_payload() -> None:
    from common.image_sequence import ZONE_IMAGE_SEQUENCE
    from story.gui.image_prompts import build_image_prompts

    authoring = {
        "meta": {
            "title": "Canonical Visuals",
            "genre": "Mystery",
            "tone": "Quiet suspense",
            "audience": "Young adult",
            "language": "en",
        },
        "outline": {
            "greeting": "A warm host welcomes listeners into a misty town.",
            "opening": "A lantern flickers beside an old train platform.",
            "introduction": "The main character finds a sealed letter.",
            "development": "Clues point toward a forgotten family promise.",
            "climax": "The promise is revealed during a storm.",
            "falling": "The town gathers after the truth settles.",
            "ending": "The character chooses forgiveness.",
            "farewell": "The host closes with a gentle goodbye.",
        },
    }

    prompts = build_image_prompts(authoring)

    assert {"cover", "scene", "intro", *ZONE_IMAGE_SEQUENCE}.issubset(prompts)
    assert prompts["intro"]["outline_key"] == "opening"
    assert prompts["intro_card"]["outline_key"] == "opening"
    assert "A lantern flickers beside an old train platform" in prompts["intro_card"]["prompt"]
    assert "language context: English" in prompts["cover"]["prompt"]
    assert "masterpiece, best quality" in prompts["cover"]["prompt"]
    assert prompts["cover"]["provider_payload"]["target"] == "stable_diffusion_comfyui"
    assert prompts["cover"]["prompt_version"] == "story_image_prompt_v2"
    for key, payload in prompts.items():
        assert payload["title"] == "Canonical Visuals"
        assert payload["prompt"] == " ".join(payload["prompt"].split()), key
        assert payload["negative_prompt"]
        assert payload["width"] == 832
        assert payload["height"] == 1472
        assert payload["source_summary"]


def test_story_image_prompts_do_not_emit_non_english_prompt_text() -> None:
    from story.gui.image_prompts import build_image_prompts

    authoring = {
        "meta": {
            "title": "BÃ­ máº­t Ä‘Ãªm mÆ°a",
            "genre": "trinh thÃ¡m",
            "tone": "áº¥m Ã¡p, há»“i há»™p",
            "audience": "thiáº¿u niÃªn",
            "language": "vi",
        },
        "outline": {
            "greeting": "NgÆ°á»i dáº«n chuyá»‡n chÃ o khÃ¡n giáº£ trong má»™t thá»‹ tráº¥n mÆ°a.",
            "opening": "Má»™t chiáº¿c Ä‘Ã¨n lá»“ng cháº­p chá»n cáº¡nh sÃ¢n ga cÅ©.",
            "introduction": "NhÃ¢n váº­t chÃ­nh tÃ¬m tháº¥y má»™t lÃ¡ thÆ° niÃªm phong.",
            "development": "CÃ¡c manh má»‘i dáº«n Ä‘áº¿n má»™t lá»i há»©a gia Ä‘Ã¬nh bá»‹ lÃ£ng quÃªn.",
            "climax": "Sá»± tháº­t Ä‘Æ°á»£c hÃ© lá»™ giá»¯a cÆ¡n bÃ£o.",
            "falling": "Thá»‹ tráº¥n láº·ng Ä‘i sau khi má»i chuyá»‡n sÃ¡ng tá».",
            "ending": "NhÃ¢n váº­t chÃ­nh chá»n tha thá»©.",
            "farewell": "NgÆ°á»i dáº«n chuyá»‡n táº¡m biá»‡t báº±ng giá»ng dá»‹u dÃ ng.",
        },
    }

    prompts = build_image_prompts(authoring)

    for payload in prompts.values():
        assert payload["title"].isascii()
        assert payload["title"] == "Untitled story"
        assert payload["source_summary"].isascii()
        assert payload["prompt"].isascii()
        assert "tiáº¿ng" not in payload["prompt"].lower()
        assert "mÆ°a" not in payload["prompt"].lower()
        assert "trinh tham" not in payload["prompt"].lower()
        assert "am ap" not in payload["prompt"].lower()
        assert "masterpiece, best quality" in payload["prompt"]
        assert "stable_diffusion_comfyui" == payload["provider_payload"]["target"]


def test_story_summary_hides_image_video_until_prompt_handoff_ready() -> None:
    from story.gui.split_jobs import story_summary_action_labels, story_summary_download_labels

    result = {"image_prompts": {}, "image_handoff_dir": ""}

    assert story_summary_action_labels(result) == ["Send to Audio"]
    assert story_summary_download_labels(result) == [
        "Tải canonical JSON",
        "Tải gói ZIP kết quả",
    ]


def test_story_summary_shows_image_video_when_prompt_handoff_ready(tmp_path: Path) -> None:
    from story.gui.split_jobs import story_summary_action_labels, story_summary_download_labels

    result = {
        "image_prompts": {"cover": {"prompt": "cover"}, "scene": {"prompt": "scene"}},
        "image_handoff_dir": str(tmp_path / "bundle"),
    }

    assert story_summary_action_labels(result) == ["Send to Audio", "Send to Image", "Send to Video"]
    assert story_summary_download_labels(result) == [
        "Tải canonical JSON",
        "Tải gói ZIP kết quả",
        "Tải cover prompt",
        "Tải scene overview prompt",
    ]

