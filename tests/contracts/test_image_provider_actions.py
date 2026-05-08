from __future__ import annotations

from typing import Iterable


def test_image_refresh_action_handles_non_sd_local_providers(monkeypatch) -> None:
    import image.gui.settings as settings
    from common.gui.provider_actions import ProviderAction

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
    from common.gui.provider_actions import ProviderAction

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

