// 이력 로그 (window.Log) — activity_log 최근순 조회 + 분류 필터
"use strict";

window.Log = (function () {
  const { get, el, esc } = App;
  let logs = [], cat = "", bound = false;

  function catOptions() {
    const cats = [...new Set(logs.map((l) => l.category).filter(Boolean))].sort();
    return `<option value="">전체 분류</option>` +
      cats.map((c) => `<option value="${esc(c)}" ${c === cat ? "selected" : ""}>${esc(c)}</option>`).join("");
  }

  function table() {
    const rows = logs.filter((l) => !cat || l.category === cat).map((l) => {
      const d = l.detail ? String(l.detail) : "";
      return `<tr>
        <td style="white-space:nowrap">${esc((l.ts || "").slice(0, 19))}</td>
        <td>${esc(l.category || "")}</td>
        <td>${esc(l.action || "")}</td>
        <td>${esc(l.target || "")}</td>
        <td>${esc(l.operator || "")}</td>
        <td class="muted" style="font-size:12px" title="${esc(d)}">${esc(d.slice(0, 80))}</td>
      </tr>`;
    }).join("");
    return `<div class="tbl-scroll"><table class="tbl"><thead><tr>
      <th>일시</th><th>분류</th><th>동작</th><th>대상</th><th>작업자</th><th>상세</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="6" class="muted">기록 없음</td></tr>'}</tbody></table></div>`;
  }

  function render() {
    const shown = logs.filter((l) => !cat || l.category === cat).length;
    el("log-root").innerHTML = `
      <div class="report-toolbar">
        <label class="rep-filter">분류 <select id="log-cat">${catOptions()}</select></label>
        <button class="btn" id="log-refresh" type="button">↻ 새로고침</button>
        <span class="muted">${shown}건 표시 · 최근 ${logs.length}건 (최대 500)</span>
      </div>
      ${table()}`;
  }

  async function show() {
    el("log-root").innerHTML = '<div class="muted">불러오는 중…</div>';
    logs = (await get("/api/logs")).items || [];
    render();
    if (!bound) {
      bound = true;
      const root = el("log-root");
      root.addEventListener("change", (e) => { if (e.target.id === "log-cat") { cat = e.target.value; render(); } });
      root.addEventListener("click", (e) => { if (e.target.id === "log-refresh") show(); });
    }
  }

  return { show };
})();
