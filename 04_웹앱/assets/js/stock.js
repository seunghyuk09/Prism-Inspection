// 소비 · 잔량 — 잔량 현황 + 기초재고/보정 (window.Stock)
"use strict";

window.Stock = (function () {
  const { get, post, el, esc, toast } = App;
  let items = [], bound = false;
  const n = (v) => Number(v || 0).toLocaleString();
  const today = () => new Date().toISOString().slice(0, 10);
  const paintLabel = (v) => ({ RAW: "미도장", PAINTED: "도장완료", NONE: "유리" }[v] || v || "");
  function supPill(s) {
    const m = { ACTIVE: ["active", "활성"], REMNANT: ["remnant", "잔량관리"], STOPPED: ["stopped", "중단"] };
    const [c, t] = m[s] || ["", s || ""]; return `<span class="pill ${c}">${t}</span>`;
  }

  function table() {
    const rows = items.map((p) => {
      const low = p.on_hand < 0;
      const unusable = Number(p.unusable || 0);
      const sentCell = p.paint_state === "RAW" ? n(p.sent_paint) : "—";
      return `<tr>
        <td>${esc(p.item_code || "—")}</td>
        <td>${esc(p.prism_type)} ${esc(p.model || "")}</td>
        <td>${paintLabel(p.paint_state)}</td>
        <td>${esc(p.supplier_name || "—")} ${p.supplier_status && p.supplier_status !== "ACTIVE" ? supPill(p.supplier_status) : ""}</td>
        <td class="right">${n(p.produced)}</td>
        <td class="right">${sentCell}</td>
        <td class="right">${n(p.consumed)}</td>
        <td class="right">${n(p.opening_adj)}</td>
        <td class="right" style="font-weight:800;${low ? "color:var(--danger-text)" : ""}">${n(p.on_hand)}</td>
        <td class="right${unusable ? " bad-t" : ""}">${unusable ? n(unusable) : "—"}</td>
        <td class="right" style="font-weight:700;color:var(--success-text)">${n(p.available == null ? p.on_hand : p.available)}</td>
      </tr>`;
    }).join("");
    return `<table class="tbl"><thead><tr>
      <th>품목코드</th><th>종류/모델</th><th>도장</th><th>공급사</th>
      <th class="right">생산·입고</th><th class="right">페인트발송</th><th class="right">소비</th><th class="right">기초/보정</th>
      <th class="right">현재고</th><th class="right">사용불가</th><th class="right">가용재고</th>
      </tr></thead><tbody>${rows || '<tr><td colspan="11" class="muted">데이터 없음</td></tr>'}</tbody></table>
      <p class="muted" style="margin-top:8px">현재고 = 기초/보정 + 생산·입고 − (페인트발송) − 소비.
      <b>사용불가</b>=불량·보류(현재고에 포함), <b>가용재고</b>=현재고 − 사용불가.
      유리=입고검사 양품, 미도장=입고양품−페인트발송, 도장완료=페인트후 양품.</p>`;
  }

  function adjustForm() {
    const opts = items.map((p) => `<option value="${p.id}">${esc((p.item_code || p.prism_type) + " · " + p.spec + " (" + paintLabel(p.paint_state) + ")")}</option>`).join("");
    return `<form class="m-form" id="adj-form">
      <h4 style="margin:0">기초재고 / 보정 입력</h4>
      <label class="field"><span>프리즘</span><select id="adj-prism">${opts}</select></label>
      <label class="field"><span>수량 (+기초재고 / −감모)</span><input type="number" id="adj-qty" placeholder="예: 1200 또는 -50"/></label>
      <label class="field"><span>구분</span><select id="adj-reason"><option value="OPENING">기초재고(오프렌 잔량 등)</option><option value="MANUAL">수기 보정</option></select></label>
      <label class="field"><span>일자</span><input type="date" id="adj-date" value="${today()}"/></label>
      <label class="field"><span>비고</span><input type="text" id="adj-note"/></label>
      <div class="form-actions"><button class="btn primary" type="submit">반영</button></div>
    </form>`;
  }

  async function refresh() {
    items = (await get("/api/stock")).items || [];
    el("stock-root").innerHTML =
      `<div class="m-grid"><div class="card-surface">${adjustForm()}</div>` +
      `<div class="card-surface"><h4>프리즘 잔량 현황</h4>${table()}</div></div>`;
    bindOnce();
  }

  function bindOnce() {
    if (bound) return; bound = true;
    el("stock-root").addEventListener("submit", async (e) => {
      e.preventDefault();
      if (e.target.id !== "adj-form") return;
      const r = await post("/api/stock/adjust", {
        prism_id: Number(el("adj-prism").value || 0), qty: el("adj-qty").value,
        reason: el("adj-reason").value, adjusted_at: el("adj-date").value, note: el("adj-note").value,
      });
      if (r.ok) { toast("재고 반영됨", "ok"); await refresh(); } else toast(r.error || "실패", "warn");
    });
  }

  async function show() { await refresh(); }
  return { show };
})();
