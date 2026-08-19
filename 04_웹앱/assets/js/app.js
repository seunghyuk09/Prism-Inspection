// 메인 셸 — 2단계 메뉴(카테고리 → 하위메뉴) 엔진 + 대시보드. (공용 App 사용)
"use strict";

const { get: apiGet, el, esc } = App;

// ── 메뉴/패널 설정(한 곳에서 관리) ───────────────────────────
// 기능을 추가하면 여기 한 줄만 늘리면 카테고리바·하위메뉴·홈카드에 자동 반영.
const NAV = [
  { cat: "대시보드", panel: "dashboard" },
  { cat: "기준정보", items: [
      { label: "프리즘마스터", panel: "masters", sub: "prism" },
      { label: "공급사", panel: "masters", sub: "supplier" },
      { label: "검사항목", panel: "masters", sub: "item" },
      { label: "제품마스터", panel: "masters", sub: "product" },
  ] },
  { cat: "입고 · 로트", panel: "receipt" },
  { cat: "입고이력", panel: "inbound_history" },
  { cat: "검사 · 페인트", items: [
      { label: "입고검사", panel: "inspection_in" },
      { label: "페인트 발송·회수", panel: "paint" },
      { label: "페인트후검사", panel: "inspection_post" },
  ] },
  { cat: "소비 · 잔량", items: [
      { label: "구매계획 임포트", panel: "plan" },
      { label: "잔량 현황", panel: "stock" },
  ] },
  { cat: "집계 · 관리", items: [
      { label: "집계", panel: "report" },
      { label: "이력 로그", panel: "log" },
  ] },
];

// ── 패널 표시 + 패널별 모듈 호출 ────────────────────────────
function showPanel(name, sub) {
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("active", p.dataset.panel === name));
  if (name === "dashboard") loadDashboard();
  if (name === "masters" && window.Masters) window.Masters.show(sub || "prism");
  if (name === "receipt" && window.Receipt) window.Receipt.show();
  if (name === "inbound_history" && window.InboundHistory) window.InboundHistory.show();
  if (name === "inspection_in" && window.Inspection) window.Inspection.showStage("INCOMING");
  if (name === "paint" && window.Inspection) window.Inspection.showStage("PAINT");
  if (name === "inspection_post" && window.Inspection) window.Inspection.showStage("POST_PAINT");
  if (name === "plan" && window.Plan) window.Plan.show();
  if (name === "stock" && window.Stock) window.Stock.show();
  if (name === "report" && window.Report) window.Report.show();
  if (name === "users" && window.UsersAdmin) window.UsersAdmin.show();
}

// 하위메뉴 렌더 + 항목 선택
function renderSubnav(catIdx) {
  const entry = NAV[catIdx];
  const bar = el("subnav");
  if (!entry.items) { bar.innerHTML = ""; return; }
  bar.innerHTML = entry.items.map((it, i) =>
    `<button class="menu-subnav-button ${i === 0 ? "active" : ""}" data-cat="${catIdx}" data-item="${i}">${esc(it.label)}</button>`).join("");
}

function selectCategory(catIdx) {
  document.querySelectorAll(".menu-category-button").forEach((b, i) => b.classList.toggle("active", i === catIdx));
  const entry = NAV[catIdx];
  if (entry.panel) { el("subnav").innerHTML = ""; showPanel(entry.panel); return; }
  renderSubnav(catIdx);
  selectItem(catIdx, 0);
}

function selectItem(catIdx, itemIdx) {
  const it = NAV[catIdx].items[itemIdx];
  el("subnav").querySelectorAll(".menu-subnav-button").forEach((b, i) => b.classList.toggle("active", i === itemIdx));
  showPanel(it.panel, it.sub);
}

// 카테고리바 + 홈카드 생성
function buildMenu() {
  el("category-bar").innerHTML = NAV.map((n, i) =>
    `<button class="menu-category-button ${i === 0 ? "active" : ""}" data-cat="${i}">${esc(n.cat)}</button>`).join("");
  el("category-bar").addEventListener("click", (e) => {
    const b = e.target.closest(".menu-category-button"); if (!b) return;
    selectCategory(Number(b.dataset.cat));
  });
  el("subnav").addEventListener("click", (e) => {
    const b = e.target.closest(".menu-subnav-button"); if (!b) return;
    selectItem(Number(b.dataset.cat), Number(b.dataset.item));
  });

  // 홈 바로가기 카드(카테고리별)
  const cats = NAV.filter((n) => n.items);
  el("home-cats").innerHTML = cats.map((n) => {
    const ci = NAV.indexOf(n);
    const btns = n.items.map((it, ii) =>
      `<button class="menu-subnav-button" data-cat="${ci}" data-item="${ii}">${esc(it.label)}</button>`).join("");
    return `<div class="category-card"><div class="category-card-title">${esc(n.cat)}</div><div class="category-card-actions">${btns}</div></div>`;
  }).join("");
  el("home-cats").addEventListener("click", (e) => {
    const b = e.target.closest(".menu-subnav-button"); if (!b) return;
    const ci = Number(b.dataset.cat);
    selectCategory(ci);
    selectItem(ci, Number(b.dataset.item));
  });
}

