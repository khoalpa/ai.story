from __future__ import annotations

import importlib


def test_vieneu_turbo_gguf_runtime_keeps_cuda_device() -> None:
    tts_core = importlib.import_module("audio.adapters.tts_core")

    tts_core._ENGINE_CACHE.clear()
    captured: dict[str, object] = {}
    original_import_factory = tts_core._import_vieneu_factory
    original_bootstrap = tts_core.bootstrap_vieneu_runtime
    original_patch_standard = tts_core._patch_vieneu_standard_offline_dependencies
    original_patch_meta = tts_core._patch_transformers_meta_to_empty
    original_resolve_model = tts_core.resolve_vieneu_model_for_runtime

    def fake_vieneu(*, mode: str, **kwargs):
        captured["mode"] = mode
        captured["kwargs"] = dict(kwargs)
        return object()

    try:
        tts_core._import_vieneu_factory = lambda: fake_vieneu  # type: ignore[assignment]
        tts_core.bootstrap_vieneu_runtime = lambda *args, **kwargs: None  # type: ignore[assignment]
        tts_core._patch_vieneu_standard_offline_dependencies = lambda: None  # type: ignore[assignment]
        tts_core._patch_transformers_meta_to_empty = lambda: None  # type: ignore[assignment]
        tts_core.resolve_vieneu_model_for_runtime = lambda value, mode, allow_network=False: str(value)  # type: ignore[assignment]

        tts_core._get_engine(
            mode="turbo",
            api_base="",
            model_name="C:/models/vieneu/model.gguf",
            device="cuda",
            allow_network=False,
        )
    finally:
        tts_core._import_vieneu_factory = original_import_factory  # type: ignore[assignment]
        tts_core.bootstrap_vieneu_runtime = original_bootstrap  # type: ignore[assignment]
        tts_core._patch_vieneu_standard_offline_dependencies = original_patch_standard  # type: ignore[assignment]
        tts_core._patch_transformers_meta_to_empty = original_patch_meta  # type: ignore[assignment]
        tts_core.resolve_vieneu_model_for_runtime = original_resolve_model  # type: ignore[assignment]
        tts_core._ENGINE_CACHE.clear()

    assert "mode" in captured
    assert captured["kwargs"]["device"] == "cuda"
    assert captured["kwargs"]["backbone_repo"] == "C:/models/vieneu/model.gguf"


def test_vieneu_runtime_backend_prefers_lmdeploy_for_standard_cuda(monkeypatch) -> None:
    tts_core = importlib.import_module("audio.adapters.tts_core")

    monkeypatch.setattr(tts_core, "_is_vieneu_lmdeploy_available", lambda: True)

    assert tts_core.resolve_vieneu_runtime_backend("standard", "pnnbao-ump/VieNeu-TTS", "cuda") == "lmdeploy"
    assert tts_core.resolve_vieneu_runtime_backend("standard", "pnnbao-ump/VieNeu-TTS-0.3B-q4-gguf", "cuda") == "native"
    assert tts_core.resolve_vieneu_runtime_backend("turbo", "pnnbao-ump/VieNeu-TTS", "cuda") == "native"


def test_vieneu_get_engine_passes_lmdeploy_backend_hint(monkeypatch) -> None:
    tts_core = importlib.import_module("audio.adapters.tts_core")

    captured: dict[str, object] = {}

    class FakeVieneu:
        def __init__(self, *, mode: str, backend: str | None = None, **kwargs):  # noqa: ANN001
            captured["mode"] = mode
            captured["backend"] = backend
            captured["kwargs"] = dict(kwargs)

    monkeypatch.setattr(tts_core, "_import_vieneu_factory", lambda: FakeVieneu)
    monkeypatch.setattr(tts_core, "_is_vieneu_lmdeploy_available", lambda: True)
    monkeypatch.setattr(tts_core, "bootstrap_vieneu_runtime", lambda *args, **kwargs: None)
    monkeypatch.setattr(tts_core, "_patch_vieneu_standard_offline_dependencies", lambda: None)
    monkeypatch.setattr(tts_core, "_patch_transformers_meta_to_empty", lambda: None)
    monkeypatch.setattr(tts_core, "resolve_vieneu_model_for_runtime", lambda value, mode, allow_network=False: str(value))

    tts_core._ENGINE_CACHE.clear()
    try:
        tts_core._get_engine(
            mode="standard",
            api_base="",
            model_name="pnnbao-ump/VieNeu-TTS-0.3B",
            device="cuda",
            allow_network=False,
        )
    finally:
        tts_core._ENGINE_CACHE.clear()

    assert captured["mode"] == "standard"
    assert captured["backend"] == "lmdeploy"
    assert captured["kwargs"]["backbone_device"] == "cuda"
    assert captured["kwargs"]["codec_device"] == "cuda"


