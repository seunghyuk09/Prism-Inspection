// 공용 헬퍼 — 모든 기능 JS 가 함께 쓰는 도구 모음(window.App 네임스페이스).
"use strict";

window.App = (function () {
  // 세션 만료(401) → 로그인 페이지로
  function _checkAuth(res) {
    if (res.status === 401 && location.pathname !== "/login.html") {
      location.href = "/login.html";
      throw new Error("unauthorized");
    }
    return res;
  }

  // ── API ────────────────────────────────────────────────
  async function get(path) {
    const res = _checkAuth(await fetch(path, { headers: { Accept: "application/json" } }));
    return res.json();
  }
  async function post(path, body) {
    const res = _checkAuth(await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    }));
    return res.json();
  }

  // ── DOM ────────────────────────────────────────────────
  function el(id) { return document.getElementById(id); }
  function esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // 간단 알림(우하단 토스트)
  function toast(msg, kind) {
    let box = el("app-toast");
    if (!box) {
      box = document.createElement("div");
      box.id = "app-toast";
      document.body.appendChild(box);
    }
    box.textContent = msg;
    box.className = "show " + (kind || "");
    clearTimeout(toast._t);
    toast._t = setTimeout(() => { box.className = ""; }, 2600);
  }

  return { get, post, el, esc, toast };
})();
