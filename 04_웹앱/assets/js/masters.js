// 기준정보 — 프리즘/공급사/검사항목/제품마스터 (window.Masters)
// 상단 하위메뉴(app.js)가 어떤 엔티티를 볼지 정하고, 여기서 해당 엔티티만 렌더한다.
// 4종을 '설정(config) 기반'으로 같은 틀에서 처리 → 기능 추가/수정 시 충돌 최소화.
"use strict";

window.Masters = (function () {
  const { get, post, el, esc, toast } = App;

  const cache = {};   // entity → 최근 목록(수정 시 조회용)
  const TITLE = { prism: "프리즘마스터", supplier: "공급사", item: "검사항목", product: "제품마스터" };

  function statusPill(s) {
    const m = { ACTIVE: ["active", "활성"], REMNANT: ["remnant", "잔량관리"], STOPPED: ["stopped", "중단"] };
    const [c, t] = m[s] || ["", s];
    return `<span class="pill ${c}">${t}</span>`;
  }
  const yn = (v) => (v ? '<span class="yes">○</span>' : '<span class="no">—</span>');

  // ── 엔티티별 설정 ─────────────────────────────────────────
  const paintLabel = (v) => ({ RAW: "미도장", PAINTED: "도장완료", NONE: "유리/해당없음" }[v] || v || "");

  function configs() {
    // 제품 폼의 프리즘 선택지(품목코드 위주)
    const prismOptions = [["", "미사용(프리즘 없음)"]].concat(
      (cache.prism || []).map((p) => [String(p.id), `${p.item_code || p.prism_type} · ${p.spec}`]));
    // 프리즘 폼의 공급사 선택지
    const supplierOptions = [["", "(미지정)"]].concat(
      (cache.suppliers || []).map((s) => [String(s.id), s.name]));
    // 프리즘 폼의 도장완료 페어 선택지(PAINTED 코드만)
    const paintedOptions = [["", "(없음)"]].concat(
      (cache.prism || []).filter((p) => p.paint_state === "PAINTED").map((p) => [String(p.id), `${p.item_code} · ${p.spec}`]));
    return {
      prism: {
        urls: { list: "/api/prisms", create: "/api/prisms/create", update: "/api/prisms/update", active: "/api/prisms/active" },
        hasActive: true,
        fields: [
          { name: "item_code", label: "품목코드(ERP)", type: "text" },
          { name: "prism_type", label: "종류", type: "select", options: [["PLASTIC", "Plastic"], ["GLASS", "Glass"]] },
          { name: "model", label: "모델 (U20/U10/U30)", type: "text" },
          { name: "spec", label: "품목명/규격", type: "text" },
          { name: "supplier_id", label: "공급사", type: "select", options: supplierOptions },
          { name: "paint_state", label: "도장상태", type: "select", options: [["NONE", "유리·해당없음"], ["RAW", "미도장(입고용)"], ["PAINTED", "도장완료"]] },
          { name: "painted_into_id", label: "도장완료 페어 (미도장만)", type: "select", options: paintedOptions },
          { name: "unit", label: "단위", type: "text", def: "EA" },
          { name: "note", label: "비고", type: "text" },
        ],
        columns: [
          { key: "item_code", label: "품목코드", fmt: (v) => v || "—" },
          { key: "model", label: "모델", fmt: (v) => v || "" },
          { key: "prism_type", label: "종류" },
          { key: "supplier_name", label: "공급사", fmt: (v) => v || "—" },
          { key: "paint_state", label: "도장", fmt: paintLabel },
          { key: "painted_into_code", label: "페어→", fmt: (v) => v || "—" },
        ],
      },
      supplier: {
        urls: { list: "/api/suppliers", create: "/api/suppliers/create", update: "/api/suppliers/update" },
        hasActive: false,
        fields: [
          { name: "name", label: "공급사명", type: "text" },
          { name: "status", label: "상태", type: "select", options: [["ACTIVE", "활성"], ["REMNANT", "잔량관리(폐업)"], ["STOPPED", "중단"]] },
          { name: "note", label: "비고", type: "text" },
        ],
        columns: [
          { key: "name", label: "공급사" }, { key: "status", label: "상태", fmt: statusPill },
          { key: "note", label: "비고", fmt: (v) => v || "" },
        ],
      },
      item: {
        urls: { list: "/api/inspection-items", create: "/api/inspection-items/create",
                update: "/api/inspection-items/update", active: "/api/inspection-items/active" },
        hasActive: true,
        fields: [
          { name: "name", label: "검사항목", type: "text" }, { name: "category", label: "분류", type: "text" },
          { name: "applies_to_incoming", label: "입고검사 적용", type: "checkbox", def: true },
          { name: "applies_to_post_paint", label: "페인트후검사 적용", type: "checkbox", def: true },
          { name: "sort_order", label: "정렬순서", type: "number" },
        ],
        columns: [
          { key: "sort_order", label: "#" }, { key: "name", label: "항목" }, { key: "category", label: "분류", fmt: (v) => v || "" },
          { key: "applies_to_incoming", label: "입고", fmt: yn }, { key: "applies_to_post_paint", label: "페인트후", fmt: yn },
        ],
      },
      product: {
        urls: { list: "/api/products", create: "/api/products/create", update: "/api/products/update", active: "/api/products/active" },
        hasActive: true,
        fields: [
          { name: "product_code", label: "제품코드", type: "text" }, { name: "product_name", label: "제품명", type: "text" },
          { name: "prism_id", label: "사용 프리즘", type: "select", options: prismOptions },
          { name: "prism_per_unit", label: "대당 소요량", type: "number", def: 1 }, { name: "note", label: "비고", type: "text" },
        ],
        columns: [
          { key: "product_code", label: "제품코드" }, { key: "product_name", label: "제품명", fmt: (v) => v || "" },
          { key: "prism_type", label: "프리즘", fmt: (v, r) => (r.prism_id ? `${v} / ${r.prism_spec || ""}` : "미사용") },
          { key: "prism_per_unit", label: "대당" },
        ],
      },
    };
  }

  // ── 폼/표 만들기 ──────────────────────────────────────────
  function buildForm(key, cfg) {
    const inputs = cfg.fields.map((f) => {
      const fid = `f-${key}-${f.name}`;
      let ctrl;
      if (f.type === "select") ctrl = `<select id="${fid}">` + f.options.map(([v, t]) => `<option value="${esc(v)}">${esc(t)}</option>`).join("") + `</select>`;
      else if (f.type === "checkbox") ctrl = `<input type="checkbox" id="${fid}" ${f.def ? "checked" : ""}/>`;
      else ctrl = `<input type="${f.type}" id="${fid}" value="${esc(f.def ?? "")}"/>`;
      return `<label class="field"><span>${esc(f.label)}</span>${ctrl}</label>`;
    }).join("");
    return `<form class="m-form" id="form-${key}"><input type="hidden" id="f-${key}-id" value=""/>${inputs}
      <div class="form-actions"><button type="submit" class="btn primary">저장</button>
      <button type="button" class="btn" data-act="reset">초기화</button></div></form>`;
  }

  function buildTable(key, cfg, items, editable) {
    const head = cfg.columns.map((c) => `<th>${esc(c.label)}</th>`).join("") + (cfg.hasActive ? "<th>사용</th>" : "") + (editable ? "<th>관리</th>" : "");
    const body = items.map((r) => {
      const tds = cfg.columns.map((c) => `<td>${c.fmt ? c.fmt(r[c.key], r) : esc(r[c.key])}</td>`).join("");
      const activeCell = cfg.hasActive
        ? (editable
            ? `<td><button class="mini" data-act="toggle" data-id="${r.id}" data-cur="${r.is_active}">${r.is_active ? "사용중" : "중지"}</button></td>`
            : `<td>${r.is_active ? "사용중" : "중지"}</td>`)
        : "";
      const editCell = editable ? `<td><button class="mini" data-act="edit" data-id="${r.id}">수정</button></td>` : "";
      return `<tr>${tds}${activeCell}${editCell}</tr>`;
    }).join("");
    return `<table class="tbl"><thead><tr>${head}</tr></thead><tbody>${body || `<tr><td colspan="9" class="muted">데이터 없음</td></tr>`}</tbody></table>`;
  }

  // ── 데이터 ────────────────────────────────────────────────
  async function loadList(key) {
    const res = await get(configs()[key].urls.list);
    cache[key] = res.items || [];
    return cache[key];
  }

  async function loadSuppliers() {
    cache.suppliers = (await get("/api/suppliers")).items || [];
  }

  function gatherForm(key, cfg) {
    const data = {};
    const idVal = el(`f-${key}-id`).value;
    if (idVal) data.id = Number(idVal);
    cfg.fields.forEach((f) => {
      const node = el(`f-${key}-${f.name}`);
      data[f.name] = f.type === "checkbox" ? (node.checked ? 1 : 0) : node.value;
    });
    return data;
  }
  function fillForm(key, cfg, row) {
    el(`f-${key}-id`).value = row.id;
    cfg.fields.forEach((f) => {
      const node = el(`f-${key}-${f.name}`);
      if (f.type === "checkbox") node.checked = !!row[f.name]; else node.value = row[f.name] ?? "";
    });
  }
  function resetForm(key, cfg) {
    el(`f-${key}-id`).value = "";
    cfg.fields.forEach((f) => {
      const node = el(`f-${key}-${f.name}`);
      if (f.type === "checkbox") node.checked = !!f.def; else node.value = f.def ?? "";
    });
  }

  let current = null;     // 현재 보고 있는 {key, cfg}
  let rootBound = false;  // 위임 핸들러 1회만 부착

  // 폼 제출(폼 요소는 렌더마다 새로 생성 → 매번 부착해도 누수 없음)
  function bindForm(key, cfg) {
    el(`form-${key}`).addEventListener("submit", async (e) => {
      e.preventDefault();
      const data = gatherForm(key, cfg);
      const r = await post(data.id ? cfg.urls.update : cfg.urls.create, data);
      if (r.ok) { toast(data.id ? "수정되었습니다." : "등록되었습니다.", "ok"); await render(key); }
      else toast(r.error || "실패했습니다.", "warn");
    });
  }

  // masters-root 클릭 위임은 단 한 번만 부착하고, current 로 대상 엔티티를 판단
  function bindRootOnce() {
    if (rootBound) return;
    rootBound = true;
    el("masters-root").addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-act]"); if (!btn || !current) return;
      const { key, cfg } = current;
      const act = btn.dataset.act;
      if (act === "reset") return resetForm(key, cfg);
      if (act === "edit") {
        const row = (cache[key] || []).find((x) => String(x.id) === btn.dataset.id);
        if (row) { fillForm(key, cfg, row); el("masters-root").scrollIntoView({ behavior: "smooth", block: "start" }); }
        return;
      }
      if (act === "toggle") {
        const r = await post(cfg.urls.active, { id: Number(btn.dataset.id), is_active: btn.dataset.cur === "1" ? 0 : 1 });
        if (r.ok) { toast("변경되었습니다.", "ok"); await render(key); } else toast(r.error || "실패", "warn");
      }
    });
  }

  // ── 렌더(한 엔티티) ───────────────────────────────────────
  async function render(key) {
    // 드롭다운 의존 데이터 먼저 로드 (프리즘 폼: 공급사 + 도장완료 페어, 제품 폼: 프리즘 목록)
    await loadList(key);
    if (key === "prism" || key === "product") {
      if (!cache.suppliers) await loadSuppliers();
      if (key !== "prism") await loadList("prism");
    }
    const cfg = configs()[key];
    current = { key, cfg };
    const canEdit = !!(window.App && App.isAdmin);   // 기준정보 편집은 관리자만(서버가 최종 강제)
    if (canEdit) {
      el("masters-root").innerHTML = `<div class="m-grid"><div>${buildForm(key, cfg)}</div><div>${buildTable(key, cfg, cache[key], true)}</div></div>`;
      bindForm(key, cfg);
    } else {
      el("masters-root").innerHTML =
        `<div class="notice-readonly">기준정보 편집은 <b>관리자</b>만 가능합니다. (조회 전용)</div>${buildTable(key, cfg, cache[key], false)}`;
    }
    bindRootOnce();
  }

  // ── 진입점: 상단 하위메뉴가 호출 ─────────────────────────
  async function show(key) {
    if (!TITLE[key]) key = "prism";
    el("masters-title").textContent = `기준정보 · ${TITLE[key]}`;
    await render(key);
  }

  return { show };
})();
