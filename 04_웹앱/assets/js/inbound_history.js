// 입고이력 (window.InboundHistory) — 품목별 입고날짜를 '열'로 나열, 날짜 클릭 시 해당 입고 상세.
"use strict";

window.InboundHistory = (function () {
  const { get, el, esc } = App;
  const n = (v) => Number(v || 0).toLocaleString();
  const STATE_KO = { RAW: "미도장", PAINTED: "도장완료", NONE: "" };

  let data = null;
  const sel = {};      // { prism_id: receipt_id } — 품목별 선택된 입고
  let bound = false;

  // 선택된 입고건 상세(수량/양불/불량유형)
  function detailHtml(d) {
    if (!d) return '<div class="ih-detail muted">날짜를 선택하세요.</div>';
    const rateTxt = d.defect_rate == null ? "미확정" : d.defect_rate + "%";
    // 양품률 = 양품 / 입고수량 (불량률과 같은 분모 = received_qty). 미검사면 —
    const goodRate = (d.good == null || !d.qty) ? "—" : (d.good / d.qty * 100).toFixed(2) + "%";
    const pill = d.status === "검사완료"
      ? '<span class="pill active">검사완료</span>'
      : '<span class="pill remnant">검사중</span>';

    let rows;
    if (d.defects && d.defects.length) {
      const maxq = Math.max.apply(null, d.defects.map((x) => x.qty)) || 1;
      // 불량률(%) = 해당 유형 / 입고수량 — 유형별 합이 전체 불량률과 일치
      rows = d.defects.map((x) => {
        const prate = d.qty ? (x.qty / d.qty * 100).toFixed(2) : "0.00";
        return `<tr><td>${esc(x.name)}</td><td class="right">${n(x.qty)}</td>
          <td class="right">${prate}%</td>
          <td class="ih-barcell"><span class="ih-bar" style="width:${Math.round(x.qty / maxq * 100)}%"></span></td></tr>`;
      }).join("");
    } else {
      rows = `<tr><td colspan="4" class="muted">${d.status === "검사중" ? "검사 진행 중 — 양·불 미확정" : "불량 없음"}</td></tr>`;
    }

    return `<div class="ih-detail">
      <div class="ih-detail-head"><b>${esc(d.date)}</b> · <code>${esc(d.receipt_no)}</code> ${pill}</div>
      <div class="ih-stat-row">
        <div class="ih-stat"><span>입고수량</span><b>${n(d.qty)}</b></div>
        <div class="ih-stat"><span>양품</span><b class="yes">${d.good == null ? "—" : n(d.good)}</b></div>
        <div class="ih-stat"><span>양품률</span><b class="yes">${goodRate}</b></div>
        <div class="ih-stat"><span>불량</span><b class="ih-bad">${d.defect == null ? "—" : n(d.defect)}</b></div>
        <div class="ih-stat"><span>불량률</span><b>${rateTxt}</b></div>
      </div>
      <table class="tbl ih-def"><thead><tr><th>불량유형</th><th class="right">수량</th><th class="right">불량률</th><th>비중</th></tr></thead>
        <tbody>${rows}</tbody></table>
    </div>`;
  }

  // 입고날짜 '열'(칩) 하나
  function colHtml(item, d) {
    const active = sel[item.prism_id] === d.receipt_id ? "active" : "";
    const tone = d.status === "검사중" ? "pending"
      : (d.defect_rate != null && d.defect_rate >= 20 ? "hi" : "");
    const rate = d.defect_rate == null
      ? '<span class="ih-col-rate muted">검사중</span>'
      : `<span class="ih-col-rate">불량 ${d.defect_rate}%</span>`;
    return `<button type="button" class="ih-col ${active} ${tone}" data-prism="${item.prism_id}" data-rid="${d.receipt_id}">
      <span class="ih-col-date">${esc(d.date)}</span>
      <span class="ih-col-qty">${n(d.qty)}</span>
      ${rate}
    </button>`;
  }

  function itemCard(item) {
    const dels = item.deliveries || [];
    const cols = dels.map((d) => colHtml(item, d)).join("") || '<span class="muted">입고 없음</span>';
    const selD = dels.find((d) => d.receipt_id === sel[item.prism_id]) || null;
    const stateKo = STATE_KO[item.paint_state] || "";
    const rate = item.defect_rate != null ? ` (${item.defect_rate}%)` : "";

    return `<div class="card-surface ih-item">
      <div class="ih-item-head">
        <div class="ih-item-title">
          <span class="ih-code">${esc(item.item_code || "")}</span>
          <span class="muted">${esc(item.spec || "")}${stateKo ? " · " + stateKo : ""} · ${esc(item.supplier_name || "")}</span>
        </div>
        <div class="ih-summary">
          현재고 <b>${n(item.on_hand)}</b>
          <span class="muted">· 누적입고 ${n(item.total_received)} · 양품 ${n(item.total_good)} · 불량 ${n(item.total_defect)}${rate}</span>
        </div>
      </div>
      ${item.opening_note ? `<div class="ih-note">${esc(item.opening_note)}</div>` : ""}
      <div class="ih-cols">${cols}</div>
      ${detailHtml(selD)}
    </div>`;
  }

  function render() {
    const items = (data && data.items) || [];
    el("inbound-root").innerHTML = items.length
      ? items.map(itemCard).join("")
      : '<div class="muted">입고 이력이 있는 품목이 없습니다.</div>';
  }

  function bindOnce() {
    if (bound) return; bound = true;
    el("inbound-root").addEventListener("click", (e) => {
      const b = e.target.closest(".ih-col"); if (!b) return;
      sel[Number(b.dataset.prism)] = Number(b.dataset.rid);
      render();
    });
  }

  async function show() {
    el("inbound-root").innerHTML = '<div class="muted">불러오는 중…</div>';
    try {
      data = await get("/api/inbound-history");
    } catch (e) {
      el("inbound-root").innerHTML = '<div class="muted">불러오기 실패</div>'; return;
    }
    // 기본 선택: 각 품목의 최근(마지막) 입고
    (data.items || []).forEach((it) => {
      if (it.deliveries.length && sel[it.prism_id] === undefined) {
        sel[it.prism_id] = it.deliveries[it.deliveries.length - 1].receipt_id;
      }
    });
    render();
    bindOnce();
  }

  return { show };
})();
