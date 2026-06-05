/* boardclock.js — 출발안내 상단 시계 라이브 동기화
 *
 * 문제: 상단 시각(#dboard-time)은 페이지 로드 시 서버값으로 한 번만 렌더되고,
 *       HTMX 폴링은 #board-table(표)만 교체하므로 시계가 멈춰 보였다.
 * 해결: 브라우저에서 매초 KST(Asia/Seoul) 현재 시각을 계산해 HH:MM으로 갱신.
 *       (요일 라벨 <small>은 공휴일 판정이 서버 도메인에 있으므로 서버 렌더값 유지.)
 */
(function () {
  "use strict";

  function kstHHMM() {
    // 브라우저 로컬 TZ와 무관하게 항상 한국시간(Asia/Seoul) HH:MM
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Seoul",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date());
  }

  function tick() {
    var el = document.getElementById("dboard-time");
    if (!el) return;
    var now = kstHHMM();
    if (el.textContent !== now) el.textContent = now;
  }

  function start() {
    tick();
    setInterval(tick, 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
