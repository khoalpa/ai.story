from __future__ import annotations

import importlib


def test_feature_app_apis_import_without_loading_streamlit() -> None:
    modules = [
        importlib.import_module(f"{package}.app_api")
        for package in ("story", "audio", "image", "video")
    ]
    for package, module in zip(("story", "audio", "image", "video"), modules):
        assert callable(getattr(module, f"render_{package}_workspace"))
        assert callable(getattr(module, f"render_{package}_studio"))
        assert callable(getattr(module, "validate_request"))
        assert callable(getattr(module, "execute_request"))
        assert "validate_request" in module.__all__
        assert "execute_request" in module.__all__


def test_studio_uses_only_public_feature_app_apis() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "studio" / "gui_entry.py").read_text(encoding="utf-8")
    for package in ("story", "audio", "image", "video"):
        assert f"from {package}.app_api import" in source
        assert f"from {package}.gui" not in source
    assert "studio._shared" not in source
