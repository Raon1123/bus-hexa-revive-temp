/* splitflap.js — 출발안내 표시 스타일 전환 (표 / Split-flap)
 *
 * - 기본: 전통 HTML 표(.dboard.table). 서버가 이미 class="dboard table"로 렌더하므로
 *   JS가 없거나 늦어도 표로 보인다.
 * - Split-flap(실험, .dboard.flap): 문자 타일 + '솔라리 보드' 플립.
 *     · 시각  → 숫자 '단위'(per-char) 타일, 0–9 드럼을 돌려 목표 숫자에 안착
 *     · 노선  → 통째 1타일. 보드의 다른 노선들을 배경색과 함께 빠르게 거쳐 감속 후 목표 노선+색에 안착
 *     · 행선  → 통째 1타일. 보드에 실제 있는 '다른 행선'들을 거쳐 목표에 안착
 * - 플립 시점:
 *     · 모드를 split-flap으로 전환할 때(=수동) → 전체 차르륵 reveal
 *     · 15초 HTMX 갱신 후 → 값이 바뀐 셀만 플립(직전값 비교, data-key 기준)
 * - 동작: 셀마다 여러 스텝을 '점점 느려지며'(감속) 돌다 마지막 스텝이 목표값에 멈춘다.
 *   타일끼리는 DOM 순서대로(위→아래, 좌→우) 시차를 두고 시작(차르륵 캐스케이드).
 * - 상태: localStorage('boardDisplay'), 기본 'table'. CDN 의존 없음.
 */
