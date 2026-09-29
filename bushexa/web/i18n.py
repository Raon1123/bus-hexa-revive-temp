"""Lightweight in-house i18n for Bus HeXA (Korean default, English secondary).

Design: "최소 인프라 + 점진 적용" — no Flask-Babel/gettext, no heavy deps.

Public API
----------
translate(key, lang) -> str   : a.k.a. t()
resolve_lang(request) -> str  : reads ?lang= → cookie → default "ko"
SUPPORTED_LANGS : list[str]
DEFAULT_LANG     : str

How to extend coverage incrementally
-------------------------------------
1. Add a new key/value pair to TRANSLATIONS below (ko + en).
2. In the template, replace the Korean literal with {{ t('your.new.key') }}.
   That's it — other templates keep their Korean literals (they still work because
   t() is only called where you explicitly use it, and untouched templates just
   render their own Korean strings directly).
3. If a key is missing or mis-spelled, translate() returns the key itself as a
   visible marker so you notice it during development — no silent breakage.
"""

from __future__ import annotations

SUPPORTED_LANGS: list[str] = ["ko", "en"]
DEFAULT_LANG: str = "ko"

# ---------------------------------------------------------------------------
# Translation dictionary
# TRANSLATIONS[key][lang] = string
# Keys use dot-notation: section.name
# ---------------------------------------------------------------------------
TRANSLATIONS: dict[str, dict[str, str]] = {
    # ── Shell: nav group titles ────────────────────────────────────────────
    "nav.group.information": {"ko": "Information",  "en": "Information"},
    "nav.group.timetable":   {"ko": "Timetable",    "en": "Timetable"},
    "nav.group.tracking":    {"ko": "Tracking",     "en": "Tracking"},

    # ── Shell: nav link labels ─────────────────────────────────────────────
    "nav.info":             {"ko": "버스정보",            "en": "Bus Info"},
    "nav.busno":            {"ko": "버스번호별",           "en": "By Route No."},
    "nav.running":          {"ko": "Running Log",        "en": "Running Log"},
    "nav.unist_timetable":  {"ko": "UNIST Timetable",   "en": "UNIST Timetable"},
    "nav.unist_board":      {"ko": "From UNIST",        "en": "From UNIST"},
    "nav.stops":            {"ko": "To UNIST",          "en": "To UNIST"},
    "nav.board":            {"ko": "Departure Board",   "en": "Departure Board"},

    # ── Shell: footer & default page title ────────────────────────────────
    "footer.made_by":       {"ko": "Made by",            "en": "Made by"},
    "footer.credit":        {"ko": "UNIST 통학버스 정보 시스템 · Made by", "en": "UNIST Bus Info System · Made by"},
    "page.default_title":   {"ko": "UNIST 버스정보",      "en": "UNIST Bus Info"},

    # ── Admin nav ──────────────────────────────────────────────────────────
    "admin.nav.group.admin":    {"ko": "Admin",       "en": "Admin"},
    "admin.nav.group.site":     {"ko": "Site",        "en": "Site"},
    "admin.nav.dashboard":      {"ko": "대시보드",      "en": "Dashboard"},
    "admin.nav.data_browser":   {"ko": "데이터 브라우저", "en": "Data Browser"},
    "admin.nav.timetable":      {"ko": "시간표 편집",    "en": "Timetable Edit"},
    "admin.nav.via":            {"ko": "경유지 편집",    "en": "Via Stop Edit"},
    "admin.nav.holidays":       {"ko": "공휴일 관리",    "en": "Holiday Mgmt"},
    "admin.nav.special":        {"ko": "특별 시간표",    "en": "Special Timetable"},
    "admin.nav.changelog":      {"ko": "변경이력 관리",  "en": "Changelog"},
    "admin.nav.logs":           {"ko": "로그",          "en": "Logs"},
    "admin.nav.password":       {"ko": "비밀번호 변경",  "en": "Change Password"},
    "admin.nav.public_site":    {"ko": "공개 사이트",    "en": "Public Site"},
    "admin.nav.logout":         {"ko": "로그아웃",       "en": "Log out"},

    # ── Board page ─────────────────────────────────────────────────────────
    "board.title":          {"ko": "UNIST 출발안내",      "en": "UNIST Departures"},
    "board.notice.743":    {"ko": "10월 3일부터 743번은 구영리에서 범서중학교를 경유합니다 (513번과 같은 경로, 713·753·1115번과 다름). 자세한 경로는 정보 페이지의 노선도를 확인하세요.",
                            "en": "From Oct 3, bus 743 passes Beomseo Middle School in Guyoung-ri (same as 513; different from 713/753/1115). See the route map on the Info page."},
    "board.page_title":     {"ko": "출발 게시판",          "en": "Departure Board"},
    "board.btn.table":      {"ko": "표",                 "en": "Table"},
    "board.btn.flap":       {"ko": "Split-flap",         "en": "Split-flap"},

    # ── Language switcher UI labels ────────────────────────────────────────
    "lang.ko":              {"ko": "한국어",              "en": "한국어"},
    "lang.en":              {"ko": "English",            "en": "English"},
}


def translate(key: str, lang: str) -> str:
    """Return the translation for *key* in *lang*.

    Fallback chain:
      1. requested lang
      2. DEFAULT_LANG ("ko")
      3. the key itself (so untranslated keys are visible, not broken)
    """
    entry = TRANSLATIONS.get(key)
    if entry is None:
        return key
    return entry.get(lang) or entry.get(DEFAULT_LANG) or key


# Convenient alias used by templates via context processor.
t = translate


def resolve_lang(request) -> str:  # type: ignore[type-arg]
    """Determine the active language for *request*.

    Resolution order:
      1. ``?lang=`` query parameter (if valid)
      2. ``lang`` cookie
      3. DEFAULT_LANG ("ko")
    """
    q = request.args.get("lang", "")
    if q in SUPPORTED_LANGS:
        return q
    cookie = request.cookies.get("lang", "")
    if cookie in SUPPORTED_LANGS:
        return cookie
    return DEFAULT_LANG
