"""i18n 테스트 — translate(), resolve_lang(), Flask 통합 (lang 쿠키 persistence).

E-13 준수: 기대값은 TRANSLATIONS 상수에서 독립적으로 정해짐.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from bushexa.web.app import create_app
from bushexa.web.i18n import DEFAULT_LANG, SUPPORTED_LANGS, resolve_lang, translate


# ===========================================================================
# 1. translate() 단위 테스트
# ===========================================================================

class TestTranslate:
    def test_ko_default_returned_for_known_key(self):
        """알려진 키의 한국어 값이 반환된다."""
        assert translate("nav.board", "ko") == "Departure Board"

    def test_en_returns_english(self):
        """lang='en' 이면 영어 값이 반환된다."""
        assert translate("board.btn.table", "en") == "Table"
        assert translate("board.btn.flap",  "en") == "Split-flap"

    def test_unknown_key_returns_key_itself(self):
        """존재하지 않는 키는 키 문자열 자체를 반환한다 (graceful degradation)."""
        assert translate("no.such.key", "ko") == "no.such.key"
        assert translate("no.such.key", "en") == "no.such.key"

    def test_unsupported_lang_falls_back_to_ko(self):
        """지원하지 않는 언어 코드는 한국어로 폴백한다."""
        result = translate("board.title", "ja")
        ko_result = translate("board.title", "ko")
        assert result == ko_result

    def test_ko_is_default_lang(self):
        assert DEFAULT_LANG == "ko"

    def test_supported_langs_contains_ko_and_en(self):
        assert "ko" in SUPPORTED_LANGS
        assert "en" in SUPPORTED_LANGS
        assert "ja" not in SUPPORTED_LANGS, "일본어는 지원 언어가 아니어야 한다"


# ===========================================================================
# 2. resolve_lang() 단위 테스트 (Flask request context 필요)
# ===========================================================================

@pytest.fixture
def _app(app_config_test):
    return create_app(app_config_test)


class TestResolveLang:
    def test_query_param_en(self, _app):
        """?lang=en → 'en' 반환."""
        with _app.test_request_context("/?lang=en"):
            from flask import request
            assert resolve_lang(request) == "en"

    def test_query_param_ko(self, _app):
        """?lang=ko → 'ko' 반환."""
        with _app.test_request_context("/?lang=ko"):
            from flask import request
            assert resolve_lang(request) == "ko"

    def test_unsupported_query_param_falls_back_to_default(self, _app):
        """?lang=ja (지원 안 함) → 기본값 'ko' 반환."""
        with _app.test_request_context("/?lang=ja"):
            from flask import request
            assert resolve_lang(request) == DEFAULT_LANG

    def test_cookie_lang(self, _app):
        """쿠키에 lang=en 이 있으면 'en' 반환."""
        with _app.test_request_context("/", headers={"Cookie": "lang=en"}):
            from flask import request
            assert resolve_lang(request) == "en"

    def test_no_lang_falls_back_to_ko(self, _app):
        """?lang=도 쿠키도 없으면 기본값 'ko'."""
        with _app.test_request_context("/"):
            from flask import request
            assert resolve_lang(request) == DEFAULT_LANG

    def test_query_param_overrides_cookie(self, _app):
        """?lang=ko + 쿠키 lang=en → 쿼리 파라미터 우선."""
        with _app.test_request_context("/?lang=ko", headers={"Cookie": "lang=en"}):
            from flask import request
            assert resolve_lang(request) == "ko"


# ===========================================================================
# 3. Flask 통합 — 쿠키 설정·유지·컨텍스트 주입
# ===========================================================================

@pytest.fixture
def board_app(app_config_test):
    """실제 라우트가 있는 앱 (board mock 포함)."""
    from unittest.mock import patch as _patch
    from bushexa.domain.board import BoardRow, BoardSnapshot

    mock_snapshot = BoardSnapshot(
        current_time="10:00",
        weekday_str="평일",
        rows=[],
        error=None,
        is_last_bus=False,
    )
    app = create_app(app_config_test)
    app.config["TESTING"] = True
    return app, mock_snapshot


class TestFlaskIntegration:
    def test_lang_en_query_sets_cookie(self, board_app):
        """?lang=en 요청 시 응답에 lang=en 쿠키가 설정된다."""
        app, snapshot = board_app
        with patch("bushexa.web.routes.board.get_board_data", return_value=snapshot):
            client = app.test_client()
            resp = client.get("/board?lang=en")
        assert resp.status_code == 200
        # Set-Cookie 헤더 확인
        cookies = resp.headers.getlist("Set-Cookie")
        lang_cookie = next((c for c in cookies if c.startswith("lang=")), None)
        assert lang_cookie is not None, f"lang 쿠키가 없음. Set-Cookie: {cookies}"
        assert "lang=en" in lang_cookie

    def test_lang_en_renders_english_strings(self, board_app):
        """?lang=en 으로 /board 요청 시 영어 번역이 HTML 에 포함된다."""
        app, snapshot = board_app
        with patch("bushexa.web.routes.board.get_board_data", return_value=snapshot):
            client = app.test_client()
            resp = client.get("/board?lang=en")
        html = resp.data.decode("utf-8")
        # board.title 영어값 (UNIST Departures)
        assert "UNIST Departures" in html, "영어 board.title 이 HTML 에 없음"

    def test_default_lang_is_ko(self, board_app):
        """lang 파라미터 없이 /board 요청 시 기본 한국어로 렌더된다."""
        app, snapshot = board_app
        with patch("bushexa.web.routes.board.get_board_data", return_value=snapshot):
            client = app.test_client()
            resp = client.get("/board")
        html = resp.data.decode("utf-8")
        # board.title 한국어 기본값
        assert "UNIST 출발안내" in html, "한국어 기본 board.title 이 HTML 에 없음"

    def test_cookie_persists_lang_across_requests(self, board_app):
        """?lang=en 설정 후 다음 요청(lang 파라미터 없음)에서도 영어가 유지된다."""
        app, snapshot = board_app
        with patch("bushexa.web.routes.board.get_board_data", return_value=snapshot):
            client = app.test_client()
            # 1차: lang 쿠키 설정
            client.get("/board?lang=en")
            # 2차: 파라미터 없이 — 쿠키로 유지
            resp2 = client.get("/board")
        html = resp2.data.decode("utf-8")
        assert "UNIST Departures" in html, "쿠키 lang=en 이 유지되지 않음"

    def test_unsupported_lang_query_falls_back_to_ko(self, board_app):
        """?lang=ja (지원 안 함) → 기본 한국어 렌더."""
        app, snapshot = board_app
        with patch("bushexa.web.routes.board.get_board_data", return_value=snapshot):
            client = app.test_client()
            resp = client.get("/board?lang=ja")
        html = resp.data.decode("utf-8")
        assert "UNIST 출발안내" in html
        # 쿠키는 설정되지 않아야 한다 (unsupported lang)
        cookies = resp.headers.getlist("Set-Cookie")
        lang_cookie = next((c for c in cookies if c.startswith("lang=")), None)
        assert lang_cookie is None, f"지원 안 되는 lang 에 대해 쿠키가 설정됨: {lang_cookie}"

    def test_context_processor_injects_t_and_lang(self, board_app):
        """컨텍스트 프로세서가 t()와 lang 을 템플릿에 주입한다 (간접 확인)."""
        app, snapshot = board_app
        with patch("bushexa.web.routes.board.get_board_data", return_value=snapshot):
            client = app.test_client()
            resp = client.get("/board?lang=en")
        html = resp.data.decode("utf-8")
        # lang="en" 이 <html> 태그에 반영되어야 한다
        assert 'lang="en"' in html, "<html lang='en'> 이 없음"


# ===========================================================================
# 4. ADR-014 Phase 0 — 플레이스홀더, Accept-Language, 전환 링크, Vary, 정류소 번역
# ===========================================================================

from bushexa.services.stop_name_dict import StopNames  # noqa: E402
from bushexa.web.i18n import lang_url, localize_stop  # noqa: E402

_NAMES = StopNames(
    aliases={"범서중학교": "범서중학교앞", "울산과학기술원": "UNIST"},
    langs={"en": {
        "명촌": "Myeongchon", "진목회관": "Jinmokhoegwan", "구영리": "Guyeong-ri",
        "범서중학교앞": "Beomseojunghakgyo-ap", "천상": "Cheonsang", "삼남": "Samnam",
        "울산역": "Ulsanyeok",
    }},
)


class TestTranslateKwargs:
    def test_placeholder_filled(self):
        assert translate("dir.towards", "en", stop="Myeongchon") == "To Myeongchon"
        assert translate("dir.towards", "ko", stop="명촌") == "명촌 방면"

    def test_missing_placeholder_returns_template(self):
        assert translate("dir.towards", "en") == "To {stop}"
        assert translate("dir.towards", "en", other="x") == "To {stop}"


class TestAcceptLanguage:
    @pytest.mark.parametrize("header, expected", [
        ("en-US,en;q=0.9", "en"),
        ("ko-KR,ko;q=0.9,en-US;q=0.8", "ko"),
        ("ja,en;q=0.5", "en"),
        ("fr", "ko"),
    ])
    def test_accept_language_first_visit(self, _app, header, expected):
        with _app.test_request_context("/", headers={"Accept-Language": header}):
            from flask import request
            assert resolve_lang(request) == expected

    def test_cookie_beats_accept_language(self, _app):
        with _app.test_request_context(
                "/", headers={"Cookie": "lang=ko", "Accept-Language": "en"}):
            from flask import request
            assert resolve_lang(request) == "ko"


class TestLangUrl:
    def test_preserves_query_and_replaces_lang(self, _app):
        with _app.test_request_context("/busno?bus=713&day=1&lang=ko"):
            from flask import request
            url = lang_url(request, "en")
        assert url.startswith("/busno?")
        assert "bus=713" in url and "day=1" in url
        assert url.count("lang=") == 1 and "lang=en" in url

    def test_repeated_keys_kept(self, _app):
        with _app.test_request_context("/x?a=1&a=2"):
            from flask import request
            assert lang_url(request, "ko") == "/x?a=1&a=2&lang=ko"

    def test_switcher_links_keep_query(self, board_app):
        app, snapshot = board_app
        with patch("bushexa.web.routes.board.get_board_data", return_value=snapshot):
            html = app.test_client().get("/board?foo=bar").data.decode("utf-8")
        assert "/board?foo=bar&amp;lang=en" in html
        assert "/board?foo=bar&amp;lang=ko" in html


class TestVary:
    def test_vary_includes_cookie_and_accept_language(self, board_app):
        app, snapshot = board_app
        with patch("bushexa.web.routes.board.get_board_data", return_value=snapshot):
            resp = app.test_client().get("/board")
        vary = resp.headers.get("Vary", "")
        assert "Cookie" in vary and "Accept-Language" in vary


class TestLocalizeStop:
    @pytest.mark.parametrize("raw, expected", [
        ("명촌", "Myeongchon"),
        ("진목회관 (시내)", "Jinmokhoegwan (Ulsan)"),
        ("진목회관 (UNIST)", "Jinmokhoegwan (UNIST)"),
        ("명촌 (종점)", "Myeongchon (Terminus)"),
        ("울산과학기술원 (경유)", "UNIST (Via)"),
        ("명촌 (시내) 방면", "To Myeongchon (Ulsan)"),
        ("UNIST 방면", "To UNIST"),
        ("삼남 (울산역) 방면", "To Samnam (Ulsanyeok)"),
        ("구영리(범서중학교)", "Guyeong-ri (Beomseojunghakgyo-ap)"),
        ("구영리(범서중학교, 10/3부터)", "Guyeong-ri (Beomseojunghakgyo-ap, from 10/3)"),
        ("천상 - 구영리 - 명촌 (종점)", "Cheonsang - Guyeong-ri - Myeongchon (Terminus)"),
    ])
    def test_en(self, raw, expected):
        assert localize_stop(raw, "en", _NAMES) == expected

    def test_unknown_name_keeps_korean(self):
        assert localize_stop("태화루", "en", _NAMES) == "태화루"
        assert localize_stop("태화루 (시내)", "en", _NAMES) == "태화루 (Ulsan)"

    @pytest.mark.parametrize("raw", ["진목회관 (시내)", "명촌 (시내) 방면", "천상 - 구영리", ""])
    def test_ko_is_identity(self, raw):
        assert localize_stop(raw, "ko", _NAMES) == raw

    def test_stop_filter_uses_request_lang(self, _app):
        from flask import g, render_template_string
        with _app.test_request_context("/"):
            g.lang = "en"
            assert render_template_string("{{ '범서중 (시내)' | stop }}") == \
                "Beomseojunghakgyo-ap (Ulsan)"
            g.lang = "ko"
            assert render_template_string("{{ '범서중 (시내)' | stop }}") == "범서중 (시내)"
