# -*- coding: utf-8 -*-
"""공급사(supplier) 서비스 — 목록/등록/수정.

규칙은 rules.py 를 빌려 쓴다(여기서 직접 만들지 않음).
is_active 는 status 에서 파생되는 생성컬럼이라 따로 쓰지 않는다.
"""
from __future__ import annotations

import db
import rules


def list_all() -> list[dict]:
    """공급사 전체 목록."""
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT id,name,status,is_active,note FROM supplier ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create(data: dict) -> dict:
    """공급사 등록."""
    name = (data.get("name") or "").strip()
    status = (data.get("status") or "ACTIVE").strip()
    note = (data.get("note") or "").strip()

    valid, reason = rules.validate_supplier(name, status)
    if not valid:
        return {"ok": False, "error": reason}

    conn = db.connect()
    try:
        ts = db.now_str()
        conn.execute(
            "INSERT INTO supplier(name,status,note,created_at,updated_at) VALUES (?,?,?,?,?)",
            (name, status, note, ts, ts))
        conn.commit()
        return {"ok": True}
    except db.sqlite3.IntegrityError:
        return {"ok": False, "error": f"이미 있는 공급사입니다: {name}"}
    finally:
        conn.close()


def update(data: dict) -> dict:
    """공급사 수정(이름/상태/비고)."""
    sid = data.get("id")
    name = (data.get("name") or "").strip()
    status = (data.get("status") or "").strip()
    note = (data.get("note") or "").strip()

    valid, reason = rules.validate_supplier(name, status)
    if not valid:
        return {"ok": False, "error": reason}

    conn = db.connect()
    try:
        cur = conn.execute(
            "UPDATE supplier SET name=?,status=?,note=?,updated_at=? WHERE id=?",
            (name, status, note, db.now_str(), sid))
        conn.commit()
        if cur.rowcount == 0:
            return {"ok": False, "error": "대상 공급사를 찾을 수 없습니다."}
        return {"ok": True}
    except db.sqlite3.IntegrityError:
        return {"ok": False, "error": f"이미 있는 공급사명입니다: {name}"}
    finally:
        conn.close()
