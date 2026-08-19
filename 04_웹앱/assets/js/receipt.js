// 입고 · 로트 (window.Receipt)
// 입고 등록 → 입고 1건을 여러 로트로 분리. 상단 하위메뉴(app.js)가 show() 호출.
"use strict";

window.Receipt = (function () {
  const { get, post, el, esc, toast } = App;

  let prisms = [], receipts = [], openId = null, bound = false;

  function today() { const d = new Date(); return d.toISOString().slice(0, 10); }
  function statusPill(s) {
    const m = { ACTIVE: ["active", "활성"], REMNANT: ["remnant", "잔량관리"], STOPPED: ["stopped", "중단"] };
    const [c, t] = m[s] || ["", s]; return `<span class="pill ${c}">${t}</span>`;
  }
  const n = (v) => Number(v || 0).toLocaleString();

  async function loadAll() {
    const [p, r] = await Promise.all([get("/api/prisms"), get("/api/receipts")]);
    // 입고 가능 프리즘: 도장완료 아님(미도장/유리) + 활성 공급사 (코드가 공급사를 품음)
    prisms = (p.items || []).filter((x) => x.is_active && x.paint_state !== "PAINTED" && x.supplier_status === "ACTIVE");
    receipts = r.items || [];
  }

  // ── 입고 등록 폼 ──────────────────────────────────────────
  function createForm() {
    const prismOpts = prisms.map((x) =>
      `<option value="${x.id}">${esc((x.item_code || x.prism_type) + " · " + x.spec + " (" + (x.supplier_name || "") + ")")}</option>`).join("")
      || `<option value="">입고 가능한 프리즘 없음</option>`;
    return `<form class="m-form" id="rcpt-form">
      <label class="field"><span>입고일자</span><input type="date" id="rc-receipt_date" value="${today()}"/></label>
      <label class="field"><span>프리즘 (미도장/유리 · 공급사 자동)</span><select id="rc-prism_id">${prismOpts}</select></label>
      <label class="field"><span>입고수량</span><input type="number" id="rc-received_qty" min="1" placeholder="예: 5000"/></label>
      <label class="field"><span>입고번호 (비우면 자동)</span><input type="text" id="rc-receipt_no" placeholder="RCV-…"/></label>
      <label class="field"><span>공급사 LOT (선택)</span><input type="text" id="rc-supplier_lot_no"/></label>
      <label class="field"><span>담당자 (선택)</span><input type="text" id="rc-operator"/></label>
      <label class="field"><span>비고 (선택)</span><input type="text" id="rc-note"/></label>
      <div class="form-actions"><button class="btn primary" type="submit">입고 등록</button></div>
    </form>`;
  }

  // ── 입고 목록 ─────────────────────────────────────────────
  function listTable() {
    const rows = receipts.map((r) =>
      `<tr class="clickable" data-id="${r.id}">
        <td>${esc(r.receipt_no)}</td><td>${esc(r.receipt_date)}</td>
        <td>${esc(r.supplier_name)} ${r.supplier_status !== "ACTIVE" ? statusPill(r.supplier_status) : ""}</td>
        <td>${esc(r.prism_type)}</td><td class="right">${n(r.received_qty)}</td>
        <td class="right">${r.lot_count}개 / 잔여 ${n(r.remaining_qty)}</td>
        <td><button class="mini" data-act="open" data-id="${r.id}">열기</button></td></tr>`).join("");
    return `<table class="tbl"><thead><tr><th>입고번호</th><th>일자</th><th>공급사</th><th>프리즘</th>
      <th class="right">입고수량</th><th class="right">로트/잔여</th><th></th></tr></thead>
      <tbody>${rows || '<tr><td colspan="7" class="muted">입고 없음</td></tr>'}</tbody></table>`;
  }

  // ── 상세(로트 분리) ───────────────────────────────────────
  async function detailHtml(id) {
    const d = await get("/api/receipts/detail?id=" + id);
    if (!d.ok) return `<div class="muted">${esc(d.error || "")}</div>`;
    const rec = d.receipt;
    const lotRows = d.lots.map((l) =>
      `<tr><td>${esc(l.lot_no)}</td><td class="right">${n(l.lot_qty)}</td><td>${esc(l.split_reason || "")}</td>
       <td>${esc(l.status)}</td><td><button class="mini danger" data-act="dellot" data-id="${l.id}">삭제</button></td></tr>`).join("");
    return `<h3>${esc(rec.receipt_no)} · ${esc(rec.supplier_name)} · ${esc(rec.prism_type)}
        &nbsp;(입고 ${n(rec.received_qty)} / 분리 ${n(d.lot_qty_sum)} / <b>잔여 ${n(d.remaining_qty)}</b>)</h3>
      <div class="m-grid">
        <div><form class="m-form" id="lot-form"><input type="hidden" id="lot-receipt_id" value="${id}"/>
          <label class="field"><span>로트수량 (잔여 ${n(d.remaining_qty)} 까지)</span><input type="number" id="lot-lot_qty" min="1" max="${d.remaining_qty}"/></label>
          <label class="field"><span>로트번호 (비우면 자동)</span><input type="text" id="lot-lot_no"/></label>
          <label class="field"><span>분리사유 (선택)</span><input type="text" id="lot-split_reason" placeholder="예: 팔레트/생산일자"/></label>
          <div class="form-actions"><button class="btn primary" type="submit">로트 추가</button></div></form></div>
        <div><table class="tbl"><thead><tr><th>로트번호</th><th class="right">수량</th><th>분리사유</th><th>상태</th><th></th></tr></thead>
          <tbody>${lotRows || '<tr><td colspan="5" class="muted">로트 없음 — 왼쪽에서 분리하세요</td></tr>'}</tbody></table></div>
      </div>`;
  }

  // ── 렌더 ──────────────────────────────────────────────────
  async function render() {
    await loadAll();
    el("receipt-root").innerHTML =
      `<div class="m-grid"><div class="card-surface"><h4>새 입고 등록</h4>${createForm()}</div>
       <div class="card-surface"><h4>입고 목록</h4>${listTable()}</div></div>
       <div class="card-surface" id="rcpt-detail" style="margin-top:16px;${openId ? "" : "display:none"}"></div>`;
    if (openId) el("rcpt-detail").innerHTML = await detailHtml(openId);
    bindOnce();
  }

  // ── 동작(위임은 1회만 부착) ──────────────────────────────
  async function onCreate() {
    const body = {
      receipt_date: el("rc-receipt_date").value,
      prism_id: Number(el("rc-prism_id").value || 0), received_qty: el("rc-received_qty").value,
      receipt_no: el("rc-receipt_no").value, supplier_lot_no: el("rc-supplier_lot_no").value,
      operator: el("rc-operator").value, note: el("rc-note").value,
    };  // 공급사는 서버가 프리즘에서 자동 결정
    const r = await post("/api/receipts/create", body);
    if (r.ok) { toast(`입고 등록: ${r.receipt_no}`, "ok"); openId = r.receipt_id; await render();
      el("rcpt-detail").scrollIntoView({ behavior: "smooth", block: "start" }); }
    else toast(r.error || "실패", "warn");
  }
  async function onAddLot() {
    const body = { receipt_id: Number(el("lot-receipt_id").value), lot_qty: el("lot-lot_qty").value,
      lot_no: el("lot-lot_no").value, split_reason: el("lot-split_reason").value };
    const r = await post("/api/receipts/add-lot", body);
    if (r.ok) { toast(`로트 추가: ${r.lot_no}`, "ok"); await render(); } else toast(r.error || "실패", "warn");
  }
  function bindOnce() {
    if (bound) return; bound = true;
    const root = el("receipt-root");
    root.addEventListener("submit", (e) => {
      e.preventDefault();
      if (e.target.id === "rcpt-form") onCreate();
      else if (e.target.id === "lot-form") onAddLot();
    });
    root.addEventListener("click", async (e) => {
      const del = e.target.closest('[data-act="dellot"]');
      if (del) { const r = await post("/api/receipts/delete-lot", { id: Number(del.dataset.id) });
        if (r.ok) { toast("로트 삭제", "ok"); await render(); } else toast(r.error || "실패", "warn"); return; }
      const opener = e.target.closest('[data-act="open"]') || e.target.closest("tr.clickable");
      if (opener) { openId = Number(opener.dataset.id); await render();
        el("rcpt-detail").scrollIntoView({ behavior: "smooth", block: "start" }); }
    });
  }

  async function show() { await render(); }
  return { show };
})();
