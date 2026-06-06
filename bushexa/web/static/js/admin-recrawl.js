/* 시간표 재크롤 (TP-010) — POST로 job 시작 후 SSE로 진행상황 표시.
 *
 * 서버 프로토콜(routes/admin.py):
 *   POST /admin/timetable/recrawl            → {"job_id": ...} | 409 {"error": ...}
 *   GET  /admin/timetable/recrawl/<id>/stream → SSE: progress/done/error 이벤트
 * 부분 실패(TimetableCrawlError — 일부 노선만 갱신)는 error 이벤트 메시지로 전달된다.
 */
(function () {
    "use strict";

    var form = document.getElementById("recrawl-form");
    var progress = document.getElementById("recrawl-progress");
    if (!form || !progress) return;

    var button = form.querySelector("button[type=submit]");

    function line(text, cls) {
        var p = document.createElement("p");
        p.className = cls || "";
        p.textContent = text;
        progress.appendChild(p);
        return p;
    }

    form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        progress.textContent = "";
        button.disabled = true;

        fetch(form.action, {
            method: "POST",
            body: new FormData(form),  // csrf_token + vacation 포함
        }).then(function (resp) {
            return resp.json().then(function (data) {
                if (!resp.ok) {  // 409: 이미 진행 중
                    throw new Error(data.error || ("HTTP " + resp.status));
                }
                return data.job_id;
            });
        }).then(function (jobId) {
            var statusLine = line("재크롤 진행 중…", "recrawl-status");
            var src = new EventSource(
                form.action + "/" + encodeURIComponent(jobId) + "/stream");
            var finished = false;  // done/error 후 네이티브 error 이벤트가 상태를 덮지 않게

            src.addEventListener("progress", function (e) {
                var d = JSON.parse(e.data);
                statusLine.textContent =
                    "진행 중: 노선 " + d.route + " / 요일 " + d.day + " / 페이지 " + d.page;
            });
            src.addEventListener("done", function () {
                finished = true;
                src.close();
                statusLine.textContent = "재크롤 완료 — 전 노선 시간표가 갱신되었습니다.";
                statusLine.className = "recrawl-done";
                button.disabled = false;
            });
            src.addEventListener("error", function (e) {
                if (finished) return;
                if (typeof e.data === "undefined") {
                    // 네이티브 연결 오류 — EventSource가 자동 재연결하므로 종료로 취급하지 않음
                    return;
                }
                finished = true;
                src.close();
                // 부분 실패 메시지(성공/실패 노선 목록)는 data에 담겨 온다
                var msg = "재크롤 실패";
                try { msg = JSON.parse(e.data).message || msg; } catch (_ignored) { /* malformed data */ }
                statusLine.textContent = msg + " — 실패 노선은 기존 시간표가 보존됩니다.";
                statusLine.className = "recrawl-error";
                button.disabled = false;
            });
        }).catch(function (err) {
            line(String(err.message || err), "recrawl-error");
            button.disabled = false;
        });
    });
})();