def test_vieneu_runtime_backend_respects_native_override(monkeypatch) -> None:
    tts_core = importlib.import_module("audio.adapters.tts_core")

    monkeypatch.setattr(tts_core, "_is_vieneu_lmdeploy_available", lambda: True)

    assert tts_core.resolve_vieneu_runtime_backend("standard", "pnnbao-ump/VieNeu-TTS", "cuda", "native") == "native"
    assert tts_core.resolve_vieneu_runtime_backend("standard", "pnnbao-ump/VieNeu-TTS", "cuda", "lmdeploy") == "lmdeploy"
    assert tts_core.resolve_vieneu_runtime_backend("standard", "pnnbao-ump/VieNeu-TTS-0.3B-q4-gguf", "cuda", "lmdeploy") == "native"


def test_edge_runtime_diagnostics_do_not_require_vieneu() -> None:
    runtime_checks = importlib.import_module("audio.runtime_checks")
    captured: dict[str, object] = {}
    original_collect = runtime_checks.collect_common_runtime_diagnostics

    def fake_collect_runtime_diagnostics(*, tool_configs, dependency_modules):
        captured["tool_configs"] = tuple(tool_configs)
        captured["dependency_modules"] = tuple(dependency_modules)
        return object()

    try:
        runtime_checks.collect_common_runtime_diagnostics = fake_collect_runtime_diagnostics  # type: ignore[assignment]
        runtime_checks.collect_runtime_diagnostics_for_settings("ffmpeg", "ffprobe", tts_provider="edge")
    finally:
        runtime_checks.collect_common_runtime_diagnostics = original_collect  # type: ignore[assignment]

    assert captured["tool_configs"] == (("ffmpeg", "ffmpeg"), ("ffprobe", "ffprobe"))
    assert captured["dependency_modules"] == ("edge_tts", "streamlit")


def test_preview_tts_cache_key_changes_with_vieneu_device() -> None:
    service = importlib.import_module("audio.gui.service")
    original_resolve_model_runtime = service.resolve_vieneu_model_for_runtime
    base_settings = {
        "tts_provider": "vieneu",
        "vieneu_core": "local",
        "vieneu_mode": "turbo",
        "vieneu_api_base": "",
        "vieneu_model_name": "C:/models/vieneu/model.gguf",
        "vieneu_device": "cuda",
        "vieneu_preview_temperature": 0.6,
        "vieneu_preview_max_chars_chunk": 160,
        "vieneu_preview_use_batch": False,
        "vieneu_preview_max_batch_size_run": 1,
        "vieneu_preview_text_max_len": 100,
    }

    try:
        service.resolve_vieneu_model_for_runtime = lambda value, mode, allow_network=False: str(value)  # type: ignore[assignment]
        first = service._preview_tts_cache_key(
            provider="vieneu",
            safe_lang="vi",
            selected_voice="voice-a",
            preview_text="hello world",
            settings=base_settings,
        )
        second = service._preview_tts_cache_key(
            provider="vieneu",
            safe_lang="vi",
            selected_voice="voice-a",
            preview_text="hello world",
            settings={**base_settings, "vieneu_device": "cpu"},
        )
    finally:
        service.resolve_vieneu_model_for_runtime = original_resolve_model_runtime  # type: ignore[assignment]

    assert first != second


def test_preview_tts_cache_key_ignores_vieneu_settings_for_edge() -> None:
    service = importlib.import_module("audio.gui.service")

    key = service._preview_tts_cache_key(
        provider="edge",
        safe_lang="vi",
        selected_voice="voice-a",
        preview_text="hello world",
        settings={
            "tts_provider": "edge",
            "vieneu_core": "local",
            "vieneu_mode": "turbo",
            "vieneu_api_base": "",
            "vieneu_model_name": "C:/models/vieneu/missing.gguf",
            "vieneu_device": "cpu",
            "vieneu_preview_temperature": 0.6,
            "vieneu_preview_max_chars_chunk": 160,
            "vieneu_preview_use_batch": False,
            "vieneu_preview_max_batch_size_run": 1,
            "vieneu_preview_text_max_len": 100,
        },
    )

    assert isinstance(key, str)
    assert len(key) == 16


