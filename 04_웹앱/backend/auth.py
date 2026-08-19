# -*- coding: utf-8 -*-
"""사용자 인증 — 세션 토큰(쿠키) 기반. (입출고시스템 인증 방식 이식)

저장: 00_설정/사용자목록.json  (pw_hash = sha256(id:password), 평문 저장 금지)
세션: 메모리(서버 재시작 시 모두 만료). 외부(Cloudflare Tunnel) 노출 시 로그인 게이트.
역할: admin(사용자 관리 가능) / user(업무만).
"""
from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from pathlib import Path

# 역할 3단계 (값은 영어, 화면 표기는 한글: admin=관리자 / manager=담당자 / user=사용자)
#   admin   : 모든 기능 + 사용자 관리
#   manager : 사용자 관리만 제외, 나머지(업무 전체)는 관리자와 동일
#   user    : 조회 전용(읽기만)
ROLES = ("admin", "manager", "user")
ROLE_LABELS = {"admin": "관리자", "manager": "담당자", "user": "사용자"}

# 최초 1회 시드되는 기본 관리자 — 첫 로그인 후 반드시 비밀번호 변경할 것
DEFAULT_ADMIN_ID = "admin"
DEFAULT_ADMIN_PW = "secugen"


def _norm_role(v) -> str:
    v = (v or "").strip()
    return v if v in ROLES else "user"


def hash_password(uid: str, password: str) -> str:
    """sha256(id:password) — id 를 솔트로. 입출고시스템과 동일한 방식."""
    d = hashlib.sha256(uid.encode("utf-8") + b":" + password.encode("utf-8")).hexdigest()
    return "sha256:" + d


