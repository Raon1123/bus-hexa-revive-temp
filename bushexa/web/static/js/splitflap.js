/* splitflap.js — 출발안내 표시 스타일 전환 (표 / Split-flap)
 *
 * - 기본: 전통 HTML 표(.dboard.table). 서버가 이미 class="dboard table"로 렌더하므로
 *   JS가 없거나 늦어도 표로 보인다.
 * - Split-flap(실험, .dboard.flap): 실제 솔라리 보드의 기계 동작을 흉내 낸다.
 *     · 모듈(타일) = 위/아래 반쪽 고정면 + 떨어지는 윗날 + 내려앉는 아랫날 4겹.
 *       한 번 넘김 = 윗날(현재 글자의 위 반쪽)이 경첩(중앙)을 축으로 앞으로 떨어지고,
 *       이어서 아랫날(다음 글자의 아래 반쪽)이 내려와 살짝 튕기며 안착한다.
 *     · 드럼은 순서가 고정된 날개 묶음이다. 목표값까지 '앞으로만' 한 장씩 넘긴다
 *       (무작위로 건너뛰지 않는다). 시각 숫자 = [공백,0–9], 노선·행선 = 보드에 나온 값을
 *       정렬한 목록(맨 앞은 빈 날). 11:49 → 11:50 이면 해당 자리만 필요한 만큼 넘어간다.
 *     · 모터는 등속이다(감속 연출 없음). 모듈마다 속도가 조금씩 달라서, 먼 값으로 가는
 *       모듈일수록 늦게 멈추고 전체가 제각각 멈춘다.
 * - 플립 시점:
 *     · 모드를 split-flap으로 전환할 때(=수동) → 모두 빈 날에서 목표까지 reveal
 *     · 15초 HTMX 갱신 후 → 값이 바뀐 셀만 직전값에서 새 값으로 넘김(슬롯 인덱스 기준)
 * - prefers-reduced-motion 이거나 탭이 숨겨져 있으면 넘기지 않고 바로 표시한다.
 * - 상태: localStorage('boardDisplay'), 기본 'table'. CDN 의존 없음.
 */
