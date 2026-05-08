from __future__ import annotations

from image.gui.state import IMAGE_DEFAULTS


def test_image_local_adetailer_like_pass_defaults_enabled() -> None:
    assert IMAGE_DEFAULTS["image_local_adetailer_enabled"] is True


def test_image_settings_fallback_defaults_local_adetailer_enabled() -> None:
    content = __import__("pathlib").Path("image/gui/settings.py").read_text(encoding="utf-8")
    assert 'st.session_state.get("image_local_adetailer_enabled", True)' in content