def test_preview_tts_sample_passes_resolved_vieneu_backend(monkeypatch, tmp_path) -> None:
    service = importlib.import_module("audio.gui.service")

    captured: dict[str, object] = {}

    def fake_synthesize_segment_with_vieneu(seg, out_wav, voice_map_vi, voice_map_en, **kwargs):  # noqa: ANN001, ANN003
        captured["text"] = getattr(seg, "text", "")
        captured["out_wav"] = out_wav
        captured["voice_map_vi"] = dict(voice_map_vi)
        captured["voice_map_en"] = dict(voice_map_en)
        captured["kwargs"] = dict(kwargs)
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        out_wav.write_text("preview", encoding="utf-8")

    monkeypatch.setattr(service, "synthesize_segment_with_vieneu", fake_synthesize_segment_with_vieneu)
    monkeypatch.setattr(service, "resolve_vieneu_model_name", lambda value, mode: str(value or mode))
    monkeypatch.setattr(service, "resolve_vieneu_model_for_runtime", lambda value, mode, allow_network=False: str(value))
    monkeypatch.setattr(service, "resolve_vieneu_runtime_backend", lambda mode, model_name, device, backend: "native")
    monkeypatch.setattr(service.tempfile, "gettempdir", lambda: str(tmp_path))

    out_path = service.preview_tts_sample(
        text="hello world",
        settings={
            "tts_provider": "vieneu",
            "vieneu_core": "local",
            "vieneu_mode": "standard",
            "vieneu_api_base": "",
            "vieneu_model_name": "model",
            "vieneu_device": "cuda",
            "vieneu_backend": "lmdeploy",
            "voice_narrator": "voice-a",
            "voice_female": "voice-b",
            "voice_male": "voice-c",
            "voice_en_narrator": "voice-en-a",
            "voice_en_female": "voice-en-b",
            "voice_en_male": "voice-en-c",
            "vieneu_preview_temperature": 0.6,
            "vieneu_preview_max_chars_chunk": 160,
            "vieneu_preview_use_batch": False,
            "vieneu_preview_max_batch_size_run": 1,
            "vieneu_preview_text_max_len": 100,
        },
        lang="vi",
        voice_choice="voice-a",
    )

    assert out_path.exists()
    assert captured["kwargs"]["backend"] == "native"
    assert captured["kwargs"]["vieneu_mode"] == "standard"
    assert captured["kwargs"]["vieneu_model_name"] == "model"
    assert captured["kwargs"]["vieneu_device"] == "cuda"


def test_vieneu_cuda_promotes_turbo_to_standard() -> None:
    service = importlib.import_module("audio.gui.service")

    assert service.resolve_vieneu_ui_mode("local", "turbo", "cuda") == "standard"
    assert service.resolve_vieneu_runtime_mode("local", "turbo", "cuda") == "standard"
    assert service.resolve_vieneu_runtime_mode("remote_api", "turbo", "cuda") == "remote"


def test_vieneu_auto_device_prefers_gpu_when_enabled(monkeypatch) -> None:
    tts_core = importlib.import_module("audio.adapters.tts_core")

    monkeypatch.setattr(tts_core, "prefer_gpu_enabled", lambda: True)

    assert tts_core.normalize_vieneu_device("auto") == "auto"
    assert tts_core.resolve_vieneu_runtime_device("auto") == "cuda"
    assert tts_core.resolve_vieneu_effective_mode("local", "turbo", "auto") == "standard"


def test_vieneu_auto_device_falls_back_to_cpu_when_gpu_disabled(monkeypatch) -> None:
    tts_core = importlib.import_module("audio.adapters.tts_core")

    monkeypatch.setattr(tts_core, "prefer_gpu_enabled", lambda: False)

    assert tts_core.resolve_vieneu_runtime_device("auto") == "cpu"
    assert tts_core.resolve_vieneu_effective_mode("local", "turbo", "auto") == "turbo"


