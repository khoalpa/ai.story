from __future__ import annotations

import hashlib
import io
import json
import stat
import zipfile

import pytest
from PIL import Image

from studio import workflow_package as packages


def encoded(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def rebind(members, path, raw):
    members[path] = raw
    manifest = json.loads(members["manifest.json"])
    for row in manifest["files"]:
        if row["path"] == path:
            row.update(size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    members["manifest.json"] = encoded(manifest)


def failed(result, name):
    assert result["status"] == "FAIL"
    assert result["publish_status"] == "FAIL"
    assert next(row for row in result["checks"] if row["check"] == name)["status"] == "FAIL"


@pytest.mark.parametrize("field,value,check", [
    ("stage", None, "manifest_schema"), ("stage", True, "manifest_schema"),
    ("stage", [], "manifest_schema"), ("stage", 9, "manifest_schema"),
    ("status", [], "manifest_schema"), ("schema_version", "3.16", "manifest_schema"),
    ("parent_package_sha256", "x" * 64, "manifest_schema"),
    ("files", None, "manifest_files"), ("files", [None], "manifest_files"),
    ("files", [], "file_set"),
])
def test_invalid_manifest_is_reported(sample_package_members, field, value, check):
    members = dict(sample_package_members("story_stage1.zip"))
    manifest = json.loads(members["manifest.json"])
    manifest[field] = value
    members["manifest.json"] = encoded(manifest)
    failed(packages.inspect_members(members), check)


@pytest.mark.parametrize("raw", [b'{', b'[]', b'{"stage":1,"stage":2}', b'\xff'])
def test_invalid_manifest_json_is_reported(raw):
    failed(packages.inspect_members({"manifest.json": raw}), "manifest_schema")


def test_missing_tampered_and_unlisted_payloads_fail(sample_package_members):
    source = sample_package_members("story_stage1.zip")
    missing = dict(source)
    del missing["story.json"]
    failed(packages.inspect_members(missing), "file_set")
    changed = dict(source)
    changed["story.json"] += b" "
    failed(packages.inspect_members(changed), "file_digest")
    extra = dict(source, unexpected=b"not declared")
    failed(packages.inspect_members(extra), "file_set")
    invalid = dict(source)
    rebind(invalid, "story.json", b'{"schema_version":NaN}')
    failed(packages.inspect_members(invalid), "strict_json")


@pytest.mark.parametrize("kind", ["corrupt", "portrait", "wrong_size", "bad_targets"])
def test_declared_landscape_image_is_verified(sample_package_members, kind):
    members = dict(sample_package_members("story_stage2.zip"))
    if kind in {"wrong_size", "bad_targets"}:
        plan = json.loads(members["visual_plan.json"])
        plan["targets"] = None if kind == "bad_targets" else {"landscape": {"size_policy": "EXACT", "width": 1, "height": 1}}
        rebind(members, "visual_plan.json", encoded(plan))
    else:
        raw = io.BytesIO()
        if kind == "portrait":
            Image.new("RGB", (8, 16)).save(raw, format="PNG")
        rebind(members, "landscape/cover.png", raw.getvalue())
    failed(packages.inspect_members(members), "image_files")


@pytest.mark.parametrize("name", ["../outside.json", "/absolute.json", "C:/escape.json", "bad\\path.json"])
def test_directory_does_not_read_unsafe_manifest_paths(tmp_path, monkeypatch, name):
    (tmp_path / "manifest.json").write_bytes(encoded({"files": [{"path": name}]}))
    contract = packages.load_prompt_contract()
    original = type(tmp_path).read_bytes
    reads = []

    def record(path):
        reads.append(path)
        return original(path)

    monkeypatch.setattr(type(tmp_path), "read_bytes", record)
    result = packages.inspect_directory(tmp_path, contract=contract)
    assert result["status"] == "FAIL"
    assert reads == [tmp_path / "manifest.json"]
    assert any("không an toàn" in row["detail"] for row in result["checks"])


def test_directory_reports_invalid_files_array(tmp_path):
    (tmp_path / "manifest.json").write_bytes(encoded({"files": None}))
    assert packages.inspect_directory(tmp_path)["status"] == "FAIL"


@pytest.mark.parametrize("names", [["../story.json"], ["Story.json", "story.json"], ["path./story.json"]])
def test_archive_rejects_unsafe_or_colliding_members(names):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        for name in names:
            archive.writestr(name, b"{}")
    with pytest.raises(ValueError, match="không an toàn"):
        packages.read_archive(raw.getvalue())


def test_archive_rejects_symlinks_and_resource_limit(monkeypatch):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, "w") as archive:
        info = zipfile.ZipInfo("story.json")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "outside.json")
    with pytest.raises(ValueError, match="không an toàn"):
        packages.read_archive(raw.getvalue())
    monkeypatch.setattr(packages, "MAX_PACKAGE_BYTES", 1)
    with pytest.raises(ValueError, match="giới hạn"):
        packages.read_archive(raw.getvalue())