(function () {
  "use strict";

  var lastValues = Object.create(null);  // slotIndex|field → 직전 표시값(스왑에도 유지)

  // ── 기계 상수 ────────────────────────────────────────────────
  var FLIP_MS = 90;         // 날개 한 장 넘기는 시간(ms). 윗날 절반 + 아랫날 절반
  var SPEED_JITTER = 0.12;  // 모듈별 모터 속도 편차(±12%)
  var ROW_STAGGER = 55;     // 행(위→아래) 시작 시차(ms)
  var START_JITTER = 70;    // 모듈별 시작 편차(0~ms)
  var MAX_WORD_FLIPS = 14;  // 노선·행선 드럼이 길 때 넘기는 최대 장수(끝부분만)
  var BLANK = " ";
  var DIGIT_DRUM = [BLANK, "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"];
  var BLANK_ROUTE_COLOR = "#252c34";

  var timers = [];          // 진행 중 setTimeout 핸들(패스마다 취소)
  // 드럼은 페이지 수명 동안 누적(갱신 사이에 사라진 값도 날개로 남는다 — 실물 드럼처럼).
  var seen = { route: [], dest: [] };
  var routeColor = Object.create(null);
  var drums = { route: [BLANK], dest: [BLANK] };

  function currentMode() {
    return localStorage.getItem("boardDisplay") || "table";
  }

  function reducedMotion() {
    return window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
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
     - 슬롯 인덱스 기반 → 순서가 바뀌면 해당 슬롯의 노선·행선도 플립됨. */
  function slotIndex(cell) {
    var row = cell.closest(".dboard-row");
    if (!row) return 0;
    var allRows = Array.prototype.slice.call(
      row.closest("tbody").querySelectorAll(".dboard-row")
    );
    return allRows.indexOf(row);
  }

  function eachFlapCell(fn) {
    document.querySelectorAll("#board-table .dboard [data-flap]").forEach(fn);
  }

  /* 보드에 실제 존재하는 값으로 노선·행선 드럼을 만든다(하드코딩 없음).
     정렬해서 순서를 고정하고 맨 앞에 빈 날을 둔다. 노선색은 route-NNN 클래스의 --route. */
  function collectDrums() {
    ["route", "dest"].forEach(function (field) {
      document.querySelectorAll("#board-table .dboard [data-field='" + field + "']").forEach(function (c) {
        var v = origValue(c);
        if (!v) return;
        if (seen[field].indexOf(v) === -1) seen[field].push(v);
        if (field === "route" && !routeColor[v]) {
          var color = getComputedStyle(c).getPropertyValue("--route").trim();
          if (color) routeColor[v] = color;
        }
      });
    });
    var routes = seen.route.slice().sort(function (a, b) {
      return (parseInt(a, 10) || 0) - (parseInt(b, 10) || 0) || a.localeCompare(b);
    });
    var dests = seen.dest.slice().sort(function (a, b) { return a.localeCompare(b, "ko"); });
    drums = { route: [BLANK].concat(routes), dest: [BLANK].concat(dests) };
  }

  /* from → to 로 드럼을 앞으로만 돌릴 때 차례로 보이는 값들(마지막 === to).
     from === to 면 빈 배열(넘기지 않음). 드럼에 없는 값은 빈 날 위치로 본다. */
  function flipSeq(drum, from, to, cap) {
    var f = drum.indexOf(from), t = drum.indexOf(to);
    if (t === -1) return from === to ? [] : [to];
    if (f === -1) f = 0;
    var seq = [];
    for (var i = f; i !== t; ) {
      i = (i + 1) % drum.length;
      seq.push(drum[i]);
    }
    return cap && seq.length > cap ? seq.slice(seq.length - cap) : seq;
  }

  // ── 모듈(타일) DOM ──────────────────────────────────────────
  // <span.flap-char aria-hidden>
  //   <span.fl-size>  목표값(보이지 않음, 모듈 크기 결정)
  //   <span.fl-half.fl-top>  고정 윗면   (다음 값)
  //   <span.fl-half.fl-bot>  고정 아랫면 (현재 값)
  //   <span.fl-half.fl-top.fl-leaf.fl-leaf-top>  떨어지는 윗날 (현재 값)
  //   <span.fl-half.fl-bot.fl-leaf.fl-leaf-bot>  내려앉는 아랫날 (다음 값)
  function half(cls) {
    var h = document.createElement("span");
    h.className = "fl-half " + cls;
    var inner = document.createElement("span");
    inner.className = "fl-in";
    h.appendChild(inner);
    return h;
  }

  function setFace(h, v, field) {
    h.firstChild.textContent = v === BLANK ? " " : v;
    if (field === "route") {
      h.style.setProperty("--route", v === BLANK ? BLANK_ROUTE_COLOR : (routeColor[v] || BLANK_ROUTE_COLOR));
    }
  }

  function makeModule(target, shown, field) {
    var m = document.createElement("span");
    m.className = "flap-char";
    m.setAttribute("aria-hidden", "true");
    var size = document.createElement("span");
    size.className = "fl-size";
    size.textContent = target === BLANK ? " " : target;
    m.appendChild(size);
    m.faces = {
      top: half("fl-top"),
      bot: half("fl-bot"),
      leafTop: half("fl-top fl-leaf fl-leaf-top"),
      leafBot: half("fl-bot fl-leaf fl-leaf-bot")
    };
    ["top", "bot", "leafTop", "leafBot"].forEach(function (k) {
      setFace(m.faces[k], shown, field);
      m.appendChild(m.faces[k]);
    });
    return m;
  }

  /* 모듈을 seq 대로 한 장씩 등속으로 넘긴다. */
  function run(m, from, seq, field, delay) {
    if (!seq.length) return;
    var ms = Math.round(FLIP_MS * (1 + (Math.random() * 2 - 1) * SPEED_JITTER));
    m.style.setProperty("--flip", ms + "ms");
    var cur = from, i = 0;
    function flip() {
      var next = seq[i++];
      var f = m.faces;
      setFace(f.top, next, field);
      setFace(f.bot, cur, field);
      setFace(f.leafTop, cur, field);
      setFace(f.leafBot, next, field);
      m.classList.remove("is-flipping");
      void m.offsetWidth;               // reflow → 매 장 애니메이션 재생
      m.classList.add("is-flipping");
      cur = next;
      pushTimer(setTimeout(i < seq.length ? flip : settle, ms));
    }
    function settle() {
      setFace(m.faces.bot, cur, field);
      m.classList.remove("is-flipping");
    }
    pushTimer(setTimeout(flip, delay));
  }

  function srText(val) {
    var s = document.createElement("span");
    s.className = "flap-sr";
    s.textContent = val;
    return s;
  }

  function makeSep(ch) {
    // 콜론 등 구분자: 패널에 인쇄된 고정 문자 ( "11" : "50" 처럼 보이게 )
    var s = document.createElement("span");
    s.className = "flap-sep";
    s.setAttribute("aria-hidden", "true");
    s.textContent = ch;
    return s;
  }

  /* prev: 넘기기 시작할 값(null → 넘기지 않고 바로 val 표시). */
  function renderModules(cell, prev, delayBase) {
    var val = origValue(cell);
    var field = cell.dataset.field;
    cell.classList.add("flap-host");
    cell.textContent = "";
    cell.appendChild(srText(val));

    function delay() { return delayBase + Math.random() * START_JITTER; }

    if (field === "time") {
      // 시각: 숫자 자리마다 [공백,0–9] 드럼 모듈, 콜론은 고정 구분자
      var chars = Array.from(val);
      var prevChars = prev === null ? null : Array.from(prev);
      chars.forEach(function (ch, idx) {
        if (ch === ":") { cell.appendChild(makeSep(ch)); return; }
        var from = prevChars === null ? ch : (prevChars[idx] || BLANK);
        if (DIGIT_DRUM.indexOf(from) === -1) from = BLANK;
        var m = makeModule(ch, from, field);
        cell.appendChild(m);
        run(m, from, flipSeq(DIGIT_DRUM, from, ch), field, delay());
      });
    } else {
      // 노선·행선: 통째 날개 1개. 정렬된 드럼을 앞으로 넘겨 목표에 안착
      var start = prev === null ? val : prev;
      var drum = drums[field] || [BLANK, val];
      if (drum.indexOf(start) === -1) start = BLANK;
      var mw = makeModule(val, start, field);
      cell.appendChild(mw);
      run(mw, start, flipSeq(drum, start, val, MAX_WORD_FLIPS), field, delay());
    }
  }

  function renderPlain(cell) {
    cell.classList.remove("flap-host");
    origValue(cell);                         // dataset.html 캐시 보장
    cell.innerHTML = cell.dataset.html;      // 원본 복원(노선 배지 포함)
  }

  function applyMode(reveal) {
    clearTimers();                           // 직전 패스의 진행 중 플립 취소(15초 폴링 경합 방지)
    var mode = currentMode();
    document.querySelectorAll("#board-table .dboard").forEach(function (b) {
      b.classList.toggle("flap", mode === "flap");
      b.classList.toggle("table", mode !== "flap");
    });

    if (mode === "flap") {
      collectDrums();                        // 셀 비우기 전에 실제 값으로 드럼 구성
      var still = reducedMotion() || document.hidden;
      eachFlapCell(function (cell) {
        var slot = slotIndex(cell);
        var key = slot + "|" + (cell.dataset.field || "");
        var val = origValue(cell);
        var prev = null;                     // null = 넘기지 않음
        if (!still) {
          if (reveal) prev = BLANK;
          else if (lastValues[key] !== undefined && lastValues[key] !== val) prev = lastValues[key];
        }
        renderModules(cell, prev, slot * ROW_STAGGER);
        lastValues[key] = val;
      });
    } else {
      eachFlapCell(function (cell) {
        renderPlain(cell);
        lastValues[slotIndex(cell) + "|" + (cell.dataset.field || "")] = origValue(cell);
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