// ── 대시보드 ───────────────────────────────────────────────
async function loadDashboard() {
  try {
    const st = await apiGet("/api/status");
    el("env-info").textContent = `포트 ${st.port} · DB ${st.db_exists ? "정상" : "없음"} · ${st.time}`;
    el("foot").textContent = `${st.app} · 로컬 전용 · DB: ${st.db_path}`;
  } catch (e) { el("env-info").textContent = "서버 연결 실패"; }

  try {
    const h = await apiGet("/api/health");
    const c = h.counts || {};
    const cards = [
      ["프리즘 종류", c.prism_master], ["공급사", c.supplier], ["검사항목", c.inspection_item],
      ["제품마스터", c.product], ["입고", c.receipt], ["로트", c.lot],
      ["검사", c.inspection], ["소비기록", c.consumption],
    ];
    el("dash-cards").innerHTML = cards.map(
      ([k, v]) => `<div class="dash-card"><div class="k">${k}</div><div class="v">${v ?? "—"}</div></div>`).join("");
  } catch (e) { el("dash-cards").innerHTML = '<div class="muted">건수 로드 실패</div>'; }
}

// ── 로그인 사용자 메뉴(드롭다운) + 개인설정 모달 ─────────────
const openModal = (id) => { el(id).hidden = false; };
const closeModal = (id) => { el(id).hidden = true; };

async function initAuth() {
  let user = null;
  try { const me = await apiGet("/api/auth/me"); if (me.ok) user = me.user; } catch (e) { /* common.js 가 401 시 로그인으로 보냄 */ }
  if (user) {
    const roleKo = { admin: "관리자", manager: "담당자", user: "사용자" }[user.role] || "사용자";
    el("u-name").textContent = user.name || user.id;
    el("u-role").textContent = roleKo;
    el("um-name").textContent = user.name || user.id;
    el("um-id").textContent = user.id;
    el("um-role").textContent = roleKo;
    if (user.role === "admin") document.querySelectorAll(".admin-only").forEach((x) => { x.hidden = false; });
  }

  // 드롭다운 토글 + 바깥 클릭 시 닫기
  const btn = el("user-info-btn"), menu = el("user-menu");
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    const willOpen = menu.hidden;
    menu.hidden = !willOpen;
    btn.setAttribute("aria-expanded", String(willOpen));
  });
  document.addEventListener("click", () => { menu.hidden = true; btn.setAttribute("aria-expanded", "false"); });
  menu.addEventListener("click", (e) => e.stopPropagation());

  // 메뉴 항목
  menu.addEventListener("click", async (e) => {
    const it = e.target.closest("[data-act]"); if (!it) return;
    menu.hidden = true;
    const act = it.dataset.act;
    if (act === "logout") { try { await App.post("/api/auth/logout", {}); } catch (err) {} location.href = "/login.html"; }
    else if (act === "changepw") { el("pw-msg").textContent = ""; el("form-pw").reset(); openModal("modal-pw"); }
    else if (act === "changeid") { el("id-msg").textContent = ""; el("form-id").reset(); openModal("modal-id"); }
    else if (act === "users") {   // 관리자: 사용자 관리 패널로
      document.querySelectorAll(".menu-category-button").forEach((b) => b.classList.remove("active"));
      el("subnav").innerHTML = "";
      showPanel("users");
    }
  });

  // 모달 닫기(취소/배경)
  document.querySelectorAll(".modal-bg").forEach((bg) => {
    bg.addEventListener("click", (e) => { if (e.target === bg) bg.hidden = true; });
    bg.querySelectorAll("[data-close]").forEach((b) => b.addEventListener("click", () => { bg.hidden = true; }));
  });

  // 비밀번호 변경
  el("form-pw").addEventListener("submit", async (e) => {
    e.preventDefault();
    const cur = el("pw-cur").value, nw = el("pw-new").value, nw2 = el("pw-new2").value;
    if (nw !== nw2) { el("pw-msg").textContent = "새 비밀번호가 일치하지 않습니다."; return; }
    const r = await App.post("/api/auth/changepw", { current_password: cur, new_password: nw });
    if (r.ok) { closeModal("modal-pw"); App.toast("비밀번호가 변경되었습니다.", "ok"); }
    else el("pw-msg").textContent = r.error || "실패했습니다.";
  });

  // ID 변경 (성공 시 재로그인)
  el("form-id").addEventListener("submit", async (e) => {
    e.preventDefault();
    const r = await App.post("/api/auth/changeid", { new_id: el("id-new").value, current_password: el("id-cur").value });
    if (r.ok) { App.toast("ID가 변경되었습니다. 다시 로그인하세요.", "ok"); setTimeout(() => { location.href = "/login.html"; }, 900); }
    else el("id-msg").textContent = r.error || "실패했습니다.";
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  await initAuth();
  buildMenu();
  loadDashboard();
});
