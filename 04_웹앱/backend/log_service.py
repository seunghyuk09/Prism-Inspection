# -*- coding: utf-8 -*-
"""이력 로그(activity_log) 조회 — 최근순. (기록은 local_server.log_activity 가 함)"""
from __future__ import annotations

import db


def list_logs(data=None) -> list[dict]:
    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT id, ts, category, action, target, detail, operator "
            "FROM activity_log ORDER BY id DESC LIMIT 500").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
