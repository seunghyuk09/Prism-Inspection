// 생산 소모 (window.Consumption) — 제품 생산으로 쓰인 With Paint 프리즘 차감 + 이력
"use strict";

window.Consumption = (function () {
  const { get, post, el, esc, toast } = App;
  const n = (v) => Number(v || 0).toLocaleString();
  const n2 = (v) => Number(v || 0);
  const today = () => new Date().toISOString().slice(0, 10);

  let products = [], prisms = [], rows = [], bound = false, mode = "product";

  function productOf(id) {
    return products.find((p) => p.id === Number(id)) || null;
  }

  // 제품 기준 입력일 때 소모량 = 생산수량 × 개당소요량
  function calcQty() {
    const p = productOf((el("cs-product") || {}).value);
    const made = n2((el("cs-made") || {}).value);
    return p ? made * n2(p.prism_per_unit) : 0;
  }

  function entryForm() {
    const prodOpts = products.map((p) =>
      `<option value="${p.id}">${esc(p.product_code)} · ${esc(p.product_name || "")} (${esc(p.prism_code)} × ${n2(p.prism_per_unit)})</option>`).join("");
    const prismOpts = prisms.map((p) =>
      `<option value="${p.id}">${esc(p.item_code)} · ${esc(p.spec || "")}</option>`).join("");
    const byProduct = mode === "product";
    return `<div class="card-surface">
      <h4 style="margin-top:0">생산 소모 등록</h4>
      <div class="insp-toolbar" style="margin-bottom:10px">
        <button class="btn ${byProduct ? "primary" : ""}" id="cs-mode-product" type="button">제품 기준</button>
        <button class="btn ${byProduct ? "" : "primary"}" id="cs-mode-prism" type="button">직접 입력</button>
      </div>
      <div class="grid2-tight">
        <label class="field"><span>소모일</span><input type="date" id="cs-date" value="${today()}"/></label>
        ${byProduct
          ? (products.length
              ? `<label class="field"><span>제품</span><select id="cs-product">${prodOpts}</select></label>`
              : `<div class="field"><span>제품</span><div class="notice-readonly">등록된 제품이 없습니다. 기준정보 → 제품마스터에서 제품과 <b>개당 소요량</b>을 먼저 등록하세요.</div></div>`)
          : `<label class="field"><span>프리즘</span><select id="cs-prism">${prismOpts}</select></label>`}
      </div>
      <div class="grid2-tight">
        ${byProduct
          ? (products.length
              ? `<label class="field"><span>생산 수량</span><input type="number" id="cs-made" min="1" value="0"/></label>`
              : "")
          : `<label class="field"><span>소모 수량</span><input type="number" id="cs-qty" min="1" value="0"/></label>`}
        <label class="field"><span>비고</span><input type="text" id="cs-note"/></label>
      </div>
      <div class="form-actions">
        <span class="muted" id="cs-preview">${byProduct ? "소모량 —" : ""}</span>
        <button class="btn primary" id="cs-save" type="button">소모 등록</button>
      </div>
    </div>`;
  }

  function summaryHtml() {
    const total = rows.reduce((s, r) => s + n2(r.qty), 0);
    const itemCount = new Set(rows.map((r) => r.item_code)).size;
    const last = rows.length ? (rows[0].consumed_at || "").slice(0, 10) : "—";
    return `<div class="ih-stat-row">
      <div class="ih-stat"><span>총 소모</span><b>${n(total)}</b></div>
      <div class="ih-stat"><span>기록 수</span><b>${n(rows.length)}</b></div>
      <div class="ih-stat"><span>품목 수</span><b>${n(itemCount)}</b></div>
      <div class="ih-stat"><span>최근 소모일</span><b>${esc(last)}</b></div>
    </div>`;
  }

  function tableHtml(canEdit) {
    const body = rows.map((r) => `<tr>
      <td style="white-space:nowrap">${esc((r.consumed_at || "").slice(0, 10))}</td>
      <td>${esc(r.item_code)}</td>
      <td class="muted" style="font-size:12px">${esc(r.spec || "")}</td>
      <td class="right">${n(r.qty)}</td>
      <td><span class="pill ${r.source === "MANUAL" ? "active" : ""}">${esc(r.source_label)}</span></td>
      <td class="muted" style="font-size:12px">${esc(r.note || "")}</td>
      <td>${canEdit && r.can_delete ? `<button class="mini danger" data-act="cs-del" data-id="${r.id}">삭제</button>` : ""}</td>
    </tr>`).join("") || '<tr><td colspan="7" class="muted">소모 기록이 없습니다.</td></tr>';
    return `<div class="tbl-scroll"><table class="tbl"><thead><tr>
      <th>소모일</th><th>품목</th><th>규격</th><th class="right">수량</th>
      <th>출처</th><th>비고</th><th></th>
    </tr></thead><tbody>${body}</tbody></table></div>`;
  }

  function render() {
    const root = el("consumption-root"); if (!root) return;
    const canEdit = !window.App || App.canEdit !== false;
    root.innerHTML = `
      ${summaryHtml()}
      ${canEdit ? entryForm() : '<div class="notice-readonly">조회 전용 계정입니다.</div>'}
      <h4 style="margin-top:16px">소모 이력 <span class="muted" style="font-weight:400;font-size:12px">최근 500건</span></h4>
      ${tableHtml(canEdit)}`;
    updatePreview();
  }

  function updatePreview() {
    const box = el("cs-preview"); if (!box || mode !== "product") return;
    const p = productOf((el("cs-product") || {}).value);
    const q = calcQty();
    box.textContent = p ? `소모량 ${n(q)} (${esc(p.prism_code)})` : "소모량 —";
  }

  async function saveNew() {
    const payload = { consumed_at: el("cs-date").value, note: el("cs-note").value };
    if (mode === "product") {
      payload.product_id = Number(el("cs-product").value);
      payload.produced_qty = el("cs-made").value;
    } else {
      payload.prism_id = Number(el("cs-prism").value);
      payload.qty = el("cs-qty").value;
    }
    const r = await post("/api/consumption/save", payload);
    if (r.ok) { toast(`소모 등록 (${n(r.qty)})`, "ok"); await reload(); }
    else toast(r.error || "실패", "warn");
  }

  async function reload() {
    rows = (await get("/api/consumptions")).items || [];
    render();
  }

  async function show() {
    const root = el("consumption-root"); if (!root) return;
    root.innerHTML = '<div class="muted">불러오는 중…</div>';
    products = (await get("/api/consumable-products")).items || [];
    if (!products.length) mode = "prism";   // 등록된 제품이 없으면 직접 입력으로
    prisms = ((await get("/api/prisms")).items || []).filter((p) => p.is_active);
    rows = (await get("/api/consumptions")).items || [];
    render();
    if (bound) return;
    bound = true;
    root.addEventListener("change", (e) => {
      if (e.target.id === "cs-product") updatePreview();
    });
    root.addEventListener("input", (e) => {
      if (e.target.id === "cs-made") updatePreview();
    });
    root.addEventListener("click", async (e) => {
      if (e.target.id === "cs-mode-product") { mode = "product"; render(); return; }
      if (e.target.id === "cs-mode-prism") { mode = "prism"; render(); return; }
      if (e.target.id === "cs-save") return saveNew();
      const del = e.target.closest('[data-act="cs-del"]');
      if (del) {
        if (!confirm("이 소모 기록을 삭제할까요? 재고가 되돌아갑니다.")) return;
        const r = await post("/api/consumption/delete", { id: Number(del.dataset.id) });
        if (r.ok) { toast("삭제됨", "ok"); await reload(); } else toast(r.error || "실패", "warn");
      }
    });
  }

  return { show };
})();
