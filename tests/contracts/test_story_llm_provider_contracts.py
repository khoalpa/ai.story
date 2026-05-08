from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import requests  # type: ignore[import-untyped]


def test_story_llm_registry_includes_lmdeploy_local_provider() -> None:
    from story.llm_providers import build_provider_settings, get_provider_preset, infer_provider_id

    provider = get_provider_preset("lmdeploy")
    assert provider.label == "LMDeploy (local)"
    assert provider.requires_api_key is False
    assert provider.default_profile_id == "local_api_server"

    settings = build_provider_settings("lmdeploy")
    assert settings["base_url"] == "http://localhost:1234/v1"
    assert settings["model"] == "auto"
    assert settings["api_key"] == "not-needed"
    assert infer_provider_id("http://localhost:1234/v1") == "lm_studio"


def test_story_llm_registry_scans_provider_modules() -> None:
    from story.llm_providers import list_provider_ids, validate_provider_modules_dir

    providers = validate_provider_modules_dir()
    provider_ids = list_provider_ids()

    assert [item.provider_id for item in providers] == provider_ids
    assert "lmdeploy" in provider_ids
    assert "lm_studio" in provider_ids
    assert "openai_chatgpt" in provider_ids
    assert "custom_compatible" in provider_ids


def test_story_llm_default_provider_is_lmdeploy_local() -> None:
    from story.gui.state import STORY_PROVIDER_DEFAULTS
    from story.llm_provider_user_config import normalize_persisted_llm_settings
    from story.llm_providers import build_provider_settings, get_provider_preset, infer_provider_id

    provider = get_provider_preset(None)
    settings = build_provider_settings(None)
    persisted = normalize_persisted_llm_settings({})

    assert provider.provider_id == "lmdeploy"
    assert settings["llm_provider"] == "lmdeploy"
    assert settings["llm_profile"] == "local_api_server"
    assert settings["base_url"] == "http://localhost:1234/v1"
    assert settings["model"] == "auto"
    assert persisted["llm_provider"] == "lmdeploy"
    assert STORY_PROVIDER_DEFAULTS["story_llm_provider_id"] == "lmdeploy"
    assert STORY_PROVIDER_DEFAULTS["story_llm_profile_id"] == "local_api_server"
    assert infer_provider_id("") == "lmdeploy"


def test_story_provider_quick_test_does_not_load_literal_auto_target() -> None:
    from story.llm_provider_runtime import build_quick_test_config

    defaults, cfg = build_quick_test_config("lmdeploy")

    assert defaults["model"] == "auto"
    assert cfg.local_update_target == ""


def test_story_local_model_picker_defaults_to_first_scanned_target(monkeypatch, tmp_path: Path) -> None:
    from story.gui import sidebar

    class FakeStreamlit:
        session_state: dict[str, str] = {}

        def selectbox(self, label: str, *, options: list[str], index: int, key: str, help: str) -> str:
            self.session_state[key] = options[index]
            return options[index]

        def caption(self, value: str) -> None:
            return None

        def text_input(self, label: str, *, value: str, key: str) -> str:
            self.session_state.setdefault(key, value)
            return self.session_state[key]

    fake_st = FakeStreamlit()
    monkeypatch.setattr(sidebar, "st", fake_st)
    monkeypatch.setattr(sidebar, "provider_target_dir", lambda *args, **kwargs: tmp_path / "lmdeploy")
    monkeypatch.setattr(sidebar, "list_local_targets", lambda *args, **kwargs: ["qwen-first/", "qwen-second/"])

    model, target_dir, local_update_target = sidebar._render_story_local_model_picker(provider_id="lmdeploy", current_model="auto")

    assert model == "qwen-first/"
    assert target_dir == str(tmp_path / "lmdeploy")
    assert local_update_target == "qwen-first/"
    assert fake_st.session_state[sidebar.MODEL_KEY] == "qwen-first/"