class UserStore:
    """사용자 목록 로드/저장 + 검증 + 관리."""

    def __init__(self, path: Path):
        self._path = path
        self._users: dict[str, dict] = {}
        self._lock = threading.RLock()
        self.reload()
        if not self._users:
            self._seed_default_admin()

    def reload(self) -> None:
        with self._lock:
            self._users.clear()
            if not self._path.exists():
                return
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return
            for u in data.get("users", []):
                uid = (u.get("id") or "").strip()
                if not uid:
                    continue
                self._users[uid] = {
                    "id": uid, "name": u.get("name") or "",
                    "pw_hash": u.get("pw_hash") or "", "role": _norm_role(u.get("role")),
                }

    def _save(self) -> None:
        with self._lock:
            data = {
                "_note": "pw_hash = sha256(id:password). 평문 저장 금지.",
                "users": [{"id": u["id"], "name": u["name"], "pw_hash": u["pw_hash"], "role": u["role"]}
                          for u in self._users.values()],
            }
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _seed_default_admin(self) -> None:
        with self._lock:
            self._users[DEFAULT_ADMIN_ID] = {
                "id": DEFAULT_ADMIN_ID, "name": "관리자",
                "pw_hash": hash_password(DEFAULT_ADMIN_ID, DEFAULT_ADMIN_PW), "role": "admin",
            }
            self._save()

    # ── 조회/검증 ─────────────────────────────────────────────
    def verify(self, uid: str, pw: str) -> bool:
        with self._lock:
            u = self._users.get(uid)
            return bool(u) and u["pw_hash"] == hash_password(uid, pw)

    def get(self, uid: str) -> dict | None:
        with self._lock:
            return dict(self._users[uid]) if uid in self._users else None

    def public(self, uid: str) -> dict | None:
        """비번해시 제외한 공개 정보."""
        u = self.get(uid)
        return {"id": u["id"], "name": u["name"], "role": u["role"]} if u else None

    def is_admin(self, uid: str) -> bool:
        u = self.get(uid)
        return bool(u) and u["role"] == "admin"

    def is_manager_or_above(self, uid: str) -> bool:
        """담당자 이상(관리자/담당자) — 업무 변경(쓰기) 권한 기준."""
        u = self.get(uid)
        return bool(u) and u["role"] in ("admin", "manager")

    def list_users(self) -> list[dict]:
        with self._lock:
            return [{"id": u["id"], "name": u["name"], "role": u["role"]} for u in self._users.values()]

    # ── 관리 ──────────────────────────────────────────────────
    def add(self, uid: str, name: str, pw: str, role: str = "user") -> tuple[bool, str]:
        uid = (uid or "").strip()
        if not uid:
            return (False, "아이디를 입력하세요.")
        if not pw:
            return (False, "비밀번호를 입력하세요.")
        with self._lock:
            if uid in self._users:
                return (False, f"이미 있는 아이디입니다: {uid}")
            self._users[uid] = {"id": uid, "name": (name or "").strip(),
                                "pw_hash": hash_password(uid, pw), "role": _norm_role(role)}
            self._save()
            return (True, "")

    def remove(self, uid: str) -> tuple[bool, str]:
        with self._lock:
            if uid not in self._users:
                return (False, "없는 아이디입니다.")
            if self._users[uid]["role"] == "admin":
                others = sum(1 for u in self._users.values() if u["role"] == "admin" and u["id"] != uid)
                if others == 0:
                    return (False, "마지막 관리자 계정은 삭제할 수 없습니다.")
            del self._users[uid]
            self._save()
            return (True, "")

    def change_password(self, uid: str, new_pw: str) -> tuple[bool, str]:
        if not new_pw:
            return (False, "새 비밀번호를 입력하세요.")
        with self._lock:
            if uid not in self._users:
                return (False, "없는 아이디입니다.")
            self._users[uid]["pw_hash"] = hash_password(uid, new_pw)
            self._save()
            return (True, "")

    def update_user(self, uid: str, name=None, role=None) -> tuple[bool, str]:
        """관리자가 사용자 정보(이름·역할) 수정. 마지막 관리자 강등은 차단."""
        with self._lock:
            if uid not in self._users:
                return (False, "없는 아이디입니다.")
            if role is not None:
                new_role = _norm_role(role)
                if self._users[uid]["role"] == "admin" and new_role != "admin":
                    others = sum(1 for u in self._users.values() if u["role"] == "admin" and u["id"] != uid)
                    if others == 0:
                        return (False, "마지막 관리자의 역할은 변경할 수 없습니다.")
                self._users[uid]["role"] = new_role
            if name is not None:
                self._users[uid]["name"] = name.strip()
            self._save()
            return (True, "")

    def change_id(self, old_id: str, new_id: str, current_pw: str) -> tuple[bool, str]:
        """본인 아이디 변경. 해시 솔트가 id 라 비번 재입력 필요 → 변경 후 재로그인."""
        new_id = (new_id or "").strip()
        if not new_id:
            return (False, "새 아이디를 입력하세요.")
        if old_id == new_id:
            return (False, "현재 아이디와 같습니다.")
        with self._lock:
            if old_id not in self._users:
                return (False, "없는 아이디입니다.")
            if new_id in self._users:
                return (False, f"이미 사용 중인 아이디입니다: {new_id}")
            if self._users[old_id]["pw_hash"] != hash_password(old_id, current_pw):
                return (False, "현재 비밀번호가 올바르지 않습니다.")
            u = self._users[old_id]
            self._users[new_id] = {"id": new_id, "name": u["name"],
                                   "pw_hash": hash_password(new_id, current_pw), "role": u["role"]}
            del self._users[old_id]
            self._save()
            return (True, "")


class SessionManager:
    """토큰 → 사용자ID (메모리). 서버 재시작 시 모두 만료."""

    TTL = 12 * 3600   # 12시간

    def __init__(self):
        self._sessions: dict[str, dict] = {}
        self._lock = threading.RLock()

    def issue(self, uid: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[token] = {"uid": uid, "exp": time.time() + self.TTL}
        return token

    def validate(self, token: str | None) -> str | None:
        if not token:
            return None
        with self._lock:
            s = self._sessions.get(token)
            if not s:
                return None
            if time.time() > s["exp"]:
                del self._sessions[token]
                return None
            return s["uid"]

    def revoke(self, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            self._sessions.pop(token, None)

    def revoke_user(self, uid: str) -> None:
        """특정 사용자의 모든 세션 만료(비번 변경 시)."""
        with self._lock:
            for t in [t for t, s in self._sessions.items() if s["uid"] == uid]:
                del self._sessions[t]
