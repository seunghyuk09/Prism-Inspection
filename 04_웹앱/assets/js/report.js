// 집계 (window.Report) — 현황 요약 + 원형/추이 그래프 + 로트/공급사/항목별 표 + 엑셀 다운로드
"use strict";

window.Report = (function () {
  const { get, el, esc } = App;
  let data = null, bound = false, curProduct = "", reqSeq = 0;
  const num = (v) => Number(v || 0);
  const n = (v) => num(v).toLocaleString();
  const pct = (v) => (v || v === 0 ? v + "%" : "—");

  // 불량유형용 색 팔레트(양품=초록/불량=빨강은 고정색 사용)
  const GOOD = "#48c78e", BAD = "#ff6b6b";
  const PAL = ["#7c9cff", "#f7b955", "#ff6b6b", "#4bc0d9", "#9b8cff", "#f472b6",
               "#34d399", "#fb923c", "#c084fc", "#facc15", "#60a5fa", "#94a3b8"];

  function dl(url) {
    const a = document.createElement("a");
    a.href = url; document.body.appendChild(a); a.click(); a.remove();
  }

  // ── 순수 SVG 도넛(고리) 차트 ──────────────────────────────
  function donut(segments, center, centerSub) {
    const R = 72, r = 46, cx = 90, cy = 90;
    const nz = segments.filter((s) => num(s.value) > 0);
    const total = nz.reduce((s, x) => s + num(x.value), 0);
    let paths = "";
    if (total <= 0) {
      paths = `<circle cx="${cx}" cy="${cy}" r="${(R + r) / 2}" fill="none" stroke="var(--border)" stroke-width="${R - r}"/>`;
    } else if (nz.length === 1) {
      paths = `<circle cx="${cx}" cy="${cy}" r="${(R + r) / 2}" fill="none" stroke="${nz[0].color}" stroke-width="${R - r}"><title>${esc(nz[0].label)}: ${n(nz[0].value)} (100%)</title></circle>`;
    } else {
      let a0 = -Math.PI / 2;
      nz.forEach((s) => {
        const frac = num(s.value) / total;
        const a1 = a0 + frac * 2 * Math.PI, big = frac > 0.5 ? 1 : 0;
        const xo0 = cx + R * Math.cos(a0), yo0 = cy + R * Math.sin(a0);
        const xo1 = cx + R * Math.cos(a1), yo1 = cy + R * Math.sin(a1);
        const xi1 = cx + r * Math.cos(a1), yi1 = cy + r * Math.sin(a1);
        const xi0 = cx + r * Math.cos(a0), yi0 = cy + r * Math.sin(a0);
        paths += `<path d="M${xo0.toFixed(2)} ${yo0.toFixed(2)} A${R} ${R} 0 ${big} 1 ${xo1.toFixed(2)} ${yo1.toFixed(2)} L${xi1.toFixed(2)} ${yi1.toFixed(2)} A${r} ${r} 0 ${big} 0 ${xi0.toFixed(2)} ${yi0.toFixed(2)} Z" fill="${s.color}"><title>${esc(s.label)}: ${n(s.value)} (${(frac * 100).toFixed(1)}%)</title></path>`;
        a0 = a1;
      });
    }
    const ctr = center != null
      ? `<text x="${cx}" y="${cy - 2}" text-anchor="middle" font-size="21" font-weight="800" fill="var(--text-strong)">${center}</text>` +
        (centerSub ? `<text x="${cx}" y="${cy + 15}" text-anchor="middle" font-size="11" fill="var(--text-muted)">${esc(centerSub)}</text>` : "")
      : "";
    return `<svg viewBox="0 0 180 180" width="164" height="164" class="donut" role="img" aria-label="${esc(centerSub || "비율")}">${paths}${ctr}</svg>`;
  }

  function legend(segments, total) {
    return `<div class="chart-legend">` + segments.filter((s) => num(s.value) > 0).map((s) =>
      `<div class="lg"><span class="dot" style="background:${s.color}"></span><span class="lg-t">${esc(s.label)}</span>` +
      `<b>${n(s.value)}</b>${total ? ` <span class="muted">${(num(s.value) / total * 100).toFixed(1)}%</span>` : ""}</div>`).join("") + `</div>`;
  }

  // ── 입고일별 양품/불량 추이(막대) — 이전 납품 대비 수치 차이 시각화 ──
  function trendBars() {
    const map = new Map();
    (data.by_lot || []).forEach((b) => {
      const d = b.receipt_date || "?";
      const m = map.get(d) || { good: 0, def: 0 };
      m.good += num(b.inc_good); m.def += num(b.inc_defect); map.set(d, m);
    });
    const arr = [...map.entries()].sort((a, b) => (a[0] < b[0] ? -1 : 1)); // 오래된→최신
    if (!arr.length) return '<div class="muted">추이를 표시할 데이터가 없습니다.</div>';
    const maxT = Math.max(...arr.map(([, m]) => m.good + m.def), 1);
    const bw = 44, gap = 30, padT = 22, padB = 46, plot = 168;
    const H = padT + plot + padB, W = Math.max(340, gap + arr.length * (bw + gap));
    let bars = "";
    arr.forEach(([d, m], i) => {
      const t = m.good + m.def, x = gap + i * (bw + gap);
      const h = plot * t / maxT, y = padT + plot - h;
      const gh = h * (t ? m.good / t : 0), dh = h - gh;
      const rate = t ? m.def / t * 100 : 0;
      bars += `<g>
        <rect x="${x}" y="${y.toFixed(1)}" width="${bw}" height="${gh.toFixed(1)}" fill="${GOOD}" rx="2"><title>${esc(d)} 양품 ${n(m.good)}</title></rect>
        <rect x="${x}" y="${(y + gh).toFixed(1)}" width="${bw}" height="${dh.toFixed(1)}" fill="${BAD}" rx="2"><title>${esc(d)} 불량 ${n(m.def)}</title></rect>
        <text x="${x + bw / 2}" y="${(y - 6).toFixed(1)}" text-anchor="middle" font-size="11" font-weight="700" fill="${BAD}">${rate.toFixed(0)}%</text>
        <text x="${x + bw / 2}" y="${H - 26}" text-anchor="middle" font-size="10.5" fill="var(--text-secondary)">${esc((d || "").slice(5) || d)}</text>
        <text x="${x + bw / 2}" y="${H - 11}" text-anchor="middle" font-size="10" fill="var(--text-muted)">${n(t)}</text>
      </g>`;
    });
    return `<div class="chart-scroll"><svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="입고일별 추이">${bars}</svg></div>`;
  }

  function statCard(k, v, tone) {
    return `<div class="stat-card ${tone || ""}"><div class="sk">${esc(k)}</div><div class="sv">${v}</div></div>`;
  }

  // ── 표 ─────────────────────────────────────────────────────
  function lotTable() {
    const rows = (data.by_lot || []).map((b) => {
      const y = num(b["yield"]);
      return `<tr><td>${esc(b.receipt_date || "")}</td>
        <td>${esc(b.item_code || (b.prism_type + " " + (b.model || "")))}</td><td>${esc(b.supplier_name)}</td>
        <td class="right">${n(b.lot_qty)}</td><td class="right good-t">${n(b.inc_good)}</td>
        <td class="right bad-t">${n(b.inc_defect)} <span class="muted">(${pct(b.inc_rate)})</span></td>
        <td class="right">${b.final_good == null ? "—" : n(b.final_good)}</td>
        <td><div class="ybar-wrap"><div class="ybar"><span style="width:${Math.max(0, Math.min(100, y))}%"></span></div><em>${pct(b["yield"])}</em></div></td>
        <td><button class="mini" data-act="dl" data-lot="${b.lot_id}" data-label="${esc(b.lot_label || b.lot_no)}">엑셀</button></td></tr>`;
    }).join("");
    return `<div class="tbl-scroll"><table class="tbl"><thead><tr><th>입고일</th><th>프리즘</th><th>공급사</th>
      <th class="right">로트수량</th><th class="right">입고양품</th><th class="right">입고불량(률)</th>
      <th class="right">최종양품</th><th>수율</th><th>건별</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="9" class="muted">검사된 로트 없음</td></tr>'}</tbody></table></div>`;
  }

  function supplierTable() {
    const rows = (data.by_supplier || []).map((b) =>
      `<tr><td>${esc(b.supplier_name)}</td><td class="right">${n(b.received)}</td>
        <td class="right good-t">${n(b.good)}</td><td class="right bad-t">${n(b.defect)}</td><td class="right">${pct(b.defect_rate)}</td></tr>`).join("");
    return `<table class="tbl"><thead><tr><th>공급사</th><th class="right">입고수량</th><th class="right">양품</th><th class="right">불량</th><th class="right">불량률</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="5" class="muted">없음</td></tr>'}</tbody></table>`;
  }

  function itemTable() {
    const rows = (data.by_item || []).map((b) =>
      `<tr><td>${esc(b.name)}</td><td class="right bad-t">${n(b.inc_defect)} <span class="muted">(${pct(b.inc_rate)})</span></td>
        <td class="right">${n(b.post_defect)} <span class="muted">(${pct(b.post_rate)})</span></td></tr>`).join("");
    return `<table class="tbl"><thead><tr><th>검사항목</th><th class="right">입고검사 불량(률)</th><th class="right">페인트후 불량(률)</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="3" class="muted">없음</td></tr>'}</tbody></table>`;
  }

  // ── 렌더(데이터 캐시 기반, 테마 전환 시 재사용) ────────────
  function render() {
    if (!data) return;
    const bl = data.by_lot || [];
    const totGood = bl.reduce((s, b) => s + num(b.inc_good), 0);
    const totDef = bl.reduce((s, b) => s + num(b.inc_defect), 0);
    const totInsp = num(data.totals && data.totals.inc_inspected) || (totGood + totDef);
    // 총 입고수량: 전체 receipt 합(공급사별표와 정합). 없으면 검사로트 합으로 대체.
    const totRecv = (data.totals && data.totals.received_total != null)
      ? num(data.totals.received_total) : bl.reduce((s, b) => s + num(b.lot_qty), 0);
    const goodRate = totInsp ? totGood / totInsp * 100 : 0;
    const defRate = totInsp ? totDef / totInsp * 100 : 0;
    const lotCount = data.totals ? data.totals.lot_count : bl.length;

    const gbSeg = [{ label: "양품", value: totGood, color: GOOD }, { label: "불량", value: totDef, color: BAD }];

    const defItems = (data.by_item || []).filter((b) => num(b.inc_defect) > 0)
      .sort((a, b) => num(b.inc_defect) - num(a.inc_defect));
    const dseg = defItems.slice(0, 8).map((b, i) => ({ label: b.name, value: num(b.inc_defect), color: PAL[i % PAL.length] }));
    const rest = defItems.slice(8).reduce((s, b) => s + num(b.inc_defect), 0);
    if (rest > 0) dseg.push({ label: "기타", value: rest, color: "#94a3b8" });

    el("report-root").innerHTML = `
      <div class="report-toolbar">
        ${productSelect()}
        <button class="btn primary" id="rep-excel">${curProduct ? "이 품목 집계 엑셀" : "전체 집계 엑셀"} 다운로드</button>
        <span class="muted">${curProduct ? "선택 품목 " + esc(curProduct) + " · " : ""}검사 로트 ${lotCount}건 · 검사수량 ${n(totInsp)}</span>
      </div>

      <div class="stat-row">
        ${statCard("총 입고수량", n(totRecv))}
        ${statCard("총 검사수량", n(totInsp))}
        ${statCard("총 양품", n(totGood), "good")}
        ${statCard("총 불량", n(totDef), "bad")}
        ${statCard("평균 불량률", defRate.toFixed(1) + "%", "bad")}
        ${statCard("검사 로트", lotCount + "건")}
      </div>

      <div class="grid2" style="margin-top:16px">
        <div class="card-surface chart-card"><h4>양품 · 불량 비율</h4>
          <div class="chart-flex">${donut(gbSeg, goodRate.toFixed(1) + "%", "양품률")}${legend(gbSeg, totGood + totDef)}</div>
        </div>
        <div class="card-surface chart-card"><h4>검사항목별 불량 구성</h4>
          <div class="chart-flex">${donut(dseg, n(totDef), "총 불량")}${legend(dseg, totDef)}</div>
        </div>
      </div>

      <div class="card-surface" style="margin-top:16px">
        <h4>입고일별 양품 · 불량 추이 <span class="muted" style="font-weight:400;font-size:12px">이전 납품 대비 한눈에</span></h4>
        <div class="chart-hint"><span class="dot" style="background:${GOOD}"></span>양품<span class="dot" style="background:${BAD};margin-left:10px"></span>불량 · 막대 위 %는 불량률</div>
        ${trendBars()}
      </div>

      <div class="card-surface" style="margin-top:16px"><h4>로트별 집계 <span class="muted" style="font-weight:400;font-size:12px">건별 엑셀 다운로드</span></h4>${lotTable()}</div>

      <div class="grid2" style="margin-top:16px">
        <div class="card-surface"><h4>공급사별</h4>${supplierTable()}</div>
        <div class="card-surface"><h4>검사항목별 불량률 <span class="muted" style="font-weight:400;font-size:12px">단계 분리</span></h4>${itemTable()}</div>
      </div>`;
  }

  async function show() {
    const qs = curProduct ? "?product=" + encodeURIComponent(curProduct) : "";
    const my = ++reqSeq;   // 마지막 요청만 반영(빠른 연속 선택 경쟁 방지)
    try {
      const res = await get("/api/report/summary" + qs);
      if (my !== reqSeq) return;
      data = res;
    } catch (e) {
      if (my !== reqSeq) return;
      if (App.toast) App.toast("집계를 불러오지 못했습니다.", "err");
      curProduct = (data && data.product) || "";   // 셀렉트를 실제 표시중 품목으로 롤백
    }
    render();
    bindOnce();
  }

  function productSelect() {
    const opts = (data.products || []).map((p) => {
      const label = esc(p.item_code) + (p.prism_type ? ` · ${esc(p.prism_type)} ${esc(p.model || "")}`.trimEnd() : "") + ` (${p.lots}로트)`;
      return `<option value="${esc(p.item_code)}" ${p.item_code === curProduct ? "selected" : ""}>${label}</option>`;
    }).join("");
    return `<label class="rep-filter">품목
      <select id="rep-product"><option value="" ${curProduct ? "" : "selected"}>전체 품목</option>${opts}</select>
    </label>`;
  }

  // 테마 전환 시 차트/표 색 즉시 반영(데이터 재조회 없이)
  function onThemeChange() {
    const p = document.querySelector('.panel[data-panel="report"]');
    if (data && p && p.classList.contains("active")) render();
  }

  function bindOnce() {
    if (bound) return; bound = true;
    const root = el("report-root");
    root.addEventListener("click", (e) => {
      if (e.target.id === "rep-excel") {
        return dl("/api/report/excel" + (curProduct ? "?product=" + encodeURIComponent(curProduct) : ""));
      }
      const b = e.target.closest('[data-act="dl"]');
      if (b) dl("/api/report/lot-excel?lot_id=" + b.dataset.lot + "&label=" + encodeURIComponent(b.dataset.label || ""));
    });
    root.addEventListener("change", (e) => {
      if (e.target.id === "rep-product") { curProduct = e.target.value; show(); }
    });
  }

  return { show, render, onThemeChange };
})();
