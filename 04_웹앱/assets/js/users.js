// 사용자 관리 (window.UsersAdmin) — 관리자 전용. 추가/수정/비번재설정/삭제, 3단계 역할.
"use strict";

window.UsersAdmin = (function () {
  const { get, post, el, esc, toast } = App;
  let users = [], editingId = null, bound = false;

  const ROLE_LABEL = { admin: "관리자", manager: "담당자", user: "사용자" };
  const roleLabel = (r) => ROLE_LABEL[r] || r;

  function form() {
    const opts = [["user", "사용자 (조회 전용)"], ["manager", "담당자 (사용자관리 외 전체)"], ["admin", "관리자 (전체)"]]
      .map(([v, t]) => `<option value="${v}">${t}</option>`).join("");
    return `<form class="m-form" id="user-form">
      <h4 style="margin:0" id="user-form-title">계정 추가</h4>
      <input type="hidden" id="u-editing" value="" />
      <label class="field"><span>아이디</span><input type="text" id="u-id" /></label>
      <label class="field"><span>이름</span><input type="text" id="u-name" /></label>
      <label class="field"><span id="u-pw-label">비밀번호</span><input type="text" id="u-pw" placeholder="" /></label>
      <label class="field"><span>역할</span><select id="u-role">${opts}</select></label>
      <div class="form-actions">
        <button class="btn primary" type="submit" id="u-submit">계정 추가</button>
        <button class="btn" type="button" data-act="reset">초기화</button>
      </div>
    </form>`;
  }
  function table() {
    const rows = users.map((u) =>
      `<tr><td>${esc(u.id)}</td><td>${esc(u.name || "")}</td><td>${roleLabel(u.role)}</td>
        <td><button class="mini" data-act="edit" data-id="${esc(u.id)}">수정</button>
            <button class="mini danger" data-act="del" data-id="${esc(u.id)}">삭제</button></td></tr>`).join("");
    return `<table class="tbl"><thead><tr><th>아이디</th><th>이름</th><th>역할</th><th>관리</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="4" class="muted">없음</td></tr>'}</tbody></table>`;
  }

  function setAddMode() {
    editingId = null;
    el("user-form-title").textContent = "계정 추가";
    el("u-submit").textContent = "계정 추가";
    el("u-editing").value = "";
    el("u-id").value = ""; el("u-id").disabled = false;
    el("u-name").value = ""; el("u-pw").value = ""; el("u-pw").placeholder = "";
    el("u-pw-label").textContent = "비밀번호";
    el("u-role").value = "user";
  }
  function setEditMode(u) {
    editingId = u.id;
    el("user-form-title").textContent = `계정 수정 — ${u.id}`;
    el("u-submit").textContent = "수정 저장";
    el("u-editing").value = u.id;
    el("u-id").value = u.id; el("u-id").disabled = true;
    el("u-name").value = u.name || "";
    el("u-pw").value = ""; el("u-pw").placeholder = "비우면 유지 · 입력하면 재설정";
    el("u-pw-label").textContent = "비밀번호 (선택)";
    el("u-role").value = u.role;
  }

  async function refresh() {
    const r = await get("/api/auth/users");
    if (!r.ok) { el("users-root").innerHTML = `<div class="muted">${esc(r.error || "권한 없음")}</div>`; return; }
    users = r.items || [];
    el("users-root").innerHTML = `<div class="m-grid"><div class="card-surface">${form()}</div>` +
      `<div class="card-surface">${table()}</div></div>`;
    setAddMode();
    bindOnce();
  }

  async function submitForm() {
    const id = el("u-id").value.trim(), name = el("u-name").value, pw = el("u-pw").value, role = el("u-role").value;
    if (editingId) {
      const r = await post("/api/auth/users/update", { id: editingId, name, role });
      if (!r.ok) { toast(r.error || "실패", "warn"); return; }
      if (pw) {
        const rp = await post("/api/auth/users/reset-pw", { id: editingId, password: pw });
        if (!rp.ok) { toast(rp.error || "비번 재설정 실패", "warn"); return; }
      }
      toast("수정되었습니다.", "ok"); await refresh();
    } else {
      const r = await post("/api/auth/users/add", { id, name, password: pw, role });
      if (r.ok) { toast("계정 추가됨", "ok"); await refresh(); } else toast(r.error || "실패", "warn");
    }
  }

  function bindOnce() {
    if (bound) return; bound = true;
    const root = el("users-root");
    root.addEventListener("submit", (e) => { if (e.target.id === "user-form") { e.preventDefault(); submitForm(); } });
    root.addEventListener("click", async (e) => {
      const b = e.target.closest("[data-act]"); if (!b) return;
      const act = b.dataset.act;
      if (act === "reset") return setAddMode();
      if (act === "edit") { const u = users.find((x) => x.id === b.dataset.id); if (u) { setEditMode(u); el("users-root").scrollIntoView({ behavior: "smooth", block: "start" }); } return; }
      if (act === "del") {
        if (!confirm(`계정 '${b.dataset.id}' 을(를) 삭제할까요?`)) return;
        const r = await post("/api/auth/users/remove", { id: b.dataset.id });
        if (r.ok) { toast("삭제됨", "ok"); await refresh(); } else toast(r.error || "실패", "warn");
      }
    });
  }

  async function show() { await refresh(); }
  return { show };
})();
