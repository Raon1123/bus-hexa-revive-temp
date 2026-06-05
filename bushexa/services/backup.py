"""설정 백업/복구 서비스 (Feature 3).

백업 번들: holidays.json, special_timetables.json, via_overrides.json,
          timetable/special/**/*.json (특별 에디션 시간표)

보안:
 - 화이트리스트 경로만 export/import 허용
 - import 시 절대경로·".." 경로 차단
 - import 시 각 파일이 유효한 JSON인지 파싱 검증
 - 검증 전부 통과한 경우에만 일괄 기록 (validate-then-write 원자성)
 - 쓰기는 fileio.atomic_write_bytes 경유 (ADR-012)

매니페스트: ZIP 루트의 MANIFEST.json — {"version": 1, "exported_at": ISO8601}
"""
from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from zoneinfo import ZoneInfo

from bushexa import fileio

_KST = ZoneInfo("Asia/Seoul")

# ── 화이트리스트 ──────────────────────────────────────────────────────────────
# 데이터 루트(data_dir) 아래의 고정 파일
_FLAT_FILES = frozenset([
    "holidays.json",
    "special_timetables.json",
    "via_overrides.json",
])

# 특별 시간표 파일은 timetable_dir / special / <edition> / <busno>.json 패턴
_SPECIAL_PREFIX = "timetable/special/"
_MANIFEST = "MANIFEST.json"

MANIFEST_VERSION = 1


def _is_safe_path(zip_name: str) -> bool:
    """집 항목 경로가 화이트리스트 패턴에 속하는지 검증.

    거부 조건:
     - 절대경로 ('/'로 시작)
     - '..' 포함
     - '\\' 포함 (백슬래시 traversal)
     - 화이트리스트 패턴 불일치
    """
    if not zip_name or zip_name.startswith("/") or "\\" in zip_name:
        return False
    parts = PurePosixPath(zip_name).parts
    if ".." in parts:
        return False
    if zip_name == _MANIFEST:
        return True
    if zip_name in _FLAT_FILES:
        return True
    if zip_name.startswith(_SPECIAL_PREFIX):
        # timetable/special/<edition>/<busno>.json
        # parts: ('timetable', 'special', edition, 'xxx.json')  — depth 4
        if len(parts) == 4 and parts[3].endswith(".json"):
            return True
    return False


def _build_manifest() -> dict:
    return {
        "version": MANIFEST_VERSION,
        "exported_at": datetime.now(_KST).isoformat(),
    }


def create_backup_zip(data_dir: Path, timetable_base_dir: Path) -> bytes:
    """현재 설정을 zip 번들로 직렬화하여 bytes 반환.

    Parameters
    ----------
    data_dir : Path
        config.data_dir — holidays.json 등의 위치
    timetable_base_dir : Path
        timetable_dir() 반환값 — special/<edition>/*.json의 부모 디렉터리

    Notes
    -----
    파일이 존재하지 않으면 zip에서 생략한다 (복구 시 무시되는 것과 대칭).
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 매니페스트
        zf.writestr(_MANIFEST, json.dumps(_build_manifest(), ensure_ascii=False, indent=2))

        # 플랫 파일
        for fname in sorted(_FLAT_FILES):
            p = data_dir / fname
            if p.exists():
                zf.write(p, arcname=fname)

        # 특별 에디션 시간표
        special_dir = timetable_base_dir / "special"
        if special_dir.is_dir():
            for json_file in sorted(special_dir.rglob("*.json")):
                try:
                    rel = json_file.relative_to(timetable_base_dir)
                except ValueError:
                    continue
                arc = rel.as_posix()           # "special/<edition>/<busno>.json"
                arc = "timetable/" + arc       # "timetable/special/..."
                if _is_safe_path(arc):
                    zf.write(json_file, arcname=arc)

    return buf.getvalue()


class RestoreError(Exception):
    """복구 실패 시 발생. args[0]에 사용자 표시용 메시지."""


def validate_and_restore(
    zip_bytes: bytes,
    data_dir: Path,
    timetable_base_dir: Path,
) -> list[str]:
    """zip 번들의 유효성을 검증하고 파일을 복구한다.

    Returns
    -------
    restored : list[str]
        실제로 복구된 파일의 arcname 목록 (MANIFEST 제외).

    Raises
    ------
    RestoreError
        zip이 아닌 경우, 경로 traversal/비허용 경로, JSON 파싱 실패.
        *예외 발생 시 기존 파일은 무손상.* (validate-first 패턴)
    """
    # ZIP 유효성
    try:
        buf = io.BytesIO(zip_bytes)
        zf = zipfile.ZipFile(buf, "r")
    except zipfile.BadZipFile:
        raise RestoreError("업로드된 파일이 유효한 ZIP 아카이브가 아닙니다.")

    with zf:
        names = zf.namelist()

        # 1단계: 경로 검증
        bad_paths = [n for n in names if not _is_safe_path(n)]
        if bad_paths:
            raise RestoreError(
                f"허용되지 않은 경로가 포함되어 있습니다: {bad_paths[:5]}"
            )

        # 2단계: JSON 파싱 검증 (MANIFEST 포함 모든 .json 파일)
        raw_by_name: dict[str, bytes] = {}
        for name in names:
            data = zf.read(name)
            try:
                json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise RestoreError(f"{name!r} 의 JSON 파싱 실패: {exc}")
            raw_by_name[name] = data

    # 3단계: 전부 통과 → 일괄 기록 (validate-then-write)
    restored: list[str] = []
    for name, raw_data in raw_by_name.items():
        if name == _MANIFEST:
            continue
        if name in _FLAT_FILES:
            dest = data_dir / name
        elif name.startswith(_SPECIAL_PREFIX):
            # "timetable/special/<edition>/<busno>.json"
            relative = name[len("timetable/"):]   # "special/<edition>/<busno>.json"
            dest = timetable_base_dir / relative
        else:
            # _is_safe_path를 통과했으므로 여기에 도달하면 안 됨
            continue

        fileio.atomic_write_bytes(dest, raw_data)
        restored.append(name)

    return restored