(function () {
  "use strict";

  var lastValues = Object.create(null);  // slotIndex|field → 직전 표시값(스왑에도 유지)

  // ── 타이밍 상수 ──────────────────────────────────────────────
  var DIGIT_STEPS = 8;     // 시각 숫자: 0–9 드럼을 도는 스텝 수
  var WORD_STEPS = 4;      // 행선: 거쳐 가는 중간 값 개수
  var ROUTE_STEPS = 3;     // 노선: 거쳐 가는 중간 노선 개수(적게 유지 → 빠르게 안착)
  var CASCADE_STEP = 70;   // 타일 시작 시차(ms) — 위→아래 차르륵
  var FLIP_FAST = 65;      // 스텝 간격 시작(빠름, ms)
  var FLIP_SLOW = 240;     // 스텝 간격 끝(느림 → 멈춤 직전, ms)

  var timers = [];         // 진행 중 setTimeout 핸들(패스마다 취소)
  var flapOrder = 0;       // 이번 패스에서 타일에 부여하는 순번(캐스케이드 시차)
  var drums = { dests: [], routes: [], routeColor: {} };

  function currentMode() {
    return localStorage.getItem("boardDisplay") || "table";
  }

  function pushTimer(id) { timers.push(id); }
  function clearTimers() {
    timers.forEach(function (id) { clearTimeout(id); });
    timers = [];
  }

  function origValue(cell) {
    if (cell.dataset.val === undefined) {
      cell.dataset.val = cell.textContent.trim();
      cell.dataset.html = cell.innerHTML;   // 표 모드 복원용(노선 배지 등 보존)
    }
    return cell.dataset.val;
  }

  /* 변경감지 키 = 슬롯(화면상 위치 인덱스) + 필드.
     - data-key(내용 기반)는 같은 버스+행선이 FIRST/SECOND로 중복될 수 있어 키가 유일하지 않음.
     - 슬롯 인덱스 기반으로 전환 → 순서가 바뀌면 해당 슬롯의 노선·행선도 플립됨. */
  function cellKey(cell) {
    var row = cell.closest(".dboard-row");
    var slotIdx = 0;
    if (row) {
      var allRows = Array.prototype.slice.call(
        row.closest("tbody").querySelectorAll(".dboard-row")
      );
      slotIdx = allRows.indexOf(row);
    }
    return slotIdx + "|" + (cell.dataset.field || "");
  }

  function eachFlapCell(fn) {
    document.querySelectorAll("#board-table .dboard [data-flap]").forEach(fn);
  }

  /* 보드에 실제 존재하는 값들로 '드럼'을 구성한다(하드코딩 없음).
     - dests: 모든 행선 문자열
     - routes: 모든 노선 문자열
     - routeColor: 노선 → CSS --route 색상 맵 (getComputedStyle로 route-NNN 클래스에서 읽음) */
  function collectDrums() {
    var dests = [];
    document.querySelectorAll("#board-table .dboard [data-field='dest']").forEach(function (c) {
      var v = origValue(c);
      if (v && dests.indexOf(v) === -1) dests.push(v);
    });
    var routes = [];
    var routeColor = {};
    document.querySelectorAll("#board-table .dboard [data-field='route']").forEach(function (c) {
      var v = origValue(c);
      if (v && routes.indexOf(v) === -1) {
        routes.push(v);
        var color = getComputedStyle(c).getPropertyValue("--route").trim();
        if (color) routeColor[v] = color;
      }
    });
    return { dests: dests, routes: routes, routeColor: routeColor };
  }

  // ── 시퀀스(드럼) 빌더 ────────────────────────────────────────
  function digitSeq(target, steps) {
    var t = parseInt(target, 10);
    if (isNaN(t)) return [target];
    var start = (((t - steps) % 10) + 10) % 10;   // steps만큼 올리면 target에 안착
    var seq = [];
    for (var k = 1; k <= steps; k++) seq.push(String((start + k) % 10));
    return seq;  // 마지막 === target
  }

  function valueSeq(target, drum, steps) {
    var pool = drum.filter(function (v) { return v !== target; });
    var seq = [], prev = null;
    for (var k = 0; k < steps; k++) {
      if (!pool.length) { seq.push(target); continue; }
      var pick = pool[Math.floor(Math.random() * pool.length)];
      if (pick === prev && pool.length > 1) {        // 연속 중복은 살짝 피함
        pick = pool[(pool.indexOf(pick) + 1) % pool.length];
      }
      seq.push(pick); prev = pick;
    }
    seq.push(target);  // 마지막 === target
    return seq;
  }

  /* 노선 타일용 콜백: 중간 스텝에서는 해당 노선의 색으로 --route를 덮어쓰고,
     최종 스텝에서는 인라인 오버라이드를 제거해 부모 route-NNN 클래스 색이 적용되도록 한다. */
  function routeOnStep(tile, value, isFinal) {
    if (isFinal) {
      tile.style.removeProperty("--route");
    } else {
      var color = drums.routeColor[value];
      if (color) {
        tile.style.setProperty("--route", color);
      } else {
        tile.style.removeProperty("--route");
      }
    }
  }

  // ── 한 타일을 시퀀스대로 '감속하며' 돌리고 마지막에 멈춤 ──────
  function spin(tile, seq, baseDelay, onStep) {
    var i = 0;
    function step() {
      var v = seq[i];
      var isFinal = i === seq.length - 1;
      if (v === " ") { tile.classList.add("flap-space"); tile.innerHTML = "&nbsp;"; }
      else { tile.classList.remove("flap-space"); tile.textContent = v; }
      if (onStep) onStep(tile, v, isFinal);
      tile.classList.remove("flap-step");
      void tile.offsetWidth;            // reflow → 매 스텝 애니메이션 재생
      tile.classList.add("flap-step");
      i++;
      if (i < seq.length) {
        var p = i / seq.length;         // 진행도(끝일수록 느리게 = 감속)
        var d = FLIP_FAST + (FLIP_SLOW - FLIP_FAST) * (p * p);
        pushTimer(setTimeout(step, d));
      }
    }
    pushTimer(setTimeout(step, baseDelay));
  }

  function makeTile(text) {
    var t = document.createElement("span");
    t.className = "flap-char";
    if (text === " ") { t.classList.add("flap-space"); t.innerHTML = "&nbsp;"; }
    else { t.textContent = text; }
    return t;
  }

  function makeSep(ch) {
    // 콜론 등 구분자: 플립하지 않는 고정 문자 ( "11" : "50" 처럼 보이게 )
    var s = document.createElement("span");
    s.className = "flap-sep";
    s.textContent = ch;
    return s;
  }

  function renderTiles(cell, animate) {
    var val = origValue(cell);
    var field = cell.dataset.field;
    cell.classList.add("flap-host");
    cell.textContent = "";

    if (field === "time") {
      // 시각: 숫자는 0–9 드럼 타일, 콜론은 고정 구분자 ( 1 1 : 5 0 )
      Array.from(val).forEach(function (ch) {
        if (ch === ":") { cell.appendChild(makeSep(ch)); return; }
        var t = makeTile(animate ? "0" : ch);
        cell.appendChild(t);
        if (animate) spin(t, digitSeq(ch, DIGIT_STEPS), (flapOrder++) * CASCADE_STEP);
      });
    } else if (field === "route") {
      // 노선: 보드의 다른 노선들을 배경색과 함께 빠르게 거쳐 감속 후 목표 노선+올바른 색에 안착.
      // 중간 스텝은 routeOnStep이 --route를 인라인으로 덮어쓰고,
      // 최종 스텝에서 removeProperty → 부모 route-NNN 클래스 색이 올바르게 복원된다.
      var tr = makeTile(val);
      cell.appendChild(tr);
      if (animate) {
        spin(tr, valueSeq(val, drums.routes, ROUTE_STEPS), (flapOrder++) * CASCADE_STEP, routeOnStep);
      }
    } else {
      // 행선: 보드의 다른 행선들을 거쳐 안착
      var td = makeTile(val);
      cell.appendChild(td);
      if (animate) spin(td, valueSeq(val, drums.dests, WORD_STEPS), (flapOrder++) * CASCADE_STEP);
    }
  }

  function renderPlain(cell) {
    cell.classList.remove("flap-host");
    origValue(cell);                         // dataset.html 캐시 보장
    cell.innerHTML = cell.dataset.html;      // 원본 복원(노선 배지 포함)
  }

  function applyMode(forceAnimate) {
    clearTimers();                           // 직전 패스의 진행 중 플립 취소(15초 폴링 경합 방지)
    var mode = currentMode();
    document.querySelectorAll("#board-table .dboard").forEach(function (b) {
      b.classList.toggle("flap", mode === "flap");
      b.classList.toggle("table", mode !== "flap");
    });

    if (mode === "flap") {
      drums = collectDrums();                // 셀 비우기 전에 실제 값 드럼 수집
      flapOrder = 0;                          // 캐스케이드 순번 0부터(위→아래)
      eachFlapCell(function (cell) {
        var key = cellKey(cell);
        var val = origValue(cell);
        var changed = lastValues[key] !== undefined && lastValues[key] !== val;
        renderTiles(cell, forceAnimate || changed);
        lastValues[key] = val;
      });
    } else {
      eachFlapCell(function (cell) {
        renderPlain(cell);
        lastValues[cellKey(cell)] = origValue(cell);
      });
    }

    document.querySelectorAll(".seg-btn").forEach(function (btn) {
      var on = btn.dataset.display === mode;
      btn.classList.toggle("active", on);
      btn.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  function wire() {
    document.querySelectorAll(".seg-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        localStorage.setItem("boardDisplay", btn.dataset.display);
        applyMode(true);   // 수동 전환 → 전체 reveal
      });
    });
    applyMode(true);       // 최초 진입(기본 table이면 표; flap이면 reveal)
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", wire);
  } else {
    wire();
  }

  document.body.addEventListener("htmx:afterSwap", function (e) {
    if (e.target && e.target.id === "board-table") {
      applyMode(false);    // 갱신 → 바뀐 셀만 플립
    }
  });
})();
