from __future__ import annotations

import io
import json
from pathlib import Path

from PIL import Image

from studio.summary_image_generation import render_summary_package
from studio.summary_image_provider import GeneratedImage, ImageGenerationRequest
from studio.summary_media import REVIEW_CHECKS
from studio.summary_stages import build_summary_stage1, build_summary_stage2
from tests.contracts.test_summary_projection import summary_fixture


def _png(*, portrait: bool = False) -> bytes:
    output = io.BytesIO()
    size = (90, 160) if portrait else (160, 90)
    Image.new("RGB", size, "navy").save(output, format="PNG")
    return output.getvalue()


class FakeProvider:
    name = "fake"

    def __init__(self, *, fail_first: bool = False) -> None:
        self.fail_first = fail_first
        self.requests: list[ImageGenerationRequest] = []

    def generate(self, request: ImageGenerationRequest) -> GeneratedImage:
        self.requests.append(request)
        if self.fail_first and len(self.requests) == 1:
            raise RuntimeError("temporary failure")
        return GeneratedImage(_png(portrait=request.orientation == "portrait"))


def test_renderer_generates_media_and_review_draft(tmp_path: Path) -> None:
    stage1 = build_summary_stage1(summary_fixture(), tmp_path / "stage1.zip")
    provider = FakeProvider()

    result = render_summary_package(
        stage1,
        tmp_path / "rendered",
        provider,
        orientation="landscape",
    )

    assert result.status == "COMPLETE"
    assert result.generated == 1
    assert (result.output_root / "landscape" / "scene_0001.png").is_file()
    review = json.loads(result.media_review_path.read_text(encoding="utf-8"))
    assert set(review["assets"][0]["checks"].values()) == {"NOT_CHECKED"}
    log = json.loads(result.render_log_path.read_text(encoding="utf-8"))
    assert log["assets"][0]["provider"] == "fake"
    assert provider.requests[0].metadata["pilot"] is True


def test_renderer_retries_tool_failure(tmp_path: Path) -> None:
    stage1 = build_summary_stage1(summary_fixture(), tmp_path / "stage1.zip")
    provider = FakeProvider(fail_first=True)

    result = render_summary_package(
        stage1,
        tmp_path / "rendered",
        provider,
        orientation="landscape",
        max_attempts=2,
    )

    assert result.status == "COMPLETE"
    assert len(provider.requests) == 2
    plan = json.loads(result.render_plan_path.read_text(encoding="utf-8"))
    assert plan["assets"][0]["attempt_count"] == 2
    assert plan["assets"][0]["status"] == "GENERATED"


def test_portrait_uses_inherited_landscape_reference(tmp_path: Path) -> None:
    stage1 = build_summary_stage1(summary_fixture(), tmp_path / "stage1.zip")
    landscape_root = tmp_path / "landscape-render"
    landscape = render_summary_package(
        stage1, landscape_root, FakeProvider(), orientation="landscape"
    )
    asset_id = json.loads(
        landscape.render_plan_path.read_text(encoding="utf-8")
    )["assets"][0]["asset_id"]
    approval = {
        "schema_version": "1.0.0",
        "assets": [
            {"asset_id": asset_id, "checks": {name: "PASS" for name in REVIEW_CHECKS}}
        ],
    }
    stage2 = build_summary_stage2(
        stage1, tmp_path / "stage2.zip", landscape_root, approval
    )
    provider = FakeProvider()
    portrait_root = tmp_path / "portrait-render"

    result = render_summary_package(
        stage2, portrait_root, provider, orientation="portrait"
    )

    reference = portrait_root / "landscape" / "scene_0001.png"
    assert result.status == "COMPLETE"
    assert reference.is_file()
    assert provider.requests[0].reference_paths == (reference,)
