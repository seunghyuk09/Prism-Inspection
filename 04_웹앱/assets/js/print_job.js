// 인쇄 작업 (window.PrintJob) — 미도장(RAW) → With Paint 전환 입력 + 이력
"use strict";

window.PrintJob = (function () {
  const { get, post, el, esc, toast } = App;
  const n = (v) => Number(v || 0).toLocaleString();
  const n2 = (v) => Number(v || 0);
  const today = () => new Date().toISOString().slice(0, 10);

  let prisms = [], jobs = [], bound = false, editingId = null;

  // 선택된 투입 품목에 연결된 산출(With Paint) 품목
  function pairOf(rawId) {
    return prisms.find((p) => p.id === Number(rawId)) || null;
  }

  // 수율 = 산출 / 투입
  function rateText(input, output) {
    const i = n2(input);
    return i ? (n2(output) / i * 100).toFixed(2) + "%" : "—";
  }

  function entryForm() {
    const opts = prisms.map((p) =>
      `<option value="${p.id}">${esc(p.item_code)} · ${esc(p.spec || "")}</option>`).join("");
    const first = prisms[0];
    const firstPainted = first ? esc(first.painted_code + " · " + (first.painted_spec || "")) : "";
    return `<div class="card-surface">
      <h4 style="margin-top:0">인쇄 작업 등록</h4>
      <p class="sub" style="margin-top:0">투입한 미도장 프리즘이 With Paint 품목으로 바뀝니다. 투입·산출 수량을 그대로 넣으세요.</p>
      <div class="grid2-tight">
        <label class="field"><span>인쇄일</span><input type="date" id="pj-date" value="${today()}"/></label>
        <label class="field"><span>투입 품목 (미도장)</span><select id="pj-raw">${opts}</select></label>
      </div>
      <label class="field"><span>산출 품목 (With Paint)</span>
        <input type="text" id="pj-painted" readonly value="${firstPainted}"/></label>
      <div class="grid2-tight">
        <label class="field"><span>투입 수량</span><input type="number" id="pj-input" min="1" value="0"/></label>
        <label class="field"><span>산출 양품</span><input type="number" id="pj-output" min="0" value="0"/></label>
      </div>
      <div class="grid2-tight">
        <label class="field"><span>인쇄 불량</span><input type="number" id="pj-defect" min="0" value="0"/></label>
        <label class="field"><span>외주처</span><input type="text" id="pj-vendor" placeholder="우경 등"/></label>
      </div>
      <label class="field"><span>비고</span><input type="text" id="pj-note"/></label>
      <div class="form-actions">
        <span class="muted" id="pj-preview">수율 —</span>
        <button class="btn primary" id="pj-save" type="button">인쇄 등록</button>
      </div>
    </div>`;
  }

  function summaryHtml() {
    const ti = jobs.reduce((s, j) => s + n2(j.input_qty), 0);
    const to = jobs.reduce((s, j) => s + n2(j.output_qty), 0);
    const td = jobs.reduce((s, j) => s + n2(j.defect_qty), 0);
    return `<div class="ih-stat-row">
      <div class="ih-stat"><span>총 투입</span><b>${n(ti)}</b></div>
      <div class="ih-stat"><span>총 산출</span><b class="yes">${n(to)}</b></div>
      <div class="ih-stat"><span>인쇄 불량</span><b class="ih-bad">${n(td)}</b></div>
      <div class="ih-stat"><span>평균 수율</span><b>${rateText(ti, to)}</b></div>
    </div>`;
  }

  function rowHtml(j, canEdit) {
    if (editingId === j.id) {
      return `<tr>
        <td><input type="date" class="pj-e-date" value="${esc(j.print_date)}" style="width:140px"/></td>
        <td>${esc(j.raw_code)}</td>
        <td class="right"><input type="number" class="pj-e-input" min="1" value="${n2(j.input_qty)}" style="width:90px"/></td>
        <td>${esc(j.painted_code)}</td>
        <td class="right"><input type="number" class="pj-e-output" min="0" value="${n2(j.output_qty)}" style="width:90px"/></td>
        <td class="right"><input type="number" class="pj-e-defect" min="0" value="${n2(j.defect_qty)}" style="width:80px"/></td>
        <td class="right">—</td>
        <td><input type="text" class="pj-e-note" value="${esc(j.note || "")}" style="width:120px"/></td>
        <td style="white-space:nowrap">
          <button class="mini primary" data-act="pj-save-edit" data-id="${j.id}">저장</button>
          <button class="mini" data-act="pj-cancel">취소</button></td>
      </tr>`;
    }
    return `<tr>
      <td style="white-space:nowrap">${esc(j.print_date)}</td>
      <td>${esc(j.raw_code)}</td>
      <td class="right">${n(j.input_qty)}</td>
      <td>${esc(j.painted_code)}</td>
      <td class="right good-t">${n(j.output_qty)}</td>
      <td class="right bad-t">${n(j.defect_qty)}</td>
      <td class="right">${rateText(j.input_qty, j.output_qty)}</td>
      <td class="muted" style="font-size:12px">${esc(j.note || "")}</td>
      <td style="white-space:nowrap">${canEdit ? `
        <button class="mini" data-act="pj-edit" data-id="${j.id}">수정</button>
        <button class="mini danger" data-act="pj-del" data-id="${j.id}">삭제</button>` : ""}</td>
    </tr>`;
  }

  function render() {
    const root = el("printjob-root"); if (!root) return;
    const canEdit = !window.App || App.canEdit !== false;
    if (!prisms.length) {
      root.innerHTML = '<div class="muted">인쇄 가능한 품목이 없습니다. 기준정보 → 프리즘마스터에서 미도장(RAW) 품목에 <b>도장완료 코드</b>를 연결해 주세요.</div>';
      return;
    }
    const rows = jobs.map((j) => rowHtml(j, canEdit)).join("")
      || '<tr><td colspan="9" class="muted">등록된 인쇄 작업이 없습니다.</td></tr>';
    root.innerHTML = `
      ${summaryHtml()}
      ${canEdit ? entryForm() : '<div class="notice-readonly">조회 전용 계정입니다.</div>'}
      <h4 style="margin-top:16px">인쇄 이력</h4>
      <div class="tbl-scroll"><table class="tbl"><thead><tr>
        <th>인쇄일</th><th>투입 품목</th><th class="right">투입</th>
        <th>산출 품목</th><th class="right">산출 양품</th><th class="right">불량</th>
        <th class="right">수율</th><th>비고</th><th></th>
      </tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  function updatePreview() {
    const box = el("pj-preview"); if (!box) return;
    const i = n2((el("pj-input") || {}).value), o = n2((el("pj-output") || {}).value);
    box.textContent = "수율 " + rateText(i, o);
  }

  async function saveNew() {
    const r = await post("/api/print-job/save", {
      print_date: el("pj-date").value,
      raw_prism_id: Number(el("pj-raw").value),
      input_qty: el("pj-input").value,
      output_qty: el("pj-output").value,
      defect_qty: el("pj-defect").value,
      vendor: el("pj-vendor").value,
      note: el("pj-note").value,
    });
    if (r.ok) { toast(`인쇄 등록 (투입 ${n(r.input_qty)} → 산출 ${n(r.output_qty)})`, "ok"); await reload(); }
    else toast(r.error || "실패", "warn");
  }

  async function saveEdit(id) {
    const q = (cls) => (document.querySelector("." + cls) || {}).value;
    const r = await post("/api/print-job/update", {
      id, print_date: q("pj-e-date"), input_qty: q("pj-e-input"),
      output_qty: q("pj-e-output"), defect_qty: q("pj-e-defect"), note: q("pj-e-note"),
    });
    if (r.ok) { toast("수정됨", "ok"); editingId = null; await reload(); }
    else toast(r.error || "실패", "warn");
  }

  async function reload() {
    jobs = (await get("/api/print-jobs")).items || [];
    render();
  }

  async function show() {
    const root = el("printjob-root"); if (!root) return;
    root.innerHTML = '<div class="muted">불러오는 중…</div>';
    prisms = (await get("/api/printable-prisms")).items || [];
    jobs = (await get("/api/print-jobs")).items || [];
    render();
    if (bound) return;
    bound = true;
    root.addEventListener("change", (e) => {
      if (e.target.id !== "pj-raw") return;
      const p = pairOf(e.target.value), box = el("pj-painted");
      if (p && box) box.value = p.painted_code + " · " + (p.painted_spec || "");
    });
    root.addEventListener("input", (e) => {
      if (e.target.id === "pj-input" || e.target.id === "pj-output") updatePreview();
    });
    root.addEventListener("click", async (e) => {
      if (e.target.id === "pj-save") return saveNew();
      const edit = e.target.closest('[data-act="pj-edit"]');
      if (edit) { editingId = Number(edit.dataset.id); render(); return; }
      if (e.target.closest('[data-act="pj-cancel"]')) { editingId = null; render(); return; }
      const se = e.target.closest('[data-act="pj-save-edit"]');
      if (se) return saveEdit(Number(se.dataset.id));
      const del = e.target.closest('[data-act="pj-del"]');
      if (del) {
        if (!confirm("이 인쇄 작업을 삭제할까요? 재고가 되돌아갑니다.")) return;
        const r = await post("/api/print-job/delete", { id: Number(del.dataset.id) });
        if (r.ok) { toast("삭제됨", "ok"); await reload(); } else toast(r.error || "실패", "warn");
      }
    });
  }

  return { show };
})();
