// 생산 소모 (window.Consumption) — ERP 상 소모·이동 수량을 그대로 따라 With Paint 프리즘을 차감 + 이력
// 제품 마스터는 쓰지 않는다. 품목 + 수량 + 비고(ERP 전표/제품명 등)만 기록한다.
"use strict";

window.Consumption = (function () {
  const { get, post, el, esc, toast } = App;
  const n = (v) => Number(v || 0).toLocaleString();
  const n2 = (v) => Number(v || 0);
  const today = () => new Date().toISOString().slice(0, 10);

  let prisms = [], rows = [], bound = false;

  function entryForm() {
    // With Paint(도장완료) 를 먼저, 나머지는 뒤에
    const sorted = prisms.slice().sort((a, b) =>
      (a.paint_state === "PAINTED" ? 0 : 1) - (b.paint_state === "PAINTED" ? 0 : 1));
    const opts = sorted.map((p) =>
      `<option value="${p.id}">${esc(p.item_code)} · ${esc(p.spec || "")}</option>`).join("");
    return `<div class="card-surface">
      <h4 style="margin-top:0">소모 등록</h4>
      <p class="sub" style="margin-top:0">ERP 에서 소모·이동된 수량을 그대로 넣으세요. 어떤 제품·전표인지는 비고에 적으면 됩니다.</p>
      <div class="grid2-tight">
        <label class="field"><span>소모일</span><input type="date" id="cs-date" value="${today()}"/></label>
        <label class="field"><span>프리즘</span><select id="cs-prism">${opts}</select></label>
      </div>
      <div class="grid2-tight">
        <label class="field"><span>소모 수량</span><input type="number" id="cs-qty" min="1" value="0"/></label>
        <label class="field"><span>비고 (제품명 · ERP 전표 등)</span><input type="text" id="cs-note" placeholder="예: Hamster Pro 7,000개 / 전표 2026-10-15"/></label>
      </div>
      <div class="form-actions">
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
      <td>${esc(r.note || "")}</td>
      <td>${canEdit && r.can_delete ? `<button class="mini danger" data-act="cs-del" data-id="${r.id}">삭제</button>` : ""}</td>
    </tr>`).join("") || '<tr><td colspan="6" class="muted">소모 기록이 없습니다.</td></tr>';
    return `<div class="tbl-scroll"><table class="tbl"><thead><tr>
      <th>소모일</th><th>품목</th><th>규격</th><th class="right">수량</th><th>비고</th><th></th>
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
  }

  async function saveNew() {
    const r = await post("/api/consumption/save", {
      consumed_at: el("cs-date").value,
      prism_id: Number(el("cs-prism").value),
      qty: el("cs-qty").value,
      note: el("cs-note").value,
    });
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
    prisms = ((await get("/api/prisms")).items || []).filter((p) => p.is_active);
    rows = (await get("/api/consumptions")).items || [];
    render();
    if (bound) return;
    bound = true;
    root.addEventListener("click", async (e) => {
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
