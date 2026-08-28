// 도장완료 품목 페인트후 불량(품목 레벨 일괄) — 페인트후검사 탭에 삽입 (window.PaintBatch)
"use strict";

window.PaintBatch = (function () {
  const { get, post, el, esc, toast } = App;
  const n = (v) => Number(v || 0).toLocaleString();
  const n2 = (v) => Number(v || 0);
  const today = () => new Date().toISOString().slice(0, 10);
  let prisms = [], items = [], batches = [], fileB64 = null, selectedPrism = null;
  const pbSel = {};   // prism_id → 선택된 batch_id (검사내역 상세)
  let editingBid = null;   // 인라인 수정 중인 batch_id (null = 조회모드)

  function sectionHtml() {
    return `<div class="card-surface" style="margin-top:16px" id="pb-root"><div class="muted">불러오는 중…</div></div>`;
  }

  // 선택된 배치 상세(양불·불량유형) — 입고이력 상세와 동일 형식
  function pbDetail(b) {
    if (!b) return '<div class="ih-detail muted">반납일을 선택하세요.</div>';
    const canEdit = !window.App || App.canEdit !== false;
    if (canEdit && editingBid === b.id) return pbEditForm(b);   // 인라인 수정 모드
    const total = n2(b.good_qty) + n2(b.defect_qty);
    const rate = total ? (n2(b.defect_qty) / total * 100).toFixed(2) + "%" : "—";
    let rows;
    if (b.defects && b.defects.length) {
      const maxq = Math.max.apply(null, b.defects.map((d) => n2(d.defect_qty))) || 1;
      rows = b.defects.map((d) =>
        `<tr><td>${esc(d.name)}</td><td class="right">${n(d.defect_qty)}</td>
          <td class="ih-barcell"><span class="ih-bar" style="width:${Math.round(n2(d.defect_qty) / maxq * 100)}%"></span></td></tr>`).join("");
    } else {
      rows = '<tr><td colspan="3" class="muted">불량 없음</td></tr>';
    }
    return `<div class="ih-detail">
      <div class="ih-detail-head"><b>${esc(b.batch_date)}</b> 반납분 <span class="pill active">등록</span>
        ${canEdit ? `<span style="float:right;display:inline-flex;gap:6px">
          <button class="mini" data-act="pb-edit" data-id="${b.id}">수정</button>
          <button class="mini danger" data-act="pb-del" data-id="${b.id}">삭제</button></span>` : ""}</div>
      <div class="ih-stat-row">
        <div class="ih-stat"><span>반납수량</span><b>${n(total)}</b></div>
        <div class="ih-stat"><span>양품</span><b class="yes">${n(b.good_qty)}</b></div>
        <div class="ih-stat"><span>불량</span><b class="ih-bad">${n(b.defect_qty)}</b></div>
        <div class="ih-stat"><span>불량률</span><b>${rate}</b></div>
      </div>
      <table class="tbl ih-def"><thead><tr><th>불량유형</th><th class="right">수량</th><th>비중</th></tr></thead>
        <tbody>${rows}</tbody></table>
    </div>`;
  }

  // 인라인 수정 폼 — 양품 + 불량유형별 수량만 그 자리에서 고침 (삭제 없이)
  function pbEditForm(b) {
    const cur = {};   // item_id → 현재 수량
    (b.defects || []).forEach((d) => { if (d.item_id != null) cur[d.item_id] = n2(d.defect_qty); });
    // 표시 항목: 활성 페인트후 검사항목 ∪ 이 배치에 이미 있는 항목(비활성 포함)
    const seen = new Set(items.map((it) => it.id));
    const rowItems = items.slice();
    (b.defects || []).forEach((d) => { if (d.item_id != null && !seen.has(d.item_id)) { rowItems.push({ id: d.item_id, name: d.name }); seen.add(d.item_id); } });
    const rows = rowItems.map((it) =>
      `<tr><td>${esc(it.name)}</td>
        <td class="right"><input type="number" min="0" class="pb-edit-def" data-item="${it.id}" value="${cur[it.id] || 0}" style="width:110px"/></td></tr>`).join("")
      || '<tr><td colspan="2" class="muted">페인트후 검사항목 없음 — 위 "검사항목 편집"에서 추가</td></tr>';
    return `<div class="ih-detail">
      <div class="ih-detail-head"><b>${esc(b.batch_date)}</b> 반납분 <span class="pill">수정 중</span>
        <span style="float:right;display:inline-flex;gap:6px">
          <button class="mini primary" data-act="pb-edit-save" data-id="${b.id}">저장</button>
          <button class="mini" data-act="pb-edit-cancel">취소</button></span></div>
      <label class="field" style="max-width:220px;margin:8px 0"><span>양품 수량</span>
        <input type="number" min="0" id="pb-edit-good" value="${n2(b.good_qty)}"/></label>
      <table class="tbl ih-def"><thead><tr><th>불량유형</th><th class="right">불량수량</th></tr></thead>
        <tbody>${rows}</tbody></table>
      <p class="muted" style="font-size:12px;margin:6px 0 0">불량률·집계는 저장 시 자동 반영됩니다. 0 으로 두면 그 유형은 제외됩니다.</p>
    </div>`;
  }

  // 도장검사 내역 — 품목별 카드 + 반납일 칩 → 상세 (입고이력과 동일 방식)
  function historyHtml() {
    if (!batches.length) return '<div class="muted">등록된 검사내역이 없습니다.</div>';
    const groups = {};
    batches.forEach((b) => { (groups[b.prism_id] = groups[b.prism_id] || []).push(b); });
    return Object.keys(groups).map((pid) => {
      const list = groups[pid].slice().sort((a, b) => (a.batch_date < b.batch_date ? -1 : 1));
      const first = list[0];
      const totGood = list.reduce((s, b) => s + n2(b.good_qty), 0);
      const totDef = list.reduce((s, b) => s + n2(b.defect_qty), 0);
      if (pbSel[pid] === undefined) pbSel[pid] = list[list.length - 1].id;   // 기본: 최근
      const chips = list.map((b) => {
        const total = n2(b.good_qty) + n2(b.defect_qty);
        const rate = total ? (n2(b.defect_qty) / total * 100).toFixed(2) : 0;
        const active = pbSel[pid] === b.id ? "active" : "";
        const tone = rate >= 20 ? "hi" : "";
        return `<button type="button" class="ih-col ${active} ${tone}" data-prism="${pid}" data-bid="${b.id}">
          <span class="ih-col-date">${esc(b.batch_date)}</span>
          <span class="ih-col-qty">${n(total)}</span>
          <span class="ih-col-rate">불량 ${rate}%</span>
        </button>`;
      }).join("");
      const selB = list.find((b) => b.id === pbSel[pid]) || null;
      return `<div class="card-surface ih-item">
        <div class="ih-item-head"><div class="ih-item-title">
          <span class="ih-code">${esc(first.item_code || "")}</span>
          <span class="muted">${esc(first.spec || "")} · 도장완료</span></div>
          <div class="ih-summary">누적 양품 <b>${n(totGood)}</b> <span class="muted">· 불량 ${n(totDef)} · 반납 ${list.length}건</span></div>
        </div>
        <div class="ih-cols">${chips}</div>
        ${pbDetail(selB)}
      </div>`;
    }).join("");
  }

  function render() {
    const root = el("pb-root"); if (!root) return;
    if (selectedPrism == null && prisms.length) selectedPrism = prisms[0].id;
    const canEdit = !window.App || App.canEdit !== false;   // 담당자·관리자만 입력 폼
    const prismOpts = prisms.map((p) => `<option value="${p.id}" ${p.id === selectedPrism ? "selected" : ""}>${esc(p.item_code)} · ${esc(p.spec || "")}</option>`).join("");
    const itemRows = items.map((it) => `<tr><td>${esc(it.name)}</td><td>${esc(it.category || "")}</td>
      <td><input type="number" min="0" class="pb-def" data-item="${it.id}" value="0" style="width:90px"/></td></tr>`).join("");

    const entryHtml = !canEdit ? "" : `
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
      </div>`;

    root.innerHTML = `
      <h3 style="margin-top:0">도장완료 페인트후검사 <span class="muted" style="font-weight:400;font-size:12px">품목 레벨 · 로트 무관</span></h3>
      <p class="sub">도장완료 프리즘의 반납일별 양품/불량 검사내역. 집계 '페인트후 불량'에 반영됩니다.</p>
      ${entryHtml}
      <h4 style="margin-top:16px">도장검사 내역 <span class="muted" style="font-weight:400;font-size:12px">반납일 클릭 → 양불·불량유형</span></h4>
      ${historyHtml()}`;
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
      const chip = e.target.closest(".ih-col");
      if (chip) { editingBid = null; pbSel[Number(chip.dataset.prism)] = Number(chip.dataset.bid); render(); return; }
      const edit = e.target.closest('[data-act="pb-edit"]');
      if (edit) { editingBid = Number(edit.dataset.id); render(); return; }
      if (e.target.closest('[data-act="pb-edit-cancel"]')) { editingBid = null; render(); return; }
      const save = e.target.closest('[data-act="pb-edit-save"]');
      if (save) {
        const good = el("pb-edit-good");
        const defects = [...document.querySelectorAll(".pb-edit-def")].map((i) => ({ item_id: Number(i.dataset.item), qty: Number(i.value || 0) }));
        const r = await post("/api/paint-batch/update", { id: Number(save.dataset.id), good_qty: good ? good.value : 0, defects });
        if (r.ok) { toast(`수정됨 (양품 ${n(r.good_qty)} / 불량 ${n(r.defect_qty)})`, "ok"); editingBid = null; await reload(); }
        else toast(r.error || "실패", "warn");
        return;
      }
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
