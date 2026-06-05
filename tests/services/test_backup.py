"""Feature 3: 백업/복구 서비스 검증."""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from bushexa.services.backup import (
    RestoreError,
    _MANIFEST,
    _is_safe_path,
    create_backup_zip,
    validate_and_restore,
)


# ── 경로 안전 검증 ────────────────────────────────────────────────────────────

class TestIsSafePath:
    def test_manifest_allowed(self):
        assert _is_safe_path("MANIFEST.json")

    def test_flat_files_allowed(self):
        assert _is_safe_path("holidays.json")
        assert _is_safe_path("special_timetables.json")
        assert _is_safe_path("via_overrides.json")

    def test_special_edition_allowed(self):
        assert _is_safe_path("timetable/special/exam/513.json")

    def test_absolute_path_rejected(self):
        assert not _is_safe_path("/etc/passwd")

    def test_dotdot_rejected(self):
        assert not _is_safe_path("../etc/passwd")
        assert not _is_safe_path("timetable/special/../../evil.json")

    def test_backslash_rejected(self):
        assert not _is_safe_path("timetable\\special\\edition\\513.json")

    def test_unknown_file_rejected(self):
        assert not _is_safe_path("evil.json")
        assert not _is_safe_path("timetable/data.json")   # 깊이가 다름

    def test_special_too_deep_rejected(self):
        assert not _is_safe_path("timetable/special/ed/sub/513.json")  # depth 5


# ── 내보내기 ──────────────────────────────────────────────────────────────────

class TestCreateBackupZip:
    def test_export_contains_manifest(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        tt_dir = tmp_path / "timetable"
        tt_dir.mkdir()

        zb = create_backup_zip(data_dir, tt_dir)
        with zipfile.ZipFile(io.BytesIO(zb)) as zf:
            assert _MANIFEST in zf.namelist()

    def test_export_includes_flat_files(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        tt_dir = tmp_path / "timetable"
        tt_dir.mkdir()

        (data_dir / "holidays.json").write_text('["20260101"]', encoding="utf-8")
        (data_dir / "via_overrides.json").write_text('{}', encoding="utf-8")

        zb = create_backup_zip(data_dir, tt_dir)
        with zipfile.ZipFile(io.BytesIO(zb)) as zf:
            names = zf.namelist()
        assert "holidays.json" in names
        assert "via_overrides.json" in names
        # special_timetables.json이 없으면 포함 안 됨 (skip)
        assert "special_timetables.json" not in names

    def test_export_includes_special_editions(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        tt_dir = tmp_path / "timetable"
        special_dir = tt_dir / "special" / "exam-week"
        special_dir.mkdir(parents=True)
        (special_dir / "513.json").write_text('{"0": {}}', encoding="utf-8")

        zb = create_backup_zip(data_dir, tt_dir)
        with zipfile.ZipFile(io.BytesIO(zb)) as zf:
            names = zf.namelist()
        assert "timetable/special/exam-week/513.json" in names

    def test_manifest_has_version_and_timestamp(self, tmp_path):
        zb = create_backup_zip(tmp_path / "data", tmp_path / "timetable")
        with zipfile.ZipFile(io.BytesIO(zb)) as zf:
            manifest = json.loads(zf.read(_MANIFEST))
        assert manifest.get("version") == 1
        assert "exported_at" in manifest


# ── 복구 ──────────────────────────────────────────────────────────────────────

class TestValidateAndRestore:

    def _make_zip(self, files: dict[str, str]) -> bytes:
        """files: {arcname: json_content} → bytes"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(_MANIFEST, json.dumps({"version": 1, "exported_at": "2026-06-01T00:00:00"}))
            for name, content in files.items():
                zf.writestr(name, content)
        return buf.getvalue()

    def test_restore_flat_file(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        tt_dir = tmp_path / "timetable"
        tt_dir.mkdir()

        zb = self._make_zip({"holidays.json": '["20260101"]'})
        restored = validate_and_restore(zb, data_dir, tt_dir)

        assert "holidays.json" in restored
        assert (data_dir / "holidays.json").exists()
        assert json.loads((data_dir / "holidays.json").read_text()) == ["20260101"]

    def test_restore_special_edition(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        tt_dir = tmp_path / "timetable"
        tt_dir.mkdir()

        zb = self._make_zip({"timetable/special/exam/513.json": '{"0": {}}'})
        restored = validate_and_restore(zb, data_dir, tt_dir)

        assert "timetable/special/exam/513.json" in restored
        dest = tt_dir / "special" / "exam" / "513.json"
        assert dest.exists()

    def test_malicious_path_traversal_rejected(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        tt_dir = tmp_path / "timetable"
        tt_dir.mkdir()

        # 경로 탐색 시도
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../evil.json", '{}')
        zb = buf.getvalue()

        with pytest.raises(RestoreError) as exc_info:
            validate_and_restore(zb, data_dir, tt_dir)
        assert "허용되지 않은 경로" in str(exc_info.value)

        # 기존 파일 무손상 확인
        assert not (data_dir / "evil.json").exists()

    def test_nonwhitelisted_path_rejected(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        tt_dir = tmp_path / "timetable"
        tt_dir.mkdir()

        zb = self._make_zip({"evil_custom.json": '{}'})

        with pytest.raises(RestoreError):
            validate_and_restore(zb, data_dir, tt_dir)

    def test_invalid_json_rejected(self, tmp_path):
        """JSON 파싱 실패 파일 → RestoreError, 기존 파일 무손상."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        tt_dir = tmp_path / "timetable"
        tt_dir.mkdir()

        # 기존 파일 시드
        (data_dir / "holidays.json").write_text('["existing"]', encoding="utf-8")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(_MANIFEST, json.dumps({"version": 1, "exported_at": "x"}))
            zf.writestr("holidays.json", "NOT VALID JSON {{{{")
        zb = buf.getvalue()

        with pytest.raises(RestoreError) as exc_info:
            validate_and_restore(zb, data_dir, tt_dir)
        assert "파싱 실패" in str(exc_info.value)

        # 기존 파일이 덮어쓰기 되지 않았는지 확인
        assert json.loads((data_dir / "holidays.json").read_text()) == ["existing"]

    def test_not_a_zip_rejected(self, tmp_path):
        with pytest.raises(RestoreError) as exc_info:
            validate_and_restore(b"not a zip file", tmp_path / "data", tmp_path / "timetable")
        assert "ZIP" in str(exc_info.value)