def test_llm_client_auto_discovers_openai_compatible_model(monkeypatch) -> None:
    from story.client import LLMClient, LLMConfig

    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload
            self.text = json.dumps(payload)
            self.status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        calls.append(("GET", url, None))
        return FakeResponse({"data": [{"id": "served-qwen"}]})

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        payload = kwargs.get("json")
        calls.append(("POST", url, cast(dict[str, Any], payload) if isinstance(payload, dict) else None))
        return FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)

    client = LLMClient(
        LLMConfig(
            base_url="http://localhost:23333/v1",
            model="auto",
            timeout_s=5,
            max_tokens=32,
            temperature=0.0,
        )
    )

    assert client.chat("system", "user") == "ok"
    assert client.model == "served-qwen"
    assert calls[0] == ("GET", "http://localhost:23333/v1/models", None)
    assert calls[1][0] == "POST"
    assert calls[1][2] is not None
    assert calls[1][2]["model"] == "served-qwen"


def test_llm_client_loads_local_target_when_no_models_are_loaded(monkeypatch) -> None:
    from story import client as client_mod
    from story.client import LLMClient, LLMConfig

    calls: list[tuple[str, str, dict[str, Any] | None]] = []
    model_lists = [
        {"data": []},
        {"data": [{"id": "qwen-first"}]},
    ]
    load_calls: list[list[str]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload
            self.text = json.dumps(payload)
            self.status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        calls.append(("GET", url, None))
        return FakeResponse(model_lists.pop(0))

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        payload = kwargs.get("json")
        calls.append(("POST", url, cast(dict[str, Any], payload) if isinstance(payload, dict) else None))
        return FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    class FakeCompletedProcess:
        returncode = 0
        stdout = "loaded"
        stderr = ""

    def fake_run(cmd: list[str], **kwargs: object) -> FakeCompletedProcess:
        load_calls.append(cmd)
        return FakeCompletedProcess()

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(client_mod.shutil, "which", lambda name: "lms.exe" if name == "lms" else None)
    monkeypatch.setattr(client_mod.subprocess, "run", fake_run)

    client = LLMClient(
        LLMConfig(
            base_url="http://localhost:1234/v1",
            model="auto",
            timeout_s=5,
            max_tokens=32,
            temperature=0.0,
            local_update_target="qwen-first/",
        )
    )

    assert client.chat("system", "user") == "ok"
    assert load_calls == [["lms.exe", "load", "qwen-first"]]
    assert calls[0] == ("GET", "http://localhost:1234/v1/models", None)
    assert calls[1] == ("GET", "http://localhost:1234/v1/models", None)
    assert calls[2][0] == "POST"
    assert calls[2][2] is not None
    assert calls[2][2]["model"] == "qwen-first"


def test_llm_client_posts_discovered_model_after_loading_explicit_local_target(monkeypatch) -> None:
    from story import client as client_mod
    from story.client import LLMClient, LLMConfig

    calls: list[tuple[str, str, dict[str, Any] | None]] = []
    load_calls: list[list[str]] = []

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload
            self.text = json.dumps(payload)
            self.status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return self._payload

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        calls.append(("GET", url, None))
        return FakeResponse({"data": [{"id": "qwen-served-id"}]})

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        payload = kwargs.get("json")
        calls.append(("POST", url, cast(dict[str, Any], payload) if isinstance(payload, dict) else None))
        return FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    class FakeCompletedProcess:
        returncode = 0
        stdout = "loaded"
        stderr = ""

    def fake_run(cmd: list[str], **kwargs: object) -> FakeCompletedProcess:
        load_calls.append(cmd)
        return FakeCompletedProcess()

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(client_mod.shutil, "which", lambda name: "lms.exe" if name == "lms" else None)
    monkeypatch.setattr(client_mod.subprocess, "run", fake_run)

    client = LLMClient(
        LLMConfig(
            base_url="http://localhost:1234/v1",
            model="qwen-first/",
            timeout_s=5,
            max_tokens=32,
            temperature=0.0,
            local_update_target="qwen-first/",
        )
    )

    assert client.chat("system", "user") == "ok"
    assert load_calls == []
    assert calls[0] == ("GET", "http://localhost:1234/v1/models", None)
    assert calls[1] == ("GET", "http://localhost:1234/v1/models", None)
    assert calls[2][0] == "POST"
    assert calls[2][2] is not None
    assert calls[2][2]["model"] == "qwen-served-id"


def test_llm_client_loads_local_target_when_chat_reports_no_models_loaded(monkeypatch) -> None:
    from story import client as client_mod
    from story.client import LLMClient, LLMConfig

    calls: list[tuple[str, str, dict[str, Any] | None]] = []
    model_lists = [
        {"data": [{"id": "stale-model"}]},
        {"data": [{"id": "qwen-first"}]},
    ]
    load_calls: list[list[str]] = []
    post_count = 0

    class FakeResponse:
        def __init__(self, payload: dict[str, object], *, status_code: int = 200, text: str = "") -> None:
            self._payload = payload
            self.status_code = status_code
            self.text = text or json.dumps(payload)

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise requests.HTTPError(response=self)

        def json(self) -> dict[str, object]:
            return self._payload

    def fake_get(url: str, **kwargs: object) -> FakeResponse:
        calls.append(("GET", url, None))
        return FakeResponse(model_lists.pop(0))

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        nonlocal post_count
        post_count += 1
        payload = kwargs.get("json")
        calls.append(("POST", url, dict(cast(dict[str, Any], payload)) if isinstance(payload, dict) else None))
        if post_count == 1:
            return FakeResponse(
                {},
                status_code=400,
                text='{"error":{"message":"No models loaded. Please load a model in the developer page or use the lms load command."}}',
            )
        return FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    class FakeCompletedProcess:
        returncode = 0
        stdout = "loaded"
        stderr = ""

    def fake_run(cmd: list[str], **kwargs: object) -> FakeCompletedProcess:
        load_calls.append(cmd)
        return FakeCompletedProcess()

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)
    monkeypatch.setattr(client_mod.shutil, "which", lambda name: "lms.exe" if name == "lms" else None)
    monkeypatch.setattr(client_mod.subprocess, "run", fake_run)

    client = LLMClient(
        LLMConfig(
            base_url="http://localhost:1234/v1",
            model="auto",
            timeout_s=5,
            max_tokens=32,
            temperature=0.0,
            local_update_target="qwen-first/",
        )
    )

    assert client.chat("system", "user") == "ok"
    assert load_calls == [["lms.exe", "load", "qwen-first"]]
    assert calls[1][0] == "POST"
    assert calls[1][2] is not None
    assert calls[1][2]["model"] == "stale-model"
    assert calls[3][0] == "POST"
    assert calls[3][2] is not None
    assert calls[3][2]["model"] == "qwen-first"


def test_llm_http_error_includes_response_body(monkeypatch) -> None:
    from story.client import LLMClient, LLMConfig, LLMHTTPError

    class FakeResponse:
        status_code = 400
        text = '{"error":"model not found"}'

        def raise_for_status(self) -> None:
            raise requests.HTTPError(response=self)

    def fake_post(url: str, **kwargs: object) -> FakeResponse:
        return FakeResponse()

    monkeypatch.setattr(requests, "post", fake_post)

    client = LLMClient(
        LLMConfig(
            base_url="http://localhost:23333/v1",
            model="served-qwen",
            timeout_s=5,
            max_tokens=32,
            temperature=0.0,
        )
    )

    try:
        client.chat("system", "user")
    except LLMHTTPError as exc:
        assert "status=400" in str(exc)
        assert "model not found" in str(exc)
    else:
        raise AssertionError("Expected LLMHTTPError")

