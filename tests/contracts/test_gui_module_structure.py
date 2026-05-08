from __future__ import annotations

import importlib
from pathlib import Path


GUI_PACKAGES = ("story", "audio", "image", "video")
GUI_CORE_FILES = (
    "__init__.py",
    "app.py",
    "settings.py",
    "sidebar.py",
    "main_panel.py",
    "service.py",
    "state.py",
    "tabs.py",
    "view_models.py",
)


def test_gui_packages_share_core_file_structure() -> None:
    for package in GUI_PACKAGES:
        gui_dir = Path(package) / "gui"
        missing = [filename for filename in GUI_CORE_FILES if not (gui_dir / filename).is_file()]
        assert missing == [], f"{package}.gui missing core files: {missing}"


def test_gui_settings_and_sidebar_expose_common_entrypoints() -> None:
    for package in GUI_PACKAGES:
        settings = importlib.import_module(f"{package}.gui.settings")
        sidebar = importlib.import_module(f"{package}.gui.sidebar")
        assert callable(getattr(settings, f"get_{package}_settings", None))
        assert callable(getattr(settings, "get_settings", None))
        assert callable(getattr(settings, "render_settings", None))
        assert callable(getattr(settings, "render_settings_sidebar", None))
        assert callable(getattr(settings, "render_sidebar", None))
        assert callable(getattr(sidebar, "render_settings_sidebar", None))
        assert callable(getattr(sidebar, "render_sidebar", None))


def test_gui_apps_expose_domain_and_generic_entrypoints() -> None:
    for package in GUI_PACKAGES:
        app = importlib.import_module(f"{package}.gui.app")
        assert callable(getattr(app, "main", None))
        assert callable(getattr(app, f"render_{package}_workspace", None))
        assert callable(getattr(app, f"render_{package}_studio", None))
        assert callable(getattr(app, "render_workspace", None))
        assert callable(getattr(app, "render_studio", None))


def test_gui_main_panels_expose_domain_and_generic_entrypoints() -> None:
    for package in GUI_PACKAGES:
        main_panel = importlib.import_module(f"{package}.gui.main_panel")
        assert callable(getattr(main_panel, f"render_{package}_main_panel", None))
        assert callable(getattr(main_panel, "render_main_panel", None))


def test_gui_packages_expose_workspace_renderers() -> None:
    for package in GUI_PACKAGES:
        module = importlib.import_module(f"{package}.gui")
        assert callable(getattr(module, "main", None))
        assert callable(getattr(module, f"render_{package}_workspace", None))
        assert callable(getattr(module, f"render_{package}_studio", None))
        assert callable(getattr(module, "render_workspace", None))
        assert callable(getattr(module, "render_studio", None))