def test_vieneu_cuda_turbo_warning_mentions_cpu_edge_path() -> None:
    service = importlib.import_module("audio.gui.service")

    warning = service.describe_vieneu_cuda_turbo_path(core="local", mode="turbo", device="cuda")

    assert "CPU/edge" in warning
    assert "Standard" in warning


def test_app_config_autopromotes_vieneu_cuda_to_standard() -> None:
    app_config = importlib.import_module("audio.app_config")

    config = app_config.AppConfig.from_mapping(
        {
            "ffmpeg_exe": "ffmpeg",
            "ffprobe_exe": "ffprobe",
            "output_dir": "output",
            "audio_format": "wav",
            "tts_provider": "vieneu",
            "vieneu_core": "local",
            "vieneu_mode": "turbo",
            "vieneu_model_name": "pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF",
            "vieneu_device": "cuda",
            "vieneu_backend": "native",
        }
    )

    assert config.vieneu_mode == "standard"
    assert config.vieneu_backend == "native"


def test_render_request_autopromotes_vieneu_cuda_to_standard() -> None:
    render_audio_app = importlib.import_module("audio.render_audio_app")

    request = render_audio_app.RenderAudioAppRequest.from_mapping(
        {
            "input_path": "input.txt",
            "output_dir": "output",
            "asset_profile": None,
            "profile_root": ".",
            "bgm": None,
            "bgmdir": "audio/bgm",
            "voice_narrator": "vi-VN-NamMinhNeural",
            "voice_female": "vi-VN-HoaiMyNeural",
            "voice_male": "vi-VN-NamMinhNeural",
            "voice_en_narrator": "en-US-AndrewNeural",
            "voice_en_female": "en-US-AvaNeural",
            "voice_en_male": "en-US-AndrewNeural",
            "abbr_map": "abbreviation_map.json",
            "bgm_config": None,
            "sentiment_tone": False,
            "validate_only": False,
            "debug": False,
            "auto_en_lines": False,
            "post_fx_preset": "none",
            "max_concurrent_tts": 8,
            "tts_provider": "vieneu",
            "audio_format": "wav",
            "vieneu_mode": "turbo",
            "vieneu_api_base": "",
            "vieneu_model_name": "pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF",
            "vieneu_device": "cuda",
            "vieneu_backend": "lmdeploy",
            "vieneu_render_temperature": 0.7,
            "vieneu_render_max_chars_chunk": 240,
            "vieneu_render_use_batch": False,
            "vieneu_render_max_batch_size_run": 1,
        }
    )

    assert request.vieneu_mode == "standard"
    assert request.vieneu_backend == "lmdeploy"


def test_render_request_autopromotes_vieneu_auto_to_standard(monkeypatch) -> None:
    tts_core = importlib.import_module("audio.adapters.tts_core")
    render_audio_app = importlib.import_module("audio.render_audio_app")

    monkeypatch.setattr(tts_core, "prefer_gpu_enabled", lambda: True)

    request = render_audio_app.RenderAudioAppRequest.from_mapping(
        {
            "input_path": "input.txt",
            "output_dir": "output",
            "asset_profile": None,
            "profile_root": ".",
            "bgm": None,
            "bgmdir": "audio/bgm",
            "voice_narrator": "vi-VN-NamMinhNeural",
            "voice_female": "vi-VN-HoaiMyNeural",
            "voice_male": "vi-VN-NamMinhNeural",
            "voice_en_narrator": "en-US-AndrewNeural",
            "voice_en_female": "en-US-AvaNeural",
            "voice_en_male": "en-US-AndrewNeural",
            "abbr_map": "abbreviation_map.json",
            "bgm_config": None,
            "sentiment_tone": False,
            "validate_only": False,
            "debug": False,
            "auto_en_lines": False,
            "post_fx_preset": "none",
            "max_concurrent_tts": 8,
            "tts_provider": "vieneu",
            "audio_format": "wav",
            "vieneu_mode": "turbo",
            "vieneu_api_base": "",
            "vieneu_model_name": "pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF",
            "vieneu_device": "auto",
            "vieneu_backend": "auto",
            "vieneu_render_temperature": 0.7,
            "vieneu_render_max_chars_chunk": 240,
            "vieneu_render_use_batch": False,
            "vieneu_render_max_batch_size_run": 1,
        }
    )

    assert request.vieneu_device == "auto"
    assert request.vieneu_mode == "standard"
    assert request.vieneu_backend == "auto"


