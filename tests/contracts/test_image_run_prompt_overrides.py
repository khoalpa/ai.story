from __future__ import annotations

import importlib
import sys
import types


class SessionState(dict):
    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name, value):
        self[name] = value


def _install_streamlit(session_state: SessionState | None = None) -> None:
    sys.modules["streamlit"] = types.SimpleNamespace(session_state=session_state or SessionState())
    for name in ["image.gui.service"]:
        sys.modules.pop(name, None)


def test_apply_prompt_edit_allows_blank_prompt_dict() -> None:
    original_streamlit = sys.modules.get("streamlit")
    _install_streamlit()
    try:
        service = importlib.import_module("image.gui.service")

        patched = service._apply_prompt_edit(
            {"prompt": "original", "negative_prompt": "neg"},
            {"prompt": "", "negative_prompt": "edited neg"},
        )

        assert patched["prompt"] == ""
        assert patched["negative_prompt"] == "edited neg"
    finally:
        if original_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = original_streamlit


def test_apply_prompt_edit_allows_blank_prompt_string() -> None:
    original_streamlit = sys.modules.get("streamlit")
    _install_streamlit()
    try:
        service = importlib.import_module("image.gui.service")

        patched = service._apply_prompt_edit(
            {"prompt": "original", "negative_prompt": "neg"},
            "",
        )

        assert patched["prompt"] == ""
        assert patched["negative_prompt"] == "neg"
    finally:
        if original_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = original_streamlit


def test_apply_prompt_edit_merges_provider_payload_override() -> None:
    original_streamlit = sys.modules.get("streamlit")
    _install_streamlit()
    try:
        service = importlib.import_module("image.gui.service")

        patched = service._apply_prompt_edit(
            {
                "prompt": "original",
                "negative_prompt": "neg",
                "provider_payload": {"story_only": True, "guidance_scale": 6.5},
            },
            {
                "provider_payload": {"guidance_scale": 4.5, "eta": 0.2},
            },
        )

        assert patched["provider_payload"] == {
            "story_only": True,
            "guidance_scale": 4.5,
            "eta": 0.2,
        }
    finally:
        if original_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = original_streamlit


def test_run_image_job_rejects_empty_prompt_directory(tmp_path) -> None:
    from image.app_api import RenderImageRequest

    original_streamlit = sys.modules.get("streamlit")
    _install_streamlit()
    try:
        service = importlib.import_module("image.gui.service")

        prompt_dir = tmp_path / "prompts"
        prompt_dir.mkdir()

        try:
            service.run_image_job(
                RenderImageRequest(
                    provider="stable_diffusion_remote",
                    handoff_dir=prompt_dir,
                    output_dir=tmp_path / "output",
                )
            )
        except FileNotFoundError as exc:
            assert "does not contain any renderable prompt files" in str(exc)
        else:
            raise AssertionError("Expected empty prompt directory to be rejected")
    finally:
        if original_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = original_streamlit


def test_generated_output_variants_includes_batch_files(tmp_path) -> None:
    original_streamlit = sys.modules.get("streamlit")
    _install_streamlit()
    try:
        service = importlib.import_module("image.gui.service")
        primary = tmp_path / "scene_2.png"
        batch_2 = tmp_path / "scene_2_batch02.png"
        batch_3 = tmp_path / "scene_2_batch03.png"
        unrelated = tmp_path / "scene_3.png"
        for path in (primary, batch_2, batch_3, unrelated):
            path.write_bytes(path.name.encode("utf-8"))

        assert service._generated_output_variants(primary) == [primary, batch_2, batch_3]
    finally:
        if original_streamlit is None:
            sys.modules.pop("streamlit", None)
        else:
            sys.modules["streamlit"] = original_streamlit

