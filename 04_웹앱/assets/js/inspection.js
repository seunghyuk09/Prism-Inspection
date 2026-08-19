// 검사 · 페인트 — 단계별 페이지 (window.Inspection)
// 입고검사(INCOMING) / 페인트 발송·회수(PAINT) / 페인트후검사(POST_PAINT) 를
// 각각 별도 페이지로. 페이지마다 '그 단계 대상 로트 목록 + 그 작업만' 보여준다.
"use strict";

window.Inspection = (function () {
  const { get, post, el, esc, toast } = App;

  let lots = [];
  const selected = { INCOMING: null, PAINT: null, POST_PAINT: null };
  const boundStages = new Set();

  const n = (v) => Number(v || 0).toLocaleString();
  const today = () => new Date().toISOString().slice(0, 10);
  const ratePct = (q, base) => (base > 0 ? ((q / base) * 100).toFixed(2) + "%" : "—");
  const rootOf = (stage) => el("stage-root-" + stage);

  // 이 단계 대상 로트인가
  function eligible(stage, l) {
    if (stage === "INCOMING") return true;
    if (stage === "PAINT") return l.prism_type === "PLASTIC" && !!l.incoming_done;
    if (stage === "POST_PAINT") return l.prism_type === "PLASTIC" && (l.returned_sum || 0) > 0;
    return false;
  }

  // ── 로트 목록(단계별 컬럼) ────────────────────────────────
  function lotListHtml(stage) {
    const items = lots.filter((l) => eligible(stage, l));
    let head, rowsFn, colspan;
    if (stage === "INCOMING") {
      head = "<th>로트번호</th><th class='right'>수량</th><th>종류</th><th>입고검사</th>"; colspan = 4;
      rowsFn = (l) => `<td>${esc(l.lot_no)}</td><td class="right">${n(l.lot_qty)}</td><td>${esc(l.prism_type)}</td>
        <td>${l.incoming_done ? '<span class="yes">완료</span>' : '<span class="no">대기</span>'}</td>`;
    } else if (stage === "PAINT") {
      head = "<th>로트번호</th><th class='right'>입고양품</th><th class='right'>발송</th><th class='right'>회수</th><th>상태</th>"; colspan = 5;
      rowsFn = (l) => {
        const remain = (l.sent_sum || 0) - (l.returned_sum || 0);
        const st = (l.sent_sum || 0) === 0 ? '<span class="no">발송대기</span>'
          : (remain > 0 ? `<span class="pill remnant">미회수 ${n(remain)}</span>` : '<span class="pill active">회수완료</span>');
        return `<td>${esc(l.lot_no)}</td><td class="right">${n(l.incoming_good)}</td>
          <td class="right">${n(l.sent_sum)}</td><td class="right">${n(l.returned_sum)}</td><td>${st}</td>`;
      };
    } else {
      head = "<th>로트번호</th><th class='right'>회수합</th><th>페인트후검사</th>"; colspan = 3;
      rowsFn = (l) => `<td>${esc(l.lot_no)}</td><td class="right">${n(l.returned_sum)}</td>
        <td>${l.post_done ? '<span class="yes">완료</span>' : '<span class="pill remnant">진행/대기</span>'}</td>`;
    }
    const title = { INCOMING: "입고검사 대상 로트", PAINT: "페인트 대상 로트 (입고검사 완료)", POST_PAINT: "페인트후검사 대상 로트 (회수분)" }[stage];
    const body = items.map((l) =>
      `<tr class="clickable" data-id="${l.id}" ${l.id === selected[stage] ? 'style="background:var(--row-hover)"' : ""}>${rowsFn(l)}</tr>`).join("");
    return `<h4>${title}</h4><table class="tbl"><thead><tr>${head}</tr></thead>
      <tbody>${body || `<tr><td colspan="${colspan}" class="muted">대상 로트 없음</td></tr>`}</tbody></table>`;
  }

  // ── 검사 섹션(입고검사 / 페인트후검사 공용) ───────────────
  function inspSection(stage, title, p) {
    const itemRows = p.items.map((it) => {
      const q = p.defects[it.id] || 0;
      return `<tr><td>${esc(it.name)}</td><td>${esc(it.category || "")}</td>
        <td><input type="number" min="0" class="def-input" data-stage="${stage}" data-item="${it.id}" value="${q}" style="width:96px"/></td>
        <td class="right" data-rate="${stage}-${it.id}">${ratePct(q, p.base_qty)}</td></tr>`;
    }).join("");
    return `<div class="insp-section"><h3>${title}</h3>
      <form class="m-form" id="insp-form-${stage}" data-stage="${stage}" data-base="${p.base_qty}">
        <div class="insp-head">검사수량(전수) <b>${n(p.base_qty)}</b> · 불량 <b id="dq-${stage}">${n(p.defect_qty)}</b> · 양품 <b id="gq-${stage}">${n(p.good_qty)}</b>
          ${p.is_complete ? '<span class="pill active" style="margin-left:8px">완료</span>' : '<span class="pill remnant" style="margin-left:8px">진행중</span>'}</div>
        <div class="grid2-tight">
          <label class="field"><span>검사 시작일</span><input type="date" id="insp-${stage}-start" value="${esc(p.start_date)}"/></label>
          <label class="field"><span>검사 종료일</span><input type="date" id="insp-${stage}-end" value="${esc(p.end_date)}"/></label>
          <label class="field"><span>검사원</span><input type="text" id="insp-${stage}-inspector" value="${esc(p.inspector)}"/></label>
          <label class="field row"><input type="checkbox" id="insp-${stage}-complete" ${p.is_complete ? "checked" : ""}/><span>검사 완료</span></label>
        </div>
        <table class="tbl"><thead><tr><th>검사항목</th><th>분류</th><th>불량수량</th><th class="right">불량률</th></tr></thead>
          <tbody>${itemRows || '<tr><td colspan="4" class="muted">적용 검사항목 없음</td></tr>'}</tbody></table>
        <label class="field"><span>비고</span><input type="text" id="insp-${stage}-note" value="${esc(p.note)}"/></label>
        <div class="form-actions"><button class="btn primary" type="submit">${title} 저장</button></div>
      </form></div>`;
  }

  // ── 페인트 외주 섹션 ──────────────────────────────────────
  function paintSection(paint) {
    const jobs = paint.jobs.map((j) => {
      const remain = j.sent_qty - j.returned_sum;
      const rets = j.returns.map((r) => `<tr><td>${esc(r.returned_date)}</td><td class="right">${n(r.returned_qty)}</td><td>${esc(r.note || "")}</td></tr>`).join("");
      const retForm = remain > 0 ? `<form class="m-form paint-return-form" data-job="${j.id}" style="margin-top:8px">
          <div class="grid2-tight">
            <label class="field"><span>회수일</span><input type="date" class="pr-date" value="${today()}"/></label>
            <label class="field"><span>회수수량 (미회수 ${n(remain)})</span><input type="number" class="pr-qty" min="1" max="${remain}"/></label>
          </div><div class="form-actions"><button class="btn" type="submit">회수 추가</button></div></form>` : "";
      return `<div class="paint-job">
        <div>발송 ${esc(j.sent_date)} · ${esc(j.vendor || "(업체 미지정)")} · 발송 <b>${n(j.sent_qty)}</b> · 회수 <b>${n(j.returned_sum)}</b> ·
          ${j.is_returned ? '<span class="pill active">회수완료</span>' : `<span class="pill remnant">미회수 ${n(remain)}</span>`}</div>
        <table class="tbl"><thead><tr><th>회수일</th><th class="right">회수수량</th><th>비고</th></tr></thead>
          <tbody>${rets || '<tr><td colspan="3" class="muted">회수 없음</td></tr>'}</tbody></table>${retForm}</div>`;
    }).join("");
    const sendForm = `<form class="m-form" id="paint-send-form">
        <div class="insp-head">발송 가능 잔량 <b>${n(paint.sendable)}</b> (입고검사 양품 − 발송합 ${n(paint.sent_sum)})</div>
        <div class="grid2-tight">
          <label class="field"><span>외주업체</span><input type="text" id="ps-vendor" placeholder="예: (주)대성도장"/></label>
          <label class="field"><span>발송일</span><input type="date" id="ps-date" value="${today()}"/></label>
          <label class="field"><span>발송수량 (가능 ${n(paint.sendable)})</span><input type="number" id="ps-qty" min="1" max="${paint.sendable}"/></label>
        </div><div class="form-actions"><button class="btn primary" type="submit" ${paint.sendable <= 0 ? "disabled" : ""}>페인트 발송</button></div></form>`;
    return sendForm + jobs;
  }

  // ── 상세(단계 한 가지만) ─────────────────────────────────
  async function renderDetail(stage, lotId) {
    const d = await get("/api/inspection/lot?id=" + lotId);
    const box = el("detail-" + stage);
    if (!d.ok) { box.innerHTML = `<div class="muted">${esc(d.error || "")}</div>`; return; }
    const L = d.lot;
    let html = `<div class="card-surface"><h3 style="margin-top:0">${esc(L.lot_no)} · ${esc(L.prism_type)} / ${esc(L.prism_spec || "")} · ${esc(L.supplier_name)} · 로트수량 ${n(L.lot_qty)}</h3>`;
    if (stage === "INCOMING") {
      html += inspSection("INCOMING", "입고검사 (전수)", d.incoming);
    } else if (stage === "PAINT") {
      if (!d.is_plastic) html += '<div class="muted">글래스 프리즘 — 페인트 단계 없음</div>';
      else if (!d.incoming.is_complete) html += '<div class="muted">입고검사를 완료해야 페인트 발송이 가능합니다.</div>';
      else html += `<div class="insp-head">입고검사 양품 <b>${n(d.incoming.good_qty)}</b> · 발송합 <b>${n(d.paint.sent_sum)}</b> · 회수합 <b>${n(d.paint.returned_sum)}</b></div>` + paintSection(d.paint);
    } else if (stage === "POST_PAINT") {
      if (!d.is_plastic) html += '<div class="muted">글래스 프리즘 — 페인트후검사 없음</div>';
      else if (d.post_paint.base_qty <= 0) html += '<div class="muted">페인트 회수 수량이 있어야 기록할 수 있습니다.</div>';
      else html += `<div class="insp-head">최종양품 = <b>${d.final_good == null ? "—" : n(d.final_good)}</b></div>` + inspSection("POST_PAINT", "페인트후검사 (전수)", d.post_paint);
    }
    html += `</div>`;
    box.innerHTML = html;
  }

  // ── 동작 ──────────────────────────────────────────────────
  function gatherInsp(stage) {
    const form = el("insp-form-" + stage);
    const defects = [...form.querySelectorAll(".def-input")].map((i) => ({ item_id: Number(i.dataset.item), qty: Number(i.value || 0) }));
    return {
      lot_id: selected[stage], stage, method: "FULL",
      start_date: el(`insp-${stage}-start`).value, end_date: el(`insp-${stage}-end`).value,
      inspector: el(`insp-${stage}-inspector`).value, is_complete: el(`insp-${stage}-complete`).checked ? 1 : 0,
      note: el(`insp-${stage}-note`).value, defects,
    };
  }

  function bindStage(stage) {
    if (boundStages.has(stage)) return;
    boundStages.add(stage);
    const root = rootOf(stage);

    root.addEventListener("click", async (e) => {
      const tr = e.target.closest("tr.clickable");
      if (tr) { selected[stage] = Number(tr.dataset.id); el("list-" + stage).innerHTML = lotListHtml(stage); await renderDetail(stage, selected[stage]); }
    });

    root.addEventListener("input", (e) => {
      const inp = e.target.closest(".def-input"); if (!inp) return;
      const st = inp.dataset.stage;
      const form = el("insp-form-" + st);
      const base = Number(form.dataset.base || 0);
      let sum = 0;
      form.querySelectorAll(".def-input").forEach((i) => {
        const q = Number(i.value || 0); sum += q;
        const cell = root.querySelector(`[data-rate="${st}-${i.dataset.item}"]`);
        if (cell) cell.textContent = base > 0 ? ((q / base) * 100).toFixed(2) + "%" : "—";
      });
      el("dq-" + st).textContent = sum.toLocaleString();
      el("gq-" + st).textContent = Math.max(0, base - sum).toLocaleString();
    });

    root.addEventListener("submit", async (e) => {
      e.preventDefault();
      const f = e.target;
      if (f.id === "insp-form-INCOMING" || f.id === "insp-form-POST_PAINT") {
        const r = await post("/api/inspection/save", gatherInsp(f.dataset.stage));
        if (r.ok) { toast(`검사 저장 (양품 ${n(r.good_qty)})`, "ok"); await refresh(stage); } else toast(r.error || "실패", "warn");
      } else if (f.id === "paint-send-form") {
        const r = await post("/api/paint/create", { lot_id: selected.PAINT, vendor: el("ps-vendor").value, sent_date: el("ps-date").value, sent_qty: el("ps-qty").value });
        if (r.ok) { toast("페인트 발송 등록", "ok"); await refresh("PAINT"); } else toast(r.error || "실패", "warn");
      } else if (f.classList.contains("paint-return-form")) {
        const r = await post("/api/paint/return", { paint_job_id: Number(f.dataset.job), returned_date: f.querySelector(".pr-date").value, returned_qty: f.querySelector(".pr-qty").value });
        if (r.ok) { toast("페인트 회수 등록", "ok"); await refresh("PAINT"); } else toast(r.error || "실패", "warn");
      }
    });
  }

  async function refresh(stage) {
    lots = (await get("/api/inspection/lots")).items || [];
    el("list-" + stage).innerHTML = lotListHtml(stage);
    if (selected[stage]) await renderDetail(stage, selected[stage]);
  }

  // ── 진입점: app.js 가 단계별로 호출 ──────────────────────
  async function showStage(stage) {
    lots = (await get("/api/inspection/lots")).items || [];
    const root = rootOf(stage);
    root.innerHTML = `<div class="m-grid"><div class="card-surface" id="list-${stage}">${lotListHtml(stage)}</div>
      <div id="detail-${stage}"><div class="muted">왼쪽에서 로트를 선택하세요.</div></div></div>`;
    bindStage(stage);
    // 선택값이 더 이상 대상이 아니면 해제
    if (selected[stage] && !lots.some((l) => l.id === selected[stage] && eligible(stage, l))) selected[stage] = null;
    if (selected[stage]) await renderDetail(stage, selected[stage]);
  }

  return { showStage };
})();