def test_render_request_preserves_remote_api_core() -> None:
    render_audio_app = importlib.import_module("audio.render_audio_app")

    request = render_audio_app.RenderAudioAppRequest.from_mapping(
        {
            "input_path": "input.txt",
            "output_dir": "output",
            "asset_profile": None,
            "profile_root": ".",
            "bgm": None,
            "bgmdir": "audio/bgm",
            "voice_narrator": "vi-VN-NamMinhNeural",
            "voice_female": "vi-VN-HoaiMyNeural",
            "voice_male": "vi-VN-NamMinhNeural",
            "voice_en_narrator": "en-US-AndrewNeural",
            "voice_en_female": "en-US-AvaNeural",
            "voice_en_male": "en-US-AndrewNeural",
            "abbr_map": "abbreviation_map.json",
            "bgm_config": None,
            "sentiment_tone": False,
            "validate_only": False,
            "debug": False,
            "auto_en_lines": False,
            "post_fx_preset": "none",
            "max_concurrent_tts": 8,
            "tts_provider": "vieneu",
            "audio_format": "wav",
            "vieneu_core": "remote_api",
            "vieneu_mode": "turbo",
            "vieneu_api_base": "http://127.0.0.1:23333/v1",
            "vieneu_model_name": "remote-model",
            "vieneu_device": "cuda",
            "vieneu_backend": "auto",
        }
    )

    assert request.vieneu_core == "remote_api"
    assert request.vieneu_mode == "remote"
    assert request.to_payload()["vieneu_core"] == "remote_api"


