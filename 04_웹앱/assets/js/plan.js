// 소비 · 잔량 — 구매계획서 임포트 (window.Plan)
// 엑셀 업로드 → 미리보기(제품 매핑/소비량) → 확정(프리즘 차감). base64 로 서버에 전송.
"use strict";

window.Plan = (function () {
  const { get, post, el, esc, toast } = App;
  let fileB64 = null, filename = "", plans = [], bound = false;
  let ledgerB64 = null;
  const n = (v) => Number(v || 0).toLocaleString();

  function readFile(file) {
    return new Promise((res, rej) => {
      const r = new FileReader();
      r.onload = () => res(r.result);
      r.onerror = rej;
      r.readAsDataURL(file);   // data:...;base64,XXXX
    });
  }

  // ── 미리보기 렌더 ─────────────────────────────────────────
  function statusTag(s) {
    if (s === "OK") return '<span class="pill active">반영</span>';
    if (s === "UNMATCHED") return '<span class="pill stopped">미등록 제품</span>';
    if (s === "NO_PRISM") return '<span class="pill remnant">프리즘 미지정</span>';
    return esc(s);
  }

  async function doPreview(sheet) {
    if (!fileB64) return;
    const r = await post("/api/plan/preview", { content: fileB64, sheet });
    const box = el("plan-preview");
    if (!r.ok) { box.innerHTML = `<div class="muted">${esc(r.error || "")}</div>`; return; }
    const sheetOpts = r.sheets.map((s) => `<option value="${esc(s)}" ${s === r.sheet ? "selected" : ""}>${esc(s)}</option>`).join("");
    const s = r.summary;
    const lineRows = r.lines.map((l) =>
      `<tr><td>${esc(l.product_code)}</td><td class="right">${n(l.qty)}</td><td>${statusTag(l.status)}</td>
        <td>${esc(l.prism_code || "—")}</td><td class="right">${l.consumed ? n(l.consumed) : "—"}</td></tr>`).join("");
    box.innerHTML = `
      <div class="m-grid" style="grid-template-columns:1fr 1fr">
        <label class="field"><span>시트(월)</span><select id="plan-sheet">${sheetOpts}</select></label>
        <label class="field"><span>계획 월(라벨)</span><input type="text" id="plan-month" value="${esc(r.sheet)}"/></label>
      </div>
      <div class="insp-head">대상 ${s.total_lines}건 · <b style="color:var(--success-text)">반영 ${s.matched}</b>
        · 미등록 ${s.unmatched} · 프리즘미지정 ${s.no_prism} · <b>총 소비 ${n(s.total_consumed)}</b></div>
      <label class="field row"><input type="checkbox" id="plan-final"/><span>월말 최종본(is_final)</span></label>
      <div class="form-actions" style="margin:8px 0 14px">
        <button class="btn primary" id="plan-commit">이대로 확정(소비 차감)</button>
      </div>
      <table class="tbl"><thead><tr><th>제품코드</th><th class="right">생산수량</th><th>상태</th><th>프리즘</th><th class="right">소비</th></tr></thead>
        <tbody>${lineRows || '<tr><td colspan="5" class="muted">수량 있는 행 없음</td></tr>'}</tbody></table>
      <p class="muted" style="margin-top:6px">미등록 제품은 기준정보 ▸ 제품마스터에 등록하면 다음부터 자동 반영됩니다.</p>`;
  }

  // ── 임포트된 계획 목록 ────────────────────────────────────
  function plansTable() {
    const rows = plans.map((p) =>
      `<tr><td>${esc(p.plan_month)}</td><td>${p.is_final ? '<span class="pill active">최종</span>' : '<span class="pill remnant">잠정</span>'}</td>
        <td>${esc(p.source_file || "")}</td><td class="right">${p.line_count}</td><td class="right">${n(p.consumed_total)}</td>
        <td>${esc((p.imported_at || "").slice(0, 16))}</td>
        <td><button class="mini danger" data-act="delplan" data-id="${p.id}">취소</button></td></tr>`).join("");
    return `<table class="tbl"><thead><tr><th>계획월</th><th>구분</th><th>파일</th><th class="right">행</th><th class="right">총소비</th><th>임포트</th><th></th></tr></thead>
      <tbody>${rows || '<tr><td colspan="7" class="muted">임포트된 계획 없음</td></tr>'}</tbody></table>`;
  }

  async function refreshPlans() {
    plans = (await get("/api/plans")).items || [];
    el("plan-list").innerHTML = plansTable();
  }

  // ── ERP 수불부 소모 임포트 ────────────────────────────────
  async function doLedgerPreview(prismId) {
    if (!ledgerB64) return toast("엑셀 파일을 선택하세요.", "warn");
    const body = { content: ledgerB64 };
    if (prismId) body.prism_id = prismId;
    const r = await post("/api/ledger/preview", body);
    const box = el("ledger-preview");
    if (!r.ok) { box.innerHTML = `<div class="muted">${esc(r.error || "")}</div>`; return; }
    const s = r.summary;
    const prismOpts = (r.prisms || []).map((p) => `<option value="${p.id}" ${p.id === r.prism_id ? "selected" : ""}>${esc(p.item_code)} · ${esc(p.spec || "")}</option>`).join("");
    const rows = r.lines.map((l) =>
      `<tr${l.status === "DUP" ? ' style="opacity:.5"' : ""}><td>${esc(l.date)}</td><td class="right">${n(l.qty)}</td><td>${esc(l.product)}</td>
        <td>${l.status === "NEW" ? '<span class="pill active">신규</span>' : '<span class="pill">이미있음</span>'}</td></tr>`).join("");
    box.innerHTML = `
      <label class="field" style="max-width:460px;margin-top:8px"><span>소비 대상 도장완료 프리즘</span><select id="ledger-prism">${prismOpts}</select></label>
      <div class="insp-head">소모 ${s.total}건 · <b style="color:var(--success-text)">신규 ${s.new}</b> · 이미있음 ${s.dup} · <b>신규 소비 ${n(s.consumed)}</b></div>
      <div class="form-actions" style="margin:8px 0 12px"><button class="btn primary" id="ledger-commit" type="button" ${s.new ? "" : "disabled"}>신규 소비 등록</button></div>
      <div class="tbl-scroll"><table class="tbl"><thead><tr><th>일자</th><th class="right">소모수량</th><th>적요(제품)</th><th>상태</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="4" class="muted">소모(출고) 줄 없음</td></tr>'}</tbody></table></div>`;
  }

  async function render() {
    plans = (await get("/api/plans")).items || [];   // 먼저 데이터 로드(아직 #plan-list 없음)
    el("plan-root").innerHTML = `
      <div class="card-surface">
        <h4>구매계획서 임포트 (.xlsx)</h4>
        <input type="file" id="plan-file" accept=".xlsx" />
        <span class="muted" id="plan-fname" style="margin-left:8px"></span>
      </div>
      <div class="card-surface" id="plan-preview"><div class="muted">파일을 선택하면 미리보기가 표시됩니다.</div></div>
      <div class="card-surface"><h4>임포트된 계획</h4><div id="plan-list">${plansTable()}</div></div>

      <div class="card-surface">
        <h4>ERP 수불부 소모 임포트 (.xlsx)</h4>
        <p class="sub">ECount 재고수불부를 올리면 '소모(출고)' 줄이 선택한 도장완료 프리즘의 소비로 등록됩니다. 이미 등록된(같은 일자·수량) 건은 자동 건너뜁니다.</p>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <input type="file" id="ledger-file" accept=".xlsx" />
          <button class="btn" id="ledger-preview-btn" type="button">미리보기</button>
        </div>
        <div id="ledger-preview"><div class="muted">파일을 선택하고 미리보기를 누르세요.</div></div>
      </div>`;
    bindOnce();
  }

  function bindOnce() {
    if (bound) return; bound = true;
    const root = el("plan-root");
    root.addEventListener("change", async (e) => {
      if (e.target.id === "plan-file") {
        const f = e.target.files[0]; if (!f) return;
        filename = f.name; el("plan-fname").textContent = f.name;
        fileB64 = await readFile(f);
        el("plan-preview").innerHTML = '<div class="muted">미리보기 불러오는 중…</div>';
        await doPreview();
      } else if (e.target.id === "plan-sheet") {
        await doPreview(e.target.value);
      } else if (e.target.id === "ledger-file") {
        const f = e.target.files[0]; if (!f) return;
        ledgerB64 = await readFile(f);
        el("ledger-preview").innerHTML = '<div class="muted">"미리보기"를 누르세요.</div>';
      } else if (e.target.id === "ledger-prism") {
        await doLedgerPreview(Number(e.target.value));   // 대상 프리즘 바뀌면 중복판정 갱신
      }
    });
    root.addEventListener("click", async (e) => {
      if (e.target.id === "plan-commit") {
        const r = await post("/api/plan/commit", {
          content: fileB64, sheet: el("plan-sheet").value, plan_month: el("plan-month").value,
          is_final: el("plan-final").checked ? 1 : 0, filename,
        });
        if (r.ok) { toast(`확정 — 총 소비 ${n(r.consumed_total)}`, "ok"); el("plan-preview").innerHTML = '<div class="muted">확정 완료. 잔량 현황에서 확인하세요.</div>'; await refreshPlans(); }
        else toast(r.error || "실패", "warn");
        return;
      }
      const del = e.target.closest('[data-act="delplan"]');
      if (del) {
        const r = await post("/api/plan/delete", { id: Number(del.dataset.id) });
        if (r.ok) { toast("계획 취소(소비 되돌림)", "ok"); await refreshPlans(); } else toast(r.error || "실패", "warn");
        return;
      }
      if (e.target.id === "ledger-preview-btn") {
        const sel = el("ledger-prism");
        return doLedgerPreview(sel ? Number(sel.value) : undefined);
      }
      if (e.target.id === "ledger-commit") {
        const r = await post("/api/ledger/commit", { content: ledgerB64, prism_id: Number(el("ledger-prism").value) });
        if (r.ok) { toast(`소비 등록 ${r.created}건 (건너뜀 ${r.skipped}) · 총 ${n(r.consumed)}`, "ok"); await doLedgerPreview(Number(el("ledger-prism").value)); }
        else toast(r.error || "실패", "warn");
      }
    });
  }

  async function show() { await render(); }
  return { show };
})();
