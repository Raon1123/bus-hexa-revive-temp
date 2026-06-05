/* boardmobile.js — 모바일 세로 전광판 아코디언 (≤480px 전용)
 *
 * 동작:
 *   - 폰 가로폭(≤480px)에서 노선 셀(td.c-route-cell)을 탭하면
 *     해당 출발의 행선(td.c-dest)과 경유 행(tr.dboard-via-row)을 열고/닫는다.
 *   - CSS는 .dboard .dboard-row.is-open 클래스 유무로 show/hide를 제어한다.
 *   - HTMX 15초 스왑 후에도 열린 슬롯 상태를 복원한다(openSlots Set으로 관리).
 *     복원 기준: 화면상 위치 인덱스(슬롯 번호) — splitflap.js와 동일한 슬롯 개념.
 *   - 이벤트 위임: #board-table에 단일 click 핸들러 → HTMX 재삽입 후에도 유효.
 *   - 데스크톱(>480px)에서는 CSS가 아코디언을 비활성화하지만 핸들러는 무해하게 존재.
 *   - 접근성: td.c-route-cell에 role="button" tabindex="0" aria-expanded 부여.
 *     Enter/Space로 키보드 조작 가능.
 */
(function () {
  "use strict";

  var MOBILE_BP = 480;   // px — CSS @media(max-width:480px)와 동일

  /* 현재 열린 슬롯 인덱스 집합. HTMX 스왑 후에도 유지. */
  var openSlots = new Set();

  /* ── 유틸 ────────────────────────────────────────────────── */
  function isMobile() {
    return window.matchMedia("(max-width: " + MOBILE_BP + "px)").matches;
  }

  /* 전광판 내 .dboard-row 목록 (빈-상태 행 제외) */
  function getRows(boardTable) {
    return Array.prototype.slice.call(
      boardTable.querySelectorAll(".dboard .dboard-row")
    );
  }

  /* 슬롯 인덱스로 메인 행 찾기 */
  function rowBySlot(rows, idx) {
    return rows[idx] || null;
  }

  /* ── aria/어포던스 부여 ──────────────────────────────────── */
  function decorateCell(td, isOpen) {
    td.setAttribute("role", "button");
    td.setAttribute("tabindex", "0");
    td.setAttribute("aria-expanded", isOpen ? "true" : "false");
    /* 케브론 affordance: 모바일에서만 시각적으로 표시 (CSS에서 cursor:pointer 추가) */
    td.setAttribute("aria-label", "행선 및 경유 " + (isOpen ? "닫기" : "열기"));
  }

  /* ── 단일 슬롯 토글 ─────────────────────────────────────── */
  function toggleSlot(rows, idx) {
    var row = rowBySlot(rows, idx);
    if (!row) return;

    var isOpen = row.classList.contains("is-open");
    if (isOpen) {
      row.classList.remove("is-open");
      openSlots.delete(idx);
    } else {
      row.classList.add("is-open");
      openSlots.add(idx);
    }

    /* aria-expanded 업데이트 */
    var routeCell = row.querySelector("td.c-route-cell");
    if (routeCell) decorateCell(routeCell, !isOpen);
  }

  /* ── 스왑 후 열린 슬롯 상태 복원 ────────────────────────── */
  function restoreOpenSlots(boardTable) {
    var rows = getRows(boardTable);
    rows.forEach(function (row, idx) {
      var routeCell = row.querySelector("td.c-route-cell");
      var isOpen = openSlots.has(idx);
      if (isOpen) row.classList.add("is-open");
      if (routeCell) decorateCell(routeCell, isOpen);
    });
  }

  /* ── 초기 장식 (HTMX 스왑 포함, 첫 로드 포함) ─────────── */
  function initBoard(boardTable) {
    var rows = getRows(boardTable);
    rows.forEach(function (row, idx) {
      var routeCell = row.querySelector("td.c-route-cell");
      if (!routeCell) return;
      /* 이미 openSlots에 있으면 복원 */
      var isOpen = openSlots.has(idx);
      if (isOpen) row.classList.add("is-open");
      decorateCell(routeCell, isOpen);
    });
  }

  /* ── 이벤트 위임 (stable parent #board-table에 단일 핸들러) */
  function attachDelegation(boardTable) {
    /* click */
    boardTable.addEventListener("click", function (e) {
      var routeCell = e.target.closest("td.c-route-cell");
      if (!routeCell) return;
      var row = routeCell.closest(".dboard-row");
      if (!row) return;
      var rows = getRows(boardTable);
      var idx = rows.indexOf(row);
      if (idx === -1) return;
      toggleSlot(rows, idx);
    });

    /* keyboard: Enter/Space */
    boardTable.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" && e.key !== " ") return;
      var routeCell = e.target.closest("td.c-route-cell");
      if (!routeCell) return;
      e.preventDefault();
      var row = routeCell.closest(".dboard-row");
      if (!row) return;
      var rows = getRows(boardTable);
      var idx = rows.indexOf(row);
      if (idx === -1) return;
      toggleSlot(rows, idx);
    });
  }

  /* ── 진입점 ─────────────────────────────────────────────── */
  function init() {
    var boardTable = document.getElementById("board-table");
    if (!boardTable) return;
    attachDelegation(boardTable);
    initBoard(boardTable);
  }

  /* HTMX afterSwap: #board-table 내용이 교체된 뒤 상태 복원 */
  document.body.addEventListener("htmx:afterSwap", function (e) {
    if (e.target && e.target.id === "board-table") {
      restoreOpenSlots(e.target);
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
