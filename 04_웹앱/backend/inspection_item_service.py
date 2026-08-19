# -*- coding: utf-8 -*-
"""검사항목(inspection_item) 서비스 — 목록/등록/수정/사용여부.

확장형의 핵심: 새 불량유형은 여기에 '행 추가'만 하면 검사 입력·집계·성적서에 자동 반영.
단계 적용(applies_to_incoming / applies_to_post_paint)은 boolean.
"""
from __future__ import annotations

import db
import rules


def list_all() -> list[dict]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT id,name,category,applies_to_incoming,applies_to_post_paint,sort_order,is_active "
            "FROM inspection_item ORDER BY sort_order,id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def _next_sort_order(conn) -> int:
    row = conn.execute("SELECT COALESCE(MAX(sort_order),0)+1 AS n FROM inspection_item").fetchone()
    return row["n"]


def create(data: dict) -> dict:
    name = (data.get("name") or "").strip()
    category = (data.get("category") or "").strip()
    inc = 1 if data.get("applies_to_incoming") else 0
    post = 1 if data.get("applies_to_post_paint") else 0

    valid, reason = rules.validate_inspection_item(name, inc, post)
    if not valid:
        return {"ok": False, "error": reason}

    conn = db.connect()
    try:
        ts = db.now_str()
        # 정렬순서를 지정 안 하면 맨 뒤로
        order = data.get("sort_order")
        order = int(order) if str(order or "").strip().isdigit() else _next_sort_order(conn)
        conn.execute(
            "INSERT INTO inspection_item"
            "(name,category,applies_to_incoming,applies_to_post_paint,sort_order,is_active,created_at,updated_at) "
            "VALUES (?,?,?,?,?,1,?,?)", (name, category, inc, post, order, ts, ts))
        conn.commit()
        return {"ok": True}
    except db.sqlite3.IntegrityError:
        return {"ok": False, "error": f"이미 있는 검사항목입니다: {name}"}
    finally:
        conn.close()


def update(data: dict) -> dict:
    iid = data.get("id")
    name = (data.get("name") or "").strip()
    category = (data.get("category") or "").strip()
    inc = 1 if data.get("applies_to_incoming") else 0
    post = 1 if data.get("applies_to_post_paint") else 0
    order = data.get("sort_order")

    valid, reason = rules.validate_inspection_item(name, inc, post)
    if not valid:
        return {"ok": False, "error": reason}

    conn = db.connect()
    try:
        order = int(order) if str(order or "").strip().isdigit() else 0
        cur = conn.execute(
            "UPDATE inspection_item SET name=?,category=?,applies_to_incoming=?,applies_to_post_paint=?,"
            "sort_order=?,updated_at=? WHERE id=?",
            (name, category, inc, post, order, db.now_str(), iid))
        conn.commit()
        if cur.rowcount == 0:
            return {"ok": False, "error": "대상 검사항목을 찾을 수 없습니다."}
        return {"ok": True}
    except db.sqlite3.IntegrityError:
        return {"ok": False, "error": f"이미 있는 검사항목입니다: {name}"}
    finally:
        conn.close()


def set_active(data: dict) -> dict:
    iid = data.get("id")
    is_active = 1 if data.get("is_active") else 0
    conn = db.connect()
    try:
        cur = conn.execute(
            "UPDATE inspection_item SET is_active=?,updated_at=? WHERE id=?",
            (is_active, db.now_str(), iid))
        conn.commit()
        if cur.rowcount == 0:
            return {"ok": False, "error": "대상 검사항목을 찾을 수 없습니다."}
        return {"ok": True}
    finally:
        conn.close()