def test_render_tts_segments_preserves_remote_api_core(monkeypatch, tmp_path) -> None:
    tts_render = importlib.import_module("audio.services.tts_render")

    captured: dict[str, object] = {}

    def fake_get_vieneu_engine(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(tts_render, "get_vieneu_engine", fake_get_vieneu_engine)
    monkeypatch.setattr(tts_render, "resolve_vieneu_model_name", lambda value, mode: str(value or mode))
    monkeypatch.setattr(tts_render, "resolve_vieneu_model_for_runtime", lambda value, mode, allow_network=False: str(value))
    monkeypatch.setattr(tts_render, "resolve_vieneu_runtime_backend", lambda mode, model_name, device, backend: str(backend or "auto"))

    config = tts_render.TtsRenderConfig(
        wav_dir=tmp_path,
        voice_map_vi={"narrator": "voice"},
        voice_map_en={"narrator": "voice"},
        abbr_map={},
        tts_provider="vieneu",
        vieneu_core="remote_api",
        vieneu_mode="remote",
        vieneu_api_base="http://127.0.0.1:23333/v1",
        vieneu_model_name="remote-model",
        vieneu_device="cuda",
        vieneu_backend="auto",
    )

    import asyncio

    asyncio.run(tts_render.render_tts_segments_async([], config))

    assert captured["mode"] == "remote"
    assert captured["api_base"] == "http://127.0.0.1:23333/v1"
    assert captured["model_name"] == "remote-model"


def test_app_config_to_request_mapping_preserves_selected_vieneu_device() -> None:
    app_config = importlib.import_module("audio.app_config")
    profile_config_module = importlib.import_module("audio.profile_config")

    config = app_config.AppConfig.from_mapping(
        {
            "ffmpeg_exe": "ffmpeg",
            "ffprobe_exe": "ffprobe",
            "output_dir": "output",
            "audio_format": "wav",
            "tts_provider": "vieneu",
            "vieneu_core": "local",
            "vieneu_mode": "turbo",
            "vieneu_model_name": "pnnbao-ump/VieNeu-TTS-v2-Turbo-GGUF",
            "vieneu_device": "cpu",
            "vieneu_backend": "native",
        }
    )
    profile = profile_config_module.ProfileConfig.from_mapping({})

    request = config.to_request(__import__("pathlib").Path("input.txt"), profile)

    assert request.vieneu_device == "cpu"
    assert request.to_payload()["vieneu_device"] == "cpu"


def test_profile_config_round_trips_selected_vieneu_device() -> None:
    profile_config_module = importlib.import_module("audio.profile_config")

    profile = profile_config_module.ProfileConfig.from_mapping({"vieneu_device": "cpu"})

    assert profile.vieneu_device == "cpu"
    assert profile.to_payload()["vieneu_device"] == "cpu"


def test_vieneu_render_uses_configured_concurrency(monkeypatch) -> None:
    tts_render = importlib.import_module("audio.services.tts_render")

    active = 0
    max_active = 0
    started = 0
    gate = None

    async def fake_synthesize_segment_with_vieneu_async(*args, **kwargs):  # noqa: ANN001
        nonlocal active, max_active, started, gate
        active += 1
        started += 1
        max_active = max(max_active, active)
        if gate is None:
            import asyncio

            gate = asyncio.Event()
        if started >= 2:
            gate.set()
        await gate.wait()
        active -= 1

    monkeypatch.setattr(tts_render, "synthesize_segment_with_vieneu_async", fake_synthesize_segment_with_vieneu_async)
    monkeypatch.setattr(tts_render, "resolve_vieneu_model_for_runtime", lambda value, mode, allow_network=False: str(value))
    monkeypatch.setattr(tts_render, "resolve_vieneu_model_name", lambda value, mode: str(value or mode))
    monkeypatch.setattr(tts_render, "get_vieneu_engine", lambda **kwargs: object())

    config = tts_render.TtsRenderConfig(
        wav_dir=__import__("pathlib").Path("tmp"),
        voice_map_vi={"narrator": "voice"},
        voice_map_en={"narrator": "voice"},
        abbr_map={},
        tts_provider="vieneu",
        vieneu_mode="turbo",
        vieneu_model_name="model",
        vieneu_device="cpu",
        max_concurrent_tts=2,
    )

    import asyncio

    asyncio.run(tts_render.render_tts_segments_async([object(), object(), object()], config))

    assert max_active == 2


def test_vieneu_render_uses_infer_batch_when_enabled(monkeypatch, tmp_path) -> None:
    tts_render = importlib.import_module("audio.services.tts_render")
    segment_planner = importlib.import_module("audio.pipeline.segment_planner")

    calls: list[tuple[list[str], object | None]] = []
    saved_paths: list[str] = []

    class FakeEngine:
        def get_preset_voice(self, voice_id: str) -> dict[str, str]:
            return {"voice_id": voice_id}

        def list_preset_voices(self) -> list[tuple[str, str]]:
            return [("Narrator", "narrator")]

        def infer_batch(self, texts, voice=None, temperature=None, max_chars=None):  # noqa: ANN001
            calls.append((list(texts), voice))
            return [f"audio:{text}" for text in texts]

        def save(self, audio, out_wav):  # noqa: ANN001
            saved_paths.append(str(out_wav))
            out_wav.write_text(str(audio), encoding="utf-8")

    fake_engine = FakeEngine()
    monkeypatch.setattr(tts_render, "get_vieneu_engine", lambda **kwargs: fake_engine)
    monkeypatch.setattr(tts_render, "resolve_vieneu_model_for_runtime", lambda value, mode, allow_network=False: str(value))
    monkeypatch.setattr(tts_render, "resolve_vieneu_model_name", lambda value, mode: str(value or mode))

    segments = [
        segment_planner.Segment(text="one", voice="narrator", rate=1.0, lang="vi", lang_from_tag=True),
        segment_planner.Segment(text="two", voice="narrator", rate=1.0, lang="vi", lang_from_tag=True),
        segment_planner.Segment(text="three", voice="narrator", rate=1.0, lang="vi", lang_from_tag=True),
    ]
    config = tts_render.TtsRenderConfig(
        wav_dir=tmp_path,
        voice_map_vi={"narrator": "narrator"},
        voice_map_en={"narrator": "narrator"},
        abbr_map={},
        tts_provider="vieneu",
        vieneu_mode="standard",
        vieneu_model_name="model",
        vieneu_device="cpu",
        vieneu_render_use_batch=True,
        vieneu_render_max_batch_size_run=2,
    )

    import asyncio

    asyncio.run(tts_render.render_tts_segments_async(segments, config))

    assert calls == [(["one", "two"], {"voice_id": "narrator"}), (["three"], {"voice_id": "narrator"})]
    assert len(saved_paths) == 3
    assert (tmp_path / "seg_000.wav").read_text(encoding="utf-8") == "audio:one"
    assert (tmp_path / "seg_001.wav").read_text(encoding="utf-8") == "audio:two"
    assert (tmp_path / "seg_002.wav").read_text(encoding="utf-8") == "audio:three"

