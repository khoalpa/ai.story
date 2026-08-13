from __future__ import annotations

from pathlib import Path

from scripts.check_security_policy import check_repository, check_subprocess_ast, check_text


def test_repository_passes_security_policy() -> None:
    assert check_repository() == []


def test_secret_and_remote_http_provider_url_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "provider.py"
    text = 'api_key = "sk-abcdefghijklmnopqrstuvwxyz123456"\nbase_url = "http://provider.example/v1"\n'

    errors = check_text(path, text, tmp_path)

    assert any("OpenAI-style API key" in error for error in errors)
    assert any("must use HTTPS" in error for error in errors)


def test_loopback_http_provider_url_is_allowed(tmp_path: Path) -> None:
    path = tmp_path / "provider.py"

    assert check_text(path, 'base_url = "http://127.0.0.1:1234/v1"\n', tmp_path) == []


def test_unsafe_subprocess_forms_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "runner.py"
    text = 'import subprocess\nsubprocess.run("tool --flag", shell=True)\n'

    errors = check_subprocess_ast(path, text, tmp_path)

    assert any("shell=True" in error for error in errors)
    assert any("argv sequence" in error for error in errors)
