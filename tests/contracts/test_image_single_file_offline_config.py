from __future__ import annotations

from pathlib import Path


class _FakeTokenizer:
    model_max_length = 5

    def __call__(self, text: str, **kwargs: object) -> dict[str, list[int]]:
        token_count = max(1, len(str(text).split()) + 1)
        return {"input_ids": list(range(token_count))}


def test_prepare_single_file_kwargs_allows_offline_original_config_only(monkeypatch, tmp_path: Path) -> None:
    original_config = tmp_path / "v1-inference.yaml"
    original_config.write_text("model: sd15\n", encoding="utf-8")
    import image.provider_runtime as providers

    monkeypatch.setattr(providers, "_infer_local_diffusers_config_repo", lambda: None)

    kwargs = providers._prepare_single_file_kwargs(
        load_kwargs={"torch_dtype": "float16", "cache_dir": str(tmp_path / "cache")},
        original_config=str(original_config),
        diffusers_config_repo="",
        allow_online_load=False,
    )

    assert kwargs["original_config"] == str(original_config.resolve())
    assert "config" not in kwargs
    assert kwargs["torch_dtype"] == "float16"


def test_prepare_single_file_kwargs_accepts_local_diffusers_repo(tmp_path: Path) -> None:
    original_config = tmp_path / "sdxl-base-inference.yaml"
    original_config.write_text("model: sdxl\n", encoding="utf-8")
    diffusers_repo = tmp_path / "diffusers_repo"
    diffusers_repo.mkdir()
    import image.provider_runtime as providers

    kwargs = providers._prepare_single_file_kwargs(
        load_kwargs={"torch_dtype": "float16"},
        original_config=str(original_config),
        diffusers_config_repo=str(diffusers_repo),
        allow_online_load=False,
    )

    assert kwargs["original_config"] == str(original_config.resolve())
    assert kwargs["config"] == str(diffusers_repo.resolve())


def test_prepare_single_file_kwargs_auto_infers_local_diffusers_repo(monkeypatch, tmp_path: Path) -> None:
    original_config = tmp_path / "v1-inference.yaml"
    original_config.write_text("model: sd15\n", encoding="utf-8")
    inferred_repo = tmp_path / "cached_repo"
    inferred_repo.mkdir()

    import image.provider_runtime as providers

    monkeypatch.setattr(providers, "_infer_local_diffusers_config_repo", lambda: inferred_repo)

    kwargs = providers._prepare_single_file_kwargs(
        load_kwargs={"torch_dtype": "float16"},
        original_config=str(original_config),
        diffusers_config_repo="",
        allow_online_load=False,
    )

    assert kwargs["original_config"] == str(original_config.resolve())
    assert kwargs["config"] == str(inferred_repo.resolve())


def test_prepare_prompt_pair_for_clip_can_disable_auto_shorten() -> None:
    import image.provider_runtime as providers

    logs: list[str] = []
    prompt = "one two three four five six seven"

    shortened_prompt, shortened_negative = providers._prepare_prompt_pair_for_clip(
        pipe=type("Pipe", (), {"tokenizer": _FakeTokenizer()})(),
        prompt=prompt,
        negative_prompt="neg one two three four five six",
        logs=logs,
        allow_auto_shorten=False,
    )

    assert shortened_prompt == prompt
    assert shortened_negative == "neg one two three four five six"
    assert any("auto-shortening disabled" in line for line in logs)


def test_prepare_prompt_pair_requires_pipeline_tokenizer() -> None:
    import pytest

    import image.provider_runtime as providers

    with pytest.raises(RuntimeError, match="loaded without a tokenizer"):
        providers._prepare_prompt_pair_for_clip(
            pipe=type("Pipe", (), {"tokenizer": None, "tokenizer_2": None})(),
            prompt="one two three",
            negative_prompt="",
            logs=[],
        )


