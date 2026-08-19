// 집계 (window.Report) — 로트별/공급사별/항목별 집계 + 엑셀 다운로드(전체/건별)
"use strict";

window.Report = (function () {
  const { get, el, esc } = App;
  let data = null, bound = false;
  const n = (v) => Number(v || 0).toLocaleString();
  const pct = (v) => (v || v === 0 ? v + "%" : "—");

  function dl(url) {
    const a = document.createElement("a");
    a.href = url; document.body.appendChild(a); a.click(); a.remove();
  }

  function lotTable() {
    const rows = (data.by_lot || []).map((b) =>
      `<tr><td>${esc(b.lot_label || b.lot_no)}</td><td>${esc(b.receipt_date || "")}</td>
        <td>${esc(b.item_code || (b.prism_type + " " + (b.model || "")))}</td><td>${esc(b.supplier_name)}</td>
        <td class="right">${n(b.lot_qty)}</td><td class="right">${n(b.inc_good)}</td>
        <td class="right">${n(b.inc_defect)} (${pct(b.inc_rate)})</td>
        <td class="right">${b.final_good == null ? "—" : n(b.final_good)}</td>
        <td class="right">${pct(b["yield"])}</td>
        <td><button class="mini" data-act="dl" data-lot="${b.lot_id}" data-label="${esc(b.lot_label || b.lot_no)}">엑셀</button></td></tr>`).join("");
    return `<table class="tbl"><thead><tr><th>로트번호</th><th>입고일</th><th>프리즘</th><th>공급사</th>
      <th class="right">로트수량</th><th class="right">입고양품</th><th class="right">입고불량(률)</th>
      <th class="right">최종양품</th><th class="right">수율</th><th>건별</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="10" class="muted">검사된 로트 없음</td></tr>'}</tbody></table>`;
  }

  function supplierTable() {
    const rows = (data.by_supplier || []).map((b) =>
      `<tr><td>${esc(b.supplier_name)}</td><td class="right">${n(b.received)}</td>
        <td class="right">${n(b.good)}</td><td class="right">${n(b.defect)}</td><td class="right">${pct(b.defect_rate)}</td></tr>`).join("");
    return `<table class="tbl"><thead><tr><th>공급사</th><th class="right">입고수량</th><th class="right">양품</th><th class="right">불량</th><th class="right">불량률</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="5" class="muted">없음</td></tr>'}</tbody></table>`;
  }

  function itemTable() {
    const rows = (data.by_item || []).map((b) =>
      `<tr><td>${esc(b.name)}</td><td class="right">${n(b.inc_defect)} (${pct(b.inc_rate)})</td>
        <td class="right">${n(b.post_defect)} (${pct(b.post_rate)})</td></tr>`).join("");
    return `<table class="tbl"><thead><tr><th>검사항목</th><th class="right">입고검사 불량(률)</th><th class="right">페인트후 불량(률)</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="3" class="muted">없음</td></tr>'}</tbody></table>`;
  }

  async function show() {
    data = await get("/api/report/summary");
    el("report-root").innerHTML = `
      <div style="margin-bottom:12px"><button class="btn primary" id="rep-excel">전체 집계 엑셀 다운로드</button>
        <span class="muted" style="margin-left:8px">검사 로트 ${data.totals ? data.totals.lot_count : 0}건</span></div>
      <div class="card-surface"><h4>로트별 집계 (건별 엑셀 다운로드)</h4>${lotTable()}</div>
      <div class="grid2" style="margin-top:16px">
        <div class="card-surface"><h4>공급사별</h4>${supplierTable()}</div>
        <div class="card-surface"><h4>검사항목별 불량률 (단계 분리)</h4>${itemTable()}</div>
      </div>`;
    bindOnce();
  }

  function bindOnce() {
    if (bound) return; bound = true;
    el("report-root").addEventListener("click", (e) => {
      if (e.target.id === "rep-excel") return dl("/api/report/excel");
      const b = e.target.closest('[data-act="dl"]');
      if (b) dl("/api/report/lot-excel?lot_id=" + b.dataset.lot + "&label=" + encodeURIComponent(b.dataset.label || ""));
    });
  }

  return { show };
})();
