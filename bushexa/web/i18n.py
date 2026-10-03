"""Lightweight in-house i18n for Bus HeXA (Korean default, English secondary).

Design: "최소 인프라 + 점진 적용" — no Flask-Babel/gettext, no heavy deps.

Public API
----------
translate(key, lang, **kw) -> str : a.k.a. t(); kw는 str.format 플레이스홀더
resolve_lang(request) -> str      : ?lang= → cookie → Accept-Language → "ko"
localize_stop(raw, lang, names)   : 정류소 이름 번역(ADR-014, 렌더 계층 전용)
lang_url(request, lang) -> str    : 현재 URL의 쿼리를 보존한 채 lang만 교체
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

import re
from urllib.parse import urlencode

from bushexa.data.constants import clean_stop_name

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
    "nav.busan":            {"ko": "부산 가는 길",       "en": "To Busan"},
    "nav.seoul":            {"ko": "서울 가는 길",       "en": "To Seoul"},
    "nav.ktx":              {"ko": "KTX 연계표",         "en": "KTX Connections"},

    # ── 요일별 KTX 연계표 (/ktx) ──
    "ktx.title":            {"ko": "KTX 연계표", "en": "KTX ↔ Bus 513 Connections"},
    "ktx.intro.out":         {"ko": "울산역에서 떠나는 KTX마다 출발 {transfer}분 전까지 울산역에 닿는 가장 늦은 버스입니다.", "en": "For each KTX from Ulsan Station: the latest bus reaching the station {transfer} min before departure."},
    "ktx.intro.in":          {"ko": "울산역에 도착하는 KTX마다 {transfer}분 뒤부터 탈 수 있는 첫 버스입니다.", "en": "For each KTX arriving at Ulsan Station: the first bus you can take {transfer} min after arrival."},
    "ktx.form.station":     {"ko": "울산역 환승 최소", "en": "Min. transfer at Ulsan Stn"},
    "ktx.form.jinmok":      {"ko": "진목회관 환승 최소", "en": "Min. transfer at Jinmok Hall"},
    "ktx.form.min":         {"ko": "분", "en": " min"},
    "ktx.form.apply":       {"ko": "적용", "en": "Apply"},
    "ktx.opt.513":          {"ko": "① 513 직행", "en": "① Bus 513 direct"},
    "ktx.opt.5001":         {"ko": "② 5001 + 진목회관 환승", "en": "② Bus 5001 + transfer at Jinmok Hall"},
    "ktx.opt.proxied":       {"ko": "추정치 · 실시간 도착 확인", "en": "estimated · check live arrivals"},
    "ktx.row.a_unist_dep":  {"ko": "UNIST 발 (버스)", "en": "Leave UNIST (bus)"},
    "ktx.row.a_jinmok_arr":  {"ko": "진목회관 착 · 길 건너기", "en": "Jinmok Hall arr. · cross"},
    "ktx.row.a_5001_jinmok": {"ko": "5001 진목회관 발", "en": "5001 Jinmok Hall dep."},
    "ktx.row.a_5001_station": {"ko": "5001 울산역 착", "en": "5001 Ulsan Stn arr."},
    "ktx.row.a_5001_station_dep": {"ko": "5001 울산역 발", "en": "5001 Ulsan Stn dep."},
    "ktx.row.a_feeder":     {"ko": "환승 버스 진목회관 발", "en": "Transfer bus at Jinmok Hall"},
    "ktx.legend.best.out":   {"ko": "초록: UNIST를 더 늦게 떠나도 되는 안", "en": "Green: lets you leave UNIST later"},
    "ktx.legend.best.in":    {"ko": "초록: UNIST에 먼저 닿는 안", "en": "Green: reaches UNIST first"},
    "ktx.legend.5001":       {"ko": "5001은 UNIST에 서지 않아 진목회관에서 길을 건너 갈아탑니다(작은 숫자: 환승 버스).", "en": "Bus 5001 skips UNIST; cross the road at Jinmok Hall and transfer (small number: transfer bus)."},

    "ktx.dir.out":          {"ko": "UNIST → 울산역 (가는 편)", "en": "UNIST → Ulsan Stn (outbound)"},
    "ktx.dir.in":           {"ko": "울산역 → UNIST (오는 편)", "en": "Ulsan Stn → UNIST (inbound)"},
    "ktx.dest.out.busan":   {"ko": "부산행", "en": "To Busan"},
    "ktx.dest.out.seoul":   {"ko": "서울행", "en": "To Seoul"},
    "ktx.dest.out.suseo":   {"ko": "수서행", "en": "To Suseo"},
    "ktx.dest.in.busan":    {"ko": "부산발", "en": "From Busan"},
    "ktx.dest.in.seoul":    {"ko": "서울발", "en": "From Seoul"},
    "ktx.dest.in.suseo":    {"ko": "수서발", "en": "From Suseo"},
    "ktx.day.0":            {"ko": "평일", "en": "Weekday"},
    "ktx.day.1":            {"ko": "토요일", "en": "Saturday"},
    "ktx.day.2":            {"ko": "일·공휴일", "en": "Sun/Holiday"},
    "ktx.today":            {"ko": "오늘", "en": "today"},
    "ktx.ref_date":         {"ko": "{date} 열차 시간표 기준", "en": "Trains as scheduled on {date}"},
    "ktx.tight":            {"ko": "빠듯", "en": "tight"},
    "ktx.station.busan":    {"ko": "부산", "en": "Busan"},
    "ktx.station.seoul":    {"ko": "서울", "en": "Seoul"},
    "ktx.station.suseo":    {"ko": "수서", "en": "Suseo"},
    "ktx.block.morning":    {"ko": "오전 (~11시)", "en": "Morning (until 11:59)"},
    "ktx.block.afternoon":  {"ko": "오후 (12~17시)", "en": "Afternoon (12:00–17:59)"},
    "ktx.block.evening":    {"ko": "저녁 (18시~)", "en": "Evening (from 18:00)"},
    "ktx.row.no":           {"ko": "열차번호", "en": "Train No."},
    "ktx.row.grade":        {"ko": "종별", "en": "Type"},
    "ktx.row.deokha":       {"ko": "513 덕하 발", "en": "513 Deokha dep."},
    "ktx.row.unist_via":    {"ko": "UNIST(경유) 탑승", "en": "Board at UNIST"},
    "ktx.row.station_bus_arr": {"ko": "울산역 정류장 착", "en": "Ulsan Stn stop arr."},
    "ktx.row.margin":       {"ko": "환승 여유(분)", "en": "Buffer (min)"},
    "ktx.row.ulsan_dep":    {"ko": "울산 발", "en": "Ulsan dep."},
    "ktx.row.dest_arr":     {"ko": "{station} 착", "en": "{station} arr."},
    "ktx.row.origin_dep":   {"ko": "{station} 발", "en": "{station} dep."},
    "ktx.row.ulsan_arr":    {"ko": "울산 착", "en": "Ulsan arr."},
    "ktx.row.wait":         {"ko": "환승 대기(분)", "en": "Wait (min)"},
    "ktx.row.station_bus_dep": {"ko": "513 울산역 발", "en": "513 Ulsan Stn dep."},
    "ktx.row.unist_arr":    {"ko": "UNIST(경유) 착", "en": "UNIST arr."},
    "ktx.row.samnam":       {"ko": "513 삼남 발", "en": "513 Samnam dep."},
    "ktx.row.via":          {"ko": "{station}", "en": "{station}"},
    "ktx.legend.via":        {"ko": "중간역 시각은 도착 · レ 통과 · ‖ 다른 경로", "en": "Intermediate times are arrivals · レ pass · ‖ other line"},
    "ktx.stops_unknown":    {"ko": "정차역을 아직 모르는 열차 {n}편은 빈 칸입니다.", "en": "{n} train(s) with unknown stops are left blank."},
    "ktx.legend.bold":       {"ko": "굵게: 열차", "en": "Bold: trains"},
    "ktx.legend.est":        {"ko": "버스 시각은 예상(덕하·삼남 발은 시간표)", "en": "Bus times are estimates (Deokha/Samnam are timetabled)"},
    "ktx.tight.out":         {"ko": "빠듯: 버스가 늦으면 여유가 {transfer}분보다 짧아집니다", "en": "tight: a late bus leaves less than {transfer} min"},
    "ktx.tight.in":          {"ko": "빠듯: 버스가 일찍 오면 놓칠 수 있습니다", "en": "tight: an early bus may be missed"},
    "ktx.skipped.out":       {"ko": "첫차로도 닿지 못하는 이른 열차 {n}편은 뺐습니다.", "en": "{n} early train(s) no bus can reach are omitted."},
    "ktx.skipped.in":        {"ko": "막차 뒤 도착 열차 {n}편은 뺐습니다.", "en": "{n} train(s) after the last bus are omitted."},
    "ktx.rail_missing":     {"ko": "이 요일의 열차 시간표를 아직 받지 못했습니다(약 2주 앞까지 수집).", "en": "No train timetable for this day type yet (collected about 2 weeks ahead)."},
    "ktx.bus_missing":      {"ko": "513 시간표를 읽지 못했습니다.", "en": "Bus 513 timetable is unavailable."},
    "ktx.profile_missing":   {"ko": "버스 구간 소요 자료가 없어 연계를 계산하지 못했습니다.", "en": "Bus travel-time data is missing."},
    "ktx.no_rows":          {"ko": "이어 탈 수 있는 열차가 없습니다.", "en": "No connecting trains."},


    "ktx.source":            {"ko": "소요: 운행 기록 {start}~{end} · 열차: 국토교통부 TAGO", "en": "Travel times: records {start}–{end} · Trains: MOLIT TAGO"},
    "ktx.link":             {"ko": "요일별 KTX 연계표 보기", "en": "Weekly KTX connection table"},
    "ktx.link_in":          {"ko": "울산역 도착 → UNIST 연계표", "en": "Ulsan Stn → UNIST connections"},

    # ── 서울 가는 길 (/seoul) ──
    "seoul.title":          {"ko": "서울 가는 길", "en": "Getting to Seoul"},
    "seoul.intro":           {"ko": "513으로 울산역까지 간 뒤 KTX로 서울역·수서역에 갑니다.", "en": "Take bus 513 to Ulsan Station, then KTX to Seoul or Suseo."},
    "seoul.step1":          {"ko": "UNIST → 울산역", "en": "UNIST → Ulsan Station"},
    "seoul.step2":          {"ko": "울산역 발차 안내", "en": "Ulsan Station departures"},
    "seoul.board_hint":     {"ko": "불 켜진 역에 섭니다", "en": "Lit stations are stops"},
    "seoul.col.to_seoul":   {"ko": "서울역 KTX", "en": "KTX to Seoul"},
    "seoul.col.to_suseo":   {"ko": "수서역 KTX", "en": "KTX to Suseo"},
    "seoul.tab.all":        {"ko": "전체", "en": "All"},
    "seoul.tab.seoul":      {"ko": "서울역", "en": "Seoul"},
    "seoul.tab.suseo":      {"ko": "수서역", "en": "Suseo"},
    "seoul.missing":        {"ko": "{dest}행 열차 시간표를 아직 받지 못했습니다.", "en": "Timetable to {dest} is not available yet."},
    "seoul.stops_note":      {"ko": "정차역은 오늘·내일 열차만 표시합니다.", "en": "Stops are shown for today's and tomorrow's trains."},
    # ── 역 발차 안내판 (macros/_rail_board.html) ──
    "rb.aria":              {"ko": "열차 발차 안내", "en": "Train departures"},
    "rb.col.dep":           {"ko": "출발", "en": "Dep"},
    "rb.col.type":          {"ko": "종별", "en": "Type"},
    "rb.col.dest":          {"ko": "행선", "en": "To"},
    "rb.col.arr":           {"ko": "도착", "en": "Arr"},
    "rb.bound":             {"ko": "행", "en": "bound"},
    "rb.connect":           {"ko": "지금 오는 513으로 연결", "en": "Reachable by the next 513"},
    "rb.soon":              {"ko": "곧 출발", "en": "Departing"},
    "rb.left":              {"ko": "{min}분 후", "en": "in {min} min"},
    "rb.stops":             {"ko": "정차역", "en": "Stops"},
    "rb.marquee_direct":    {"ko": "{dest} 직행", "en": "Direct to {dest}"},
    "rb.view":              {"ko": "보기", "en": "View"},
    "rb.special.seodaegu":  {"ko": "서대구 정차", "en": "Stops at Seodaegu"},
    "rb.special.suwon":     {"ko": "수원 경유", "en": "Via Suwon"},
    "rb.view.table":        {"ko": "표", "en": "Table"},
    "rb.view.board":        {"ko": "발차 안내판", "en": "Departure board"},
    "rb.no_stops":          {"ko": "정차역 정보 없음", "en": "Stop information unavailable"},
    "rb.empty":             {"ko": "오늘 남은 열차가 없습니다.", "en": "No more trains today."},
    # ── 부산 가는 길 (/busan) ──
    "busan.title":          {"ko": "부산 가는 길", "en": "Getting to Busan"},
    "busan.intro":          {"ko": "지금 UNIST에서 출발하면 어떤 차를 이어 타고 언제 도착하는지 목적지별로 보여 줍니다.",
                             "en": "Next connections from UNIST to Busan, by destination."},
    "busan.as_of":          {"ko": "{time} 기준", "en": "As of {time}"},
    "busan.r1.title":       {"ko": "부산역", "en": "Busan Station"},
    "busan.r1.via":         {"ko": "513 → 울산역 → KTX", "en": "Bus 513 → Ulsan Station → KTX"},
    "busan.r2.title":       {"ko": "노포", "en": "Nopo"},
    "busan.r2.via":         {"ko": "743·753 → 좋은삼정병원앞 환승 → 1224", "en": "Bus 743/753 → transfer at Joeun Samjeong Hospital → Bus 1224"},
    "busan.r3.title":       {"ko": "벡스코 · 부전", "en": "BEXCO · Bujeon"},
    "busan.r3.via":         {"ko": "버스 → 태화강역 → 동해선", "en": "Bus → Taehwagang Station → Donghae Line"},
    "busan.col.bus":        {"ko": "버스", "en": "Bus"},
    "busan.col.unist_arr":  {"ko": "UNIST 도착", "en": "At UNIST"},
    "busan.col.unist_dep":  {"ko": "UNIST 출발", "en": "Leaves UNIST"},
    "busan.col.station":    {"ko": "울산역 도착(예상)", "en": "Ulsan Stn (est.)"},
    "busan.col.ktx":        {"ko": "KTX 출발", "en": "KTX dep."},
    "busan.col.busan_arr":  {"ko": "부산역 도착", "en": "Busan arr."},
    "busan.col.taehwagang":  {"ko": "태화강역(예상)", "en": "Taehwagang (est.)"},
    "busan.col.metro":      {"ko": "동해선 출발", "en": "Donghae Line dep."},
    "busan.col.bexco":      {"ko": "벡스코", "en": "BEXCO"},
    "busan.col.bujeon":     {"ko": "부전", "en": "Bujeon"},
    "busan.col.dep":        {"ko": "출발", "en": "Dep."},
    "busan.col.arr":        {"ko": "도착", "en": "Arr."},
    "busan.col.train":      {"ko": "열차", "en": "Train"},
    "busan.in_min":         {"ko": "{min}분 후", "en": "in {min} min"},
    "busan.live_513":       {"ko": "UNIST로 오는 513(울산역 방면) 실시간", "en": "Live: bus 513 toward Ulsan Station"},
    "busan.no_live_513":    {"ko": "지금 UNIST로 오는 513(울산역 방면) 실시간 정보가 없습니다.",
                             "en": "No live bus 513 (toward Ulsan Station) approaching UNIST right now."},
    "busan.origin_513":      {"ko": "513 덕하 출발 시각(UNIST까지 약 1시간)", "en": "Bus 513 departures from Deokha (about 1 hour to UNIST)"},
    "busan.ktx_next":       {"ko": "울산역 → 부산역 KTX", "en": "KTX Ulsan → Busan"},
    "busan.note_513":        {"ko": "울산역 도착은 UNIST 도착 + {min}분, KTX는 {transfer}분 여유를 두고 고릅니다.", "en": "Ulsan Stn = UNIST arrival + {min} min; KTX chosen with a {transfer}-min buffer."},
    "busan.rail_missing":   {"ko": "열차 시간표를 아직 받지 못했습니다.", "en": "Train timetable not available yet."},
    "busan.rail_suspect":   {"ko": "오늘 열차가 평소보다 훨씬 적게 조회되었습니다. 코레일에서 확인하세요.",
                             "en": "Far fewer trains than usual were listed for today. Please check with Korail."},
    "busan.no_more_trains":  {"ko": "오늘 남은 열차가 없습니다.", "en": "No more trains today."},
    "busan.no_more_buses":  {"ko": "오늘 남은 버스가 없습니다.", "en": "No more buses today."},
    "busan.no_connection":  {"ko": "연결 없음", "en": "No connection"},
    "busan.col.transfer_arr": {"ko": "좋은삼정병원앞 도착", "en": "At Joeun Samjeong Hosp."},
    "busan.col.bus_1224":   {"ko": "갈아탈 1224", "en": "Bus 1224 to catch"},
    "busan.r2.live_1224":   {"ko": "좋은삼정병원앞 1224(노포 방면) 실시간", "en": "Live: bus 1224 toward Nopo at Joeun Samjeong Hospital"},
    "busan.r2.no_live_1224": {"ko": "지금 좋은삼정병원앞으로 오는 1224(노포 방면) 실시간 정보가 없습니다.",
                              "en": "No live bus 1224 (toward Nopo) approaching Joeun Samjeong Hospital right now."},
    "busan.r2.live_transfer": {"ko": "743·753 → 1224 실시간 환승", "en": "Live transfer: bus 743/753 → 1224"},
    "busan.r2.no_live_feeder": {"ko": "지금 좋은삼정병원앞으로 오는 743·753(명촌 방면) 실시간 정보가 없습니다.",
                                "en": "No live bus 743/753 (toward Myeongchon) approaching Joeun Samjeong Hospital right now."},
    "busan.r2.wait_min":    {"ko": "{min}분 대기", "en": "{min} min wait"},
    "busan.r2.no_1224_yet":  {"ko": "아직 운행 중인 1224 없음", "en": "No bus 1224 on the way yet"},
    "busan.r2.running_link": {"ko": "1224 운행 기록 보기", "en": "Bus 1224 run records"},
    "busan.r2.plan_title":  {"ko": "시간표로 보는 연계 (예상)", "en": "Timetable-based connections (estimated)"},
    "busan.r2.plan_dep":    {"ko": "UNIST 출발", "en": "Leaves UNIST"},
    "busan.r2.plan_1224":   {"ko": "갈아탈 1224 통과", "en": "Bus 1224 passes"},
    "busan.r2.plan_live":   {"ko": "실시간", "en": "live"},
    "busan.r2.plan_none":   {"ko": "이후 1224 없음", "en": "No later 1224"},
    "busan.r2.plan_note":   {"ko": "시간표 출발 시각에 추정 소요(743 약 35분, 753 약 28분, 1224 농소 출발 후 약 35분)를 더한 예상입니다. 근처에 실시간 버스가 있으면 실시간 시각으로 바꿔 보이고, 예상끼리 잇는 환승은 여유 3분을 둡니다.",
                              "en": "Estimates: scheduled departure plus an assumed run time (743 ~35 min, 753 ~28 min, 1224 ~35 min after leaving Nongso). Live times replace estimates when a bus is nearby; estimate-to-estimate transfers keep a 3 min margin."},
    "busan.r2.unist_dep":   {"ko": "743·753 UNIST 출발(시간표)", "en": "Bus 743/753 departures from UNIST (timetable)"},
    "busan.r2.note":         {"ko": "743·753과 1224는 같은 좋은삼정병원앞 정류장에 섭니다.", "en": "Buses 743/753 and 1224 use the same stop at Good Samsung Hospital."},
    "busan.r3.note":         {"ko": "태화강역 도착은 예상 시각이며, 승강장까지 5~8분 여유를 둡니다.", "en": "Taehwagang arrival is estimated, with 5–8 min to the platform."},
    "busan.metro_saturday":  {"ko": "토요일은 휴일 시간표로 안내합니다.", "en": "Saturday uses the holiday timetable."},
    "busan.metro_missing":  {"ko": "동해선 시간표를 아직 받지 못했습니다.", "en": "Donghae Line timetable not available yet."},
    "busan.intercity":      {"ko": "태화강역 → 부전 일반·고속열차 (KTX-이음·ITX-마음·무궁화)", "en": "Taehwagang → Bujeon intercity trains (KTX-Eum, ITX-Maeum, Mugunghwa)"},
    "busan.arrival_error":  {"ko": "실시간 정보를 가져오지 못했습니다. 시간표 정보만 표시합니다.",
                             "en": "Live information is unavailable. Showing timetables only."},
    "busan.source":          {"ko": "열차: 국토교통부 TAGO 시간표(매일 갱신)", "en": "Trains: MOLIT TAGO timetable (updated daily)"},

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
    "board.page_title":     {"ko": "출발 게시판",          "en": "Departure Board"},
    "board.btn.table":      {"ko": "표",                 "en": "Table"},
    "board.btn.flap":       {"ko": "Split-flap",         "en": "Split-flap"},

    # ── Stop names: parenthetical annotations & direction (ADR-014) ────────
    # 방향 주석은 목적지 이름으로 표기한다: 시내 → Ulsan, 학교/UNIST → UNIST.
    "stop.annot.city":      {"ko": "시내",               "en": "Ulsan"},
    "stop.annot.unist":     {"ko": "UNIST",              "en": "UNIST"},
    "stop.annot.terminus":  {"ko": "종점",               "en": "Terminus"},
    "stop.annot.origin":    {"ko": "기점",               "en": "Origin"},
    "stop.annot.via":       {"ko": "경유",               "en": "Via"},
    "stop.annot.from_date": {"ko": "{date}부터",          "en": "from {date}"},
    "dir.towards":          {"ko": "{stop} 방면",         "en": "To {stop}"},

    # ── Arrival info: /stops, /unist ───────────────────────────────────────
    "arrival.min_sec":      {"ko": "{m}분 {s}초",          "en": "{m}m {s}s"},
    "arrival.scheduled":    {"ko": "{time} 출발 예정",      "en": "Departs {time}"},
    "arrival.no_service":   {"ko": "운행 종료 또는 정보 없음", "en": "Service ended or no info"},
    "stops.title":          {"ko": "정류소별 버스 도착 정보", "en": "Arrivals by Stop"},
    "stops.select_label":   {"ko": "정류소 선택:",          "en": "Select a stop:"},
    "stops.select_prompt":  {"ko": "-- 정류소를 선택해주세요 --", "en": "-- Select a stop --"},
    "stops.loading":        {"ko": "불러오는 중…",          "en": "Loading…"},
    "stops.pick_hint":      {"ko": "정류소를 선택하면 도착 정보가 표시됩니다.", "en": "Select a stop to see arrival info."},
    "stops.error":          {"ko": "실시간 정보를 가져오지 못했습니다:", "en": "Could not fetch live info:"},
    "stops.long_gap":       {"ko": "첫 번째 버스와 두 번째 버스의 간격이 30분 이상입니다.", "en": "The gap between the first and second bus is 30 minutes or more."},
    "stops.no_bus":         {"ko": "운행 중인 버스가 없습니다.", "en": "No buses are running."},
    "stops.col.route":      {"ko": "노선",                "en": "Route"},
    "stops.col.direction":  {"ko": "방향",                "en": "Direction"},
    "stops.col.eta":        {"ko": "도착 예상",            "en": "Arriving in"},
    "stops.col.position":   {"ko": "현재 위치",            "en": "Current stop"},
    "stops.col.vehicle":    {"ko": "차량번호",             "en": "Vehicle No."},
    # ── 기한형 공지 (services/notices.py) ───────────────────────────────────
    "notice.region":             {"ko": "공지",       "en": "Notices"},
    "notice.more":               {"ko": "자세히",     "en": "Details"},
    "notice.kind.info":          {"ko": "안내",       "en": "Info"},
    "notice.kind.route_change":  {"ko": "노선 변경",  "en": "Route change"},
    "notice.kind.warning":       {"ko": "주의",       "en": "Caution"},
    "notice.kind.suspension":    {"ko": "운행 중단",  "en": "Suspended"},

    # ── Language switcher UI labels ────────────────────────────────────────
    "lang.ko":              {"ko": "한국어",              "en": "한국어"},
    "lang.en":              {"ko": "English",            "en": "English"},
}


def translate(key: str, lang: str, **kwargs: object) -> str:
    """Return the translation for *key* in *lang*.

    Fallback chain:
      1. requested lang
      2. DEFAULT_LANG ("ko")
      3. the key itself (so untranslated keys are visible, not broken)

    *kwargs* fill ``{name}`` placeholders via ``str.format``. A missing placeholder
    returns the unformatted template rather than raising (render must not 500).
    """
    entry = TRANSLATIONS.get(key)
    if entry is None:
        return key
    text = entry.get(lang) or entry.get(DEFAULT_LANG) or key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


# Convenient alias used by templates via context processor.
t = translate


def resolve_lang(request) -> str:  # type: ignore[type-arg]
    """Determine the active language for *request*.

    Resolution order:
      1. ``?lang=`` query parameter (if valid)
      2. ``lang`` cookie
      3. ``Accept-Language`` best match (first visit only — explicit choice wins)
      4. DEFAULT_LANG ("ko")
    """
    q = request.args.get("lang", "")
    if q in SUPPORTED_LANGS:
        return q
    cookie = request.cookies.get("lang", "")
    if cookie in SUPPORTED_LANGS:
        return cookie
    return request.accept_languages.best_match(SUPPORTED_LANGS, default=DEFAULT_LANG)


def lang_url(request, lang: str) -> str:  # type: ignore[type-arg]
    """현재 경로 + 기존 쿼리(반복 키 포함)를 보존하고 ``lang``만 교체한 URL."""
    params = [(k, v) for k, vs in request.args.lists() if k != "lang" for v in vs]
    params.append(("lang", lang))
    return f"{request.path}?{urlencode(params)}"


# ---------------------------------------------------------------------------
# Stop names (ADR-014) — 한국어 원문은 도메인·DB에 그대로 두고 렌더 직전에만 번역한다.
# 사전 자체(StopNames)는 bushexa.services.stop_name_dict 가 관리자 편집 파일에서 로드한다.
# ---------------------------------------------------------------------------

_ANNOT_KEYS: dict[str, str] = {
    "시내": "stop.annot.city",
    "시내방향": "stop.annot.city",
    "시내 방향": "stop.annot.city",
    "시내 방면": "stop.annot.city",
    "UNIST": "stop.annot.unist",
    "학교": "stop.annot.unist",
    "종점": "stop.annot.terminus",
    "기점": "stop.annot.origin",
    "경유": "stop.annot.via",
}
_PAREN_RE = re.compile(r"\(([^)]*)\)")
_FROM_DATE_RE = re.compile(r"^(\d{1,2}/\d{1,2})\s*부터$")
_TOWARDS_SUFFIX = "방면"
_JOIN = " - "


def _localize_annotation(part: str, lang: str, names) -> str:
    part = part.strip()
    key = _ANNOT_KEYS.get(part)
    if key:
        return translate(key, lang)
    m = _FROM_DATE_RE.match(part)
    if m:
        return translate("stop.annot.from_date", lang, date=m.group(1))
    return names.lookup(part, lang) or part


def localize_stop(raw: str, lang: str, names) -> str:
    """정류소 이름(또는 그 조합)을 *lang*으로 표시할 문자열로 바꾼다.

    - ``ko``(또는 빈 값)는 원문 그대로(비용 0).
    - ``"천상 - 구영리 - 명촌 (종점)"`` 같은 경유 문자열은 `` - `` 토큰별로 번역.
    - ``"명촌 (시내) 방면"`` → ``dir.towards``(en ``"To Myeongchon (Ulsan)"``).
    - ``"진목회관 (시내)"`` → 기준명은 사전, 괄호 주석은 ``stop.annot.*`` 어휘(없으면 사전, 그래도 없으면 원문).
    - 사전에 없는 기준명은 한국어 원문을 유지한다(깨지지 않는 폴백).
    """
    if not raw or lang == DEFAULT_LANG:
        return raw
    if _JOIN in raw:
        return _JOIN.join(localize_stop(tok, lang, names) for tok in raw.split(_JOIN))
    stripped = raw.strip()
    if stripped.endswith(_TOWARDS_SUFFIX) and stripped != _TOWARDS_SUFFIX:
        inner = stripped[: -len(_TOWARDS_SUFFIX)].strip()
        return translate("dir.towards", lang, stop=localize_stop(inner, lang, names))
    base = clean_stop_name(stripped)
    out = names.lookup(base, lang) or base
    for annot in _PAREN_RE.findall(stripped):
        parts = [_localize_annotation(p, lang, names) for p in annot.split(",")]
        out += f" ({', '.join(parts)})"
    return out
