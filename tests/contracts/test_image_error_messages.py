from __future__ import annotations

import importlib
import sys
import types


def test_image_error_normalization_repairs_mojibake() -> None:
    original_modules = {
        "streamlit": sys.modules.get("streamlit"),
        "common.gui.user_messages": sys.modules.get("common.gui.user_messages"),
        "image.gui.common_ui": sys.modules.get("image.gui.common_ui"),
    }
    sys.modules["streamlit"] = types.SimpleNamespace()
    user_messages = types.ModuleType("common.gui.user_messages")
    user_messages.UserMessage = object
    user_messages.render_user_message = lambda *args, **kwargs: None
    sys.modules["common.gui.user_messages"] = user_messages
    sys.modules.pop("image.gui.common_ui", None)
    try:
        common_ui = importlib.import_module("image.gui.common_ui")

        message = common_ui._normalize_exc(RuntimeError("KhÃƒÂ´ng tÃƒÂ¬m thÃ¡ÂºÂ¥y workflow JSON"))

        assert message == "RuntimeError: Không tìm thấy workflow JSON"
    finally:
        for name, module in original_modules.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
