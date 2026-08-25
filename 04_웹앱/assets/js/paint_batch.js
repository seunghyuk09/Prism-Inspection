// 도장완료 품목 페인트후 불량(품목 레벨 일괄) — 페인트후검사 탭에 삽입 (window.PaintBatch)
"use strict";

window.PaintBatch = (function () {
  const { get, post, el, esc, toast } = App;
  const n = (v) => Number(v || 0).toLocaleString();
  const today = () => new Date().toISOString().slice(0, 10);
  let prisms = [], items = [], batches = [], fileB64 = null, selectedPrism = null;

  function sectionHtml() {
    return `<div class="card-surface" style="margin-top:16px" id="pb-root"><div class="muted">불러오는 중…</div></div>`;
  }

  function render() {
    const root = el("pb-root"); if (!root) return;
    if (selectedPrism == null && prisms.length) selectedPrism = prisms[0].id;
    const prismOpts = prisms.map((p) => `<option value="${p.id}" ${p.id === selectedPrism ? "selected" : ""}>${esc(p.item_code)} · ${esc(p.spec || "")}</option>`).join("");
    const itemRows = items.map((it) => `<tr><td>${esc(it.name)}</td><td>${esc(it.category || "")}</td>
      <td><input type="number" min="0" class="pb-def" data-item="${it.id}" value="0" style="width:90px"/></td></tr>`).join("");
    const listHtml = batches.length
      ? `<div class="tbl-scroll"><table class="tbl"><thead><tr><th>반납일</th><th>품목</th><th class="right">양품</th><th class="right">불량</th><th>불량내역</th><th>관리</th></tr></thead>
        <tbody>${batches.map((b) => `<tr><td>${esc(b.batch_date)}</td><td>${esc(b.item_code || "")}</td>
          <td class="right good-t">${n(b.good_qty)}</td><td class="right bad-t">${n(b.defect_qty)}</td>
          <td class="muted" style="font-size:12px">${b.defects.map((d) => esc(d.name) + " " + n(d.defect_qty)).join(", ")}</td>
          <td><button class="mini danger" data-act="pb-del" data-id="${b.id}">삭제</button></td></tr>`).join("")}</tbody></table></div>`
      : '<div class="muted">등록된 배치 없음</div>';

    root.innerHTML = `
      <h3 style="margin-top:0">도장완료 품목 페인트후 불량 <span class="muted" style="font-weight:400;font-size:12px">품목 레벨 일괄 · 로트 무관</span></h3>
      <p class="sub">도장완료 프리즘의 반납일별 양품/불량을 기록합니다. 우경 불량 엑셀 업로드 또는 직접 입력. 집계 '페인트후 불량'에 반영됩니다.</p>
      <label class="field" style="max-width:460px"><span>도장완료 프리즘</span><select id="pb-prism">${prismOpts}</select></label>

      <div class="grid2" style="margin-top:12px">
        <div class="card-surface">
          <h4 style="margin-top:0">① 우경 불량 엑셀 업로드</h4>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <input type="file" id="pb-file" accept=".xlsx"/>
            <button class="btn" id="pb-preview-btn" type="button">미리보기</button>
          </div>
          <div id="pb-preview"></div>
        </div>
        <div class="card-surface">
          <h4 style="margin-top:0">② 직접 입력</h4>
          <div class="grid2-tight">
            <label class="field"><span>반납/검사일</span><input type="date" id="pb-date" value="${today()}"/></label>
            <label class="field"><span>양품 수량</span><input type="number" id="pb-good" min="0" value="0"/></label>
          </div>
          <table class="tbl"><thead><tr><th>검사항목</th><th>분류</th><th>불량수량</th></tr></thead>
            <tbody>${itemRows || '<tr><td colspan="3" class="muted">페인트후 검사항목 없음 — 위 "검사항목 편집"에서 추가</td></tr>'}</tbody></table>
          <label class="field"><span>비고</span><input type="text" id="pb-note"/></label>
          <div class="form-actions"><button class="btn primary" id="pb-save-btn" type="button">직접 입력 저장</button></div>
        </div>
      </div>

      <h4 style="margin-top:16px">등록된 페인트후 불량 배치</h4>
      ${listHtml}`;
  }

  async function previewExcel() {
    if (!fileB64) return toast("엑셀 파일을 선택하세요.", "warn");
    const prism_id = Number(el("pb-prism").value);
    const r = await post("/api/paint-batch/preview", { content: fileB64, prism_id });
    if (!r.ok) return toast(r.error || "실패", "warn");
    const rows = r.batches.map((b) => `<tr${b.already ? ' style="opacity:.5"' : ""}><td>${esc(b.batch_date)}</td><td class="right good-t">${n(b.good)}</td>
      <td class="right bad-t">${n(b.total - b.good)}</td><td style="font-size:12px">${b.defects.map((d) => esc(d.name) + " " + n(d.qty)).join(", ")}</td>
      <td>${b.already ? '<span class="pill">이미있음</span>' : '<span class="pill active">신규</span>'}</td></tr>`).join("");
    el("pb-preview").innerHTML = `<div class="tbl-scroll" style="margin-top:8px"><table class="tbl"><thead><tr><th>반납일</th><th class="right">양품</th><th class="right">불량</th><th>불량내역</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>
      <div style="margin-top:8px">신규 <b>${r.summary.new_batches}</b>건 · 양품 ${n(r.summary.good)} · 불량 ${n(r.summary.defect)}
      <button class="btn primary" id="pb-commit-btn" type="button" ${r.summary.new_batches ? "" : "disabled"}>확정 등록</button></div>`;
  }

  async function commitExcel() {
    const prism_id = Number(el("pb-prism").value);
    const r = await post("/api/paint-batch/commit", { content: fileB64, prism_id });
    if (r.ok) { toast(`등록 ${r.created}건 (건너뜀 ${r.skipped})`, "ok"); fileB64 = null; await reload(); }
    else toast(r.error || "실패", "warn");
  }

  async function saveManual() {
    const prism_id = Number(el("pb-prism").value);
    const defects = [...document.querySelectorAll(".pb-def")].map((i) => ({ item_id: Number(i.dataset.item), qty: Number(i.value || 0) }));
    const r = await post("/api/paint-batch/save", {
      prism_id, batch_date: el("pb-date").value, good_qty: el("pb-good").value, defects, note: el("pb-note").value,
    });
    if (r.ok) { toast(`저장 (양품 ${n(r.good_qty)} / 불량 ${n(r.defect_qty)})`, "ok"); await reload(); }
    else toast(r.error || "실패", "warn");
  }

  async function reload() {
    batches = (await get("/api/paint-batches")).items || [];
    render();
  }

  async function mount() {
    const root = el("pb-root"); if (!root) return;
    prisms = (await get("/api/painted-prisms")).items || [];
    items = ((await get("/api/inspection-items")).items || []).filter((it) => it.applies_to_post_paint && it.is_active);
    batches = (await get("/api/paint-batches")).items || [];
    render();
    // 이벤트 위임(root 는 이 mount 동안 유지 → render 로 innerHTML 교체돼도 리스너 유지)
    root.addEventListener("change", (e) => {
      if (e.target.id === "pb-prism") { selectedPrism = Number(e.target.value); return; }
      if (e.target.id !== "pb-file") return;
      const f = e.target.files[0]; if (!f) return;
      const rd = new FileReader(); rd.onload = () => { fileB64 = rd.result; }; rd.readAsDataURL(f);
    });
    root.addEventListener("click", async (e) => {
      if (e.target.id === "pb-preview-btn") return previewExcel();
      if (e.target.id === "pb-commit-btn") return commitExcel();
      if (e.target.id === "pb-save-btn") return saveManual();
      const del = e.target.closest('[data-act="pb-del"]');
      if (del) {
        if (!confirm("이 배치를 삭제할까요?")) return;
        const r = await post("/api/paint-batch/delete", { id: Number(del.dataset.id) });
        if (r.ok) { toast("삭제됨", "ok"); await reload(); } else toast(r.error || "실패", "warn");
      }
    });
  }

  return { sectionHtml, mount };
})();
