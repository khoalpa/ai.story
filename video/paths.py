from __future__ import annotations

from video.runtime import compute_standard_paths

_PATHS = compute_standard_paths(__file__)
PACKAGE_ROOT = _PATHS["PACKAGE_ROOT"]
PROJECT_ROOT = _PATHS["PROJECT_ROOT"]
PACKAGE_ASSETS_ROOT = _PATHS["PACKAGE_ASSETS_ROOT"]
PROJECT_ASSETS_ROOT = _PATHS["PROJECT_ASSETS_ROOT"]
BUNDLED_ASSETS_ROOT = _PATHS["BUNDLED_ASSETS_ROOT"]
ASSETS_ROOT = _PATHS["ASSETS_ROOT"]
TESTS_ROOT = _PATHS["TESTS_ROOT"]
PACKAGE_PROFILE_ROOT = _PATHS["PACKAGE_PROFILE_ROOT"]


def default_profile_root():
    """Return the canonical asset profile root bundled with the package."""
    return PACKAGE_PROFILE_ROOT
