from __future__ import annotations

import json
import zipfile

from studio.legacy_compatibility import inspect_legacy_package


def test_legacy_router_is_exact_and_never_auto_migrates(tmp_path):
    path = tmp_path / "stage2_checkpoint.zip"
    members = {"story.json": json.dumps({"schema_version": "2.2", "characters": []}).encode()}
    members.update({f"legacy_{index}.json": b"{}" for index in range(12)})
    with zipfile.ZipFile(path, "w") as archive:
        for name, raw in members.items():
            archive.writestr(name, raw)
    result = inspect_legacy_package(path)
    assert result["status"] == "MIGRATION_REQUIRED"
    assert result["adapter_id"] == "LEGACY_PROGRESSIVE_PACKAGE_ADAPTER_01"


def test_legacy_router_rejects_unlisted_basename(tmp_path):
    path = tmp_path / "almost_stage2.zip"
    path.write_bytes(b"not used")
    result = inspect_legacy_package(path)
    assert result["status"] == "MIGRATION_REQUIRED"
    assert result["adapter_id"] is None
