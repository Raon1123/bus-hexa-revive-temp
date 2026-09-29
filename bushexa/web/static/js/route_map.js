/* /info 노선도 상호작용 — A/B 보기 전환, 노선 강조, 정류장 정보 패널, A/B 카운터.
 *
 * 서버가 A(지도)·B(목록) 중 하나를 보여 준 완성된 HTML 을 준다. 이 스크립트는 보조다:
 *   - "지도로/목록으로 보기"를 누르면 새로고침 없이 바꾸고, 전환 1회를 세고, 쿠키에 기억한다.
 *     (JS 가 없으면 같은 링크 ?view= 로 서버가 바꾸고 센다.)
 *   - 노선 칩·종점 pill·노선 선을 누르면 그 노선만 진하게. 다시 누르거나 "전체"로 해제.
 *   - 정류장을 누르면 패널에 서는 노선·환승 철도·설명·실시간 도착 링크를 보여 준다.
 *   - 이벤트는 /info/event 로 보낸다. 실패해도 무시.
 */
(function () {
    "use strict";

    function beacon(ev) {
        try {
            var body = new URLSearchParams({ e: ev });
            if (navigator.sendBeacon && navigator.sendBeacon("/info/event", body)) return;
            fetch("/info/event", { method: "POST", body: body, keepalive: true }).catch(function () {});
        } catch (e) { /* 카운터 실패는 무시 */ }
    }

    // 노선도 컨테이너(.route-map) 하나마다 독립적으로 붙는다.
    function init(root) {
        var svg = root.querySelector("svg.route-svg");
        var panel = root.querySelector(".route-map-panel");
        if (!svg || !panel) return;
        var chips = Array.prototype.slice.call(root.querySelectorAll(".route-chip"));
        var current = "";

        function linesOf(el) {
            return (el.getAttribute("data-lines") || "").split(" ").filter(Boolean);
        }

        function setLine(line) {
            current = line;
            var all = svg.querySelectorAll(".route-line, .route-pill-btn");
            Array.prototype.forEach.call(all, function (el) {
                el.classList.toggle("is-dim", !!line && el.getAttribute("data-line") !== line);
            });
            Array.prototype.forEach.call(svg.querySelectorAll(".route-station"), function (el) {
                var on = !line || linesOf(el).indexOf(line) >= 0;
                el.classList.toggle("is-dim", !on);
                var label = svg.querySelector('.route-label[data-stop="' + cssEscape(el.getAttribute("data-stop")) + '"]');
                if (label) label.classList.toggle("is-dim", !on);
            });
            chips.forEach(function (c) {
                c.setAttribute("aria-pressed", String((c.getAttribute("data-line") || "") === line));
            });
            svg.classList.toggle("has-focus", !!line);
        }

        function toggleLine(line) {
            setLine(current === line ? "" : line);
            beacon("map_line");
        }

        function cssEscape(s) {
            return window.CSS && CSS.escape ? CSS.escape(s) : String(s).replace(/"/g, '\\"');
        }

        function el(tag, cls, text) {
            var e = document.createElement(tag);
            if (cls) e.className = cls;
            if (text != null) e.textContent = text;
            return e;
        }

        function showStop(g) {
            Array.prototype.forEach.call(svg.querySelectorAll(".route-station.is-selected"), function (x) {
                x.classList.remove("is-selected");
            });
            g.classList.add("is-selected");
            panel.textContent = "";
            panel.appendChild(el("h4", "route-map-panel-title", g.getAttribute("data-label")));

            var row = el("div", "route-map-panel-lines");
            linesOf(g).forEach(function (line) {
                var b = el("button", "route-chip route-chip-sm", line);
                b.type = "button";
                b.setAttribute("data-line", line);
                b.setAttribute("aria-label", line + "번 노선만 보기");
                var chip = root.querySelector('.route-chip[data-line="' + line + '"]');
                if (chip) b.style.setProperty("--route", chip.style.getPropertyValue("--route"));
                b.addEventListener("click", function () { toggleLine(line); });
                row.appendChild(b);
            });
            panel.appendChild(row);

            var rail = g.getAttribute("data-rail");
            if (rail) panel.appendChild(el("p", "route-map-panel-rail", "철도 환승: " + rail));
            var note = g.getAttribute("data-note");
            if (note) panel.appendChild(el("p", "route-map-panel-note", note));
            var href = g.getAttribute("data-href");
            if (href) {
                var a = el("a", "route-map-panel-link", "실시간 도착 보기 · " + g.getAttribute("data-href-label"));
                a.href = href;
                a.addEventListener("click", function () { beacon("map_link"); });
                panel.appendChild(a);
            }
            beacon("map_stop");
        }

        svg.addEventListener("click", function (ev) {
            var t = ev.target;
            var pill = t.closest(".route-pill-btn");
            if (pill) { toggleLine(pill.getAttribute("data-line")); return; }
            var st = t.closest(".route-station");
            if (st) { showStop(st); return; }
            if (t.classList.contains("route-line")) { toggleLine(t.getAttribute("data-line")); }
        });
        svg.addEventListener("keydown", function (ev) {
            if (ev.key !== "Enter" && ev.key !== " ") return;
            var t = ev.target.closest(".route-pill-btn, .route-station");
            if (!t) return;
            ev.preventDefault();
            t.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        });
        chips.forEach(function (c) {
            c.addEventListener("click", function () {
                var line = c.getAttribute("data-line") || "";
                if (!line) { setLine(""); beacon("map_line"); } else { toggleLine(line); }
            });
        });
        document.addEventListener("keydown", function (ev) {
            if (ev.key === "Escape" && current) setLine("");
        });
    }

    Array.prototype.forEach.call(document.querySelectorAll(".route-map"), init);

    // A/B 보기 전환
    var toggles = document.querySelectorAll(".route-view-toggle a[data-view]");
    Array.prototype.forEach.call(toggles, function (a) {
        a.addEventListener("click", function (ev) {
            ev.preventDefault();
            var to = a.getAttribute("data-view");
            if (a.getAttribute("aria-current") === "true") return;
            Array.prototype.forEach.call(document.querySelectorAll(".route-view"), function (v) {
                v.hidden = v.getAttribute("data-view") !== to;
            });
            Array.prototype.forEach.call(toggles, function (t) {
                if (t === a) t.setAttribute("aria-current", "true"); else t.removeAttribute("aria-current");
            });
            document.cookie = "route_map_view=" + to + "; max-age=7776000; path=/; SameSite=Lax";
            beacon("switch_to_" + to);
        });
    });

    // B: 노선별 목록 링크 이동
    Array.prototype.forEach.call(document.querySelectorAll('a[data-ab="list_link"]'), function (a) {
        a.addEventListener("click", function () { beacon("list_link"); });
    });
})();
