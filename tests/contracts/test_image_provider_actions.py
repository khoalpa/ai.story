from __future__ import annotations

from typing import Iterable

from image.providers.registry import SDProvider


def test_advanced_payload_json_parser_accepts_objects() -> None:
    import image.gui.settings as settings

    payload, error = settings._parse_advanced_payload_json('{"guidance_scale": 5.5, "eta": 0.2}')

    assert error == ""
    assert payload == {"guidance_scale": 5.5, "eta": 0.2}


def test_advanced_payload_json_parser_rejects_non_objects() -> None:
    import image.gui.settings as settings

    payload, error = settings._parse_advanced_payload_json("[1, 2, 3]")

    assert payload == {}
    assert error == "Advanced payload JSON must be a JSON object."


def test_advanced_payload_json_is_limited_to_a1111_and_diffusers() -> None:
    import image.gui.settings as settings

    assert settings._provider_supports_advanced_payload(
        SDProvider(provider_id="stable_diffusion_remote", label="", renderer="a1111_remote")
    )
    assert settings._provider_supports_advanced_payload(
        SDProvider(provider_id="stable_diffusion_local", label="", renderer="diffusers_local")
    )
    assert not settings._provider_supports_advanced_payload(
        SDProvider(provider_id="comfyui_remote", label="", renderer="comfyui_remote")
    )


def test_comfyui_workflow_preview_supports_remote_and_local() -> None:
    import image.gui.settings as settings

    assert settings._provider_supports_comfyui_workflow_preview(
        SDProvider(provider_id="comfyui_local", label="", renderer="comfyui_local", is_comfyui=True, is_local=True)
    )
    assert settings._provider_supports_comfyui_workflow_preview(
        SDProvider(provider_id="comfyui_remote", label="", renderer="comfyui_remote", is_comfyui=True)
    )
    assert not settings._provider_supports_comfyui_workflow_preview(
        SDProvider(provider_id="stable_diffusion_remote", label="", renderer="a1111_remote")
    )


def test_image_settings_merges_advanced_payload_after_builtin_payload() -> None:
    from pathlib import Path

    content = Path("image/gui/settings.py").read_text(encoding="utf-8")

    assert "Advanced payload JSON" in content
    assert "provider_payload.update(advanced_provider_payload)" in content


def test_image_settings_exposes_num_images_per_prompt_after_gallery_support() -> None:
    from pathlib import Path

    settings_content = Path("image/gui/settings.py").read_text(encoding="utf-8")
    service_content = Path("image/gui/service.py").read_text(encoding="utf-8")
    result_ui_content = Path("image/gui/result_ui.py").read_text(encoding="utf-8")

    assert "Images per prompt" in settings_content
    assert '"num_images_per_prompt"' in settings_content
    assert "_generated_output_variants" in service_content
    assert "_render_generated_image_gallery" in result_ui_content


def test_image_refresh_action_handles_non_sd_local_providers(monkeypatch) -> None:
    import image.gui.settings as settings
    from image.gui.provider_actions import ProviderAction

    statuses: list[tuple[str, str, str]] = []

    def fake_action_row(actions: Iterable[ProviderAction]) -> str:
        for action in actions:
            if action.action_id == "refresh":
                action.callback()
                return action.action_id
        raise AssertionError("refresh action not found")

    monkeypatch.setattr(settings, "render_provider_action_row", fake_action_row)
    monkeypatch.setattr(settings, "set_action_status", lambda key, level, message: statuses.append((key, level, message)))

    for provider in ("comfyui_local", "stable_diffusion_remote", "comfyui_remote"):
        settings._handle_image_provider_actions(provider, {"base_url": "http://127.0.0.1:8188"})

    assert len(statuses) == 3
    assert all(item[0] == "image_provider_message" for item in statuses)
    assert all(item[1] == "success" for item in statuses)


def test_image_refresh_action_handles_stable_diffusion_status_without_model_count(monkeypatch) -> None:
    import image.gui.settings as settings
    from image.gui.provider_actions import ProviderAction

    statuses: list[tuple[str, str, str]] = []

    def fake_action_row(actions: Iterable[ProviderAction]) -> str:
        for action in actions:
            if action.action_id == "refresh":
                action.callback()
                return action.action_id
        raise AssertionError("refresh action not found")

    monkeypatch.setattr(settings, "render_provider_action_row", fake_action_row)
    monkeypatch.setattr(settings, "set_action_status", lambda key, level, message: statuses.append((key, level, message)))
    monkeypatch.setattr(
        settings,
        "local_provider_status",
        lambda provider_settings: {
            "models_dir": "D:/project/ai.story/image/local_models",
            "local_models": ["one", "two"],
        },
    )

    settings._handle_image_provider_actions("stable_diffusion_local", {})

    assert statuses == [
        (
            "image_provider_message",
            "success",
            "Image: scanned D:/project/ai.story/image/local_models and found 2 local model(s).",
        )
    ]


def test_model_target_recommended_default_does_not_mutate_instantiated_widget_key(monkeypatch) -> None:
    import image.gui.settings as settings

    class LockedSessionState(dict):
        def __init__(self):
            super().__init__()
            self.locked_keys: set[str] = set()

        def __setitem__(self, key, value):
            if key in self.locked_keys:
                raise AssertionError(f"widget key mutated after instantiation: {key}")
            return super().__setitem__(key, value)

    class FakeColumn:
        def __init__(self, clicked: bool = False):
            self.clicked = clicked

        def button(self, *args, **kwargs):
            return self.clicked

        def caption(self, *args, **kwargs):
            return None

    class FakeStreamlit:
        def __init__(self):
            self.session_state = LockedSessionState()

        def selectbox(self, label, options, index=0, key=None, **kwargs):
            if key:
                self.session_state[key] = options[index]
            return options[index]

        def text_input(self, label, value="", key=None, **kwargs):
            if key:
                self.session_state.setdefault(key, value)
                self.session_state.locked_keys.add(key)
            return value

        def columns(self, spec):
            return [FakeColumn(clicked=True), FakeColumn()]

        def caption(self, *args, **kwargs):
            return None

    fake_st = FakeStreamlit()
    rerun_called = []
    monkeypatch.setattr(settings, "st", fake_st)
    monkeypatch.setattr(settings, "list_local_targets", lambda *args, **kwargs: [])
    monkeypatch.setattr(settings, "provider_target_dir", lambda *args, **kwargs: "image/local_models/stable_diffusion_local")
    monkeypatch.setattr(settings, "safe_rerun", lambda: rerun_called.append(True))

    effective, _ = settings._model_target_selector(
        label="Local model id / path",
        branch="image",
        provider_id="stable_diffusion_local",
        current_value="",
        key_prefix="image_local_model",
        suggested_default="runwayml/stable-diffusion-v1-5",
    )

    assert effective == ""
    assert fake_st.session_state["image_local_model_manual_input_pending"] == "runwayml/stable-diffusion-v1-5"
    assert rerun_called == [True]

