# -*- coding: utf-8 -*-
"""Prism 검사·재고 관리 — 로컬 웹서버.

표준 라이브러리 http.server 만 사용(외부 의존성 없음).
Phase 0 범위: 정적 파일 서빙 + 상태/헬스 API + 기준정보 요약.
다음 단계에서 기준정보 CRUD / 입고·로트 / 검사 / 소비·잔량 라우트가 추가된다.

실행:  python local_server.py [PORT]   (기본 10000)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

# backend 디렉터리를 import 경로에 추가
BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import db  # noqa: E402  (경로 추가 후 import)
import supplier_service          # noqa: E402
import prism_service            # noqa: E402
import inspection_item_service  # noqa: E402
import product_service          # noqa: E402
import receipt_service          # noqa: E402
import inbound_history_service  # noqa: E402
import inspection_service       # noqa: E402
import paint_service            # noqa: E402
import stock_service            # noqa: E402
import plan_service             # noqa: E402
import paint_batch_service       # noqa: E402
import ledger_service            # noqa: E402
import log_service               # noqa: E402
import report_service           # noqa: E402
import auth                      # noqa: E402

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = ROOT / "04_웹앱"
DEFAULT_PORT = 10000

# ── 인증(로그인/세션) ────────────────────────────────────────
SESSION_COOKIE = "prism_sid"
USERS_JSON = ROOT / "00_설정" / "사용자목록.json"
user_store = auth.UserStore(USERS_JSON)
session_manager = auth.SessionManager()
# 로그인 없이 접근 가능: 로그인 페이지·로그인 API·정적 자원(로그인 화면 스타일용)
PUBLIC_PATHS = frozenset({"/login.html", "/api/auth/login"})

# ── GET 목록 라우트: path → 목록 함수 ────────────────────────
GET_LIST_ROUTES = {
    "/api/suppliers":        supplier_service.list_all,
    "/api/prisms":           prism_service.list_all,
    "/api/inspection-items": inspection_item_service.list_all,
    "/api/products":         product_service.list_all,
    "/api/receipts":         receipt_service.list_all,
    "/api/inspection/lots":  inspection_service.list_lots,
    "/api/plans":            plan_service.list_plans,
    "/api/painted-prisms":   paint_batch_service.painted_prisms,
    "/api/paint-batches":    paint_batch_service.list_batches,
    "/api/logs":             log_service.list_logs,
}

# ── POST 액션 라우트: path → (서비스함수, 분류, 동작) ─────────
# 분류/동작은 이력 로그(activity_log)용. 새 라우트는 여기 한 줄만 추가.
POST_ROUTES = {
    "/api/suppliers/create":        (supplier_service.create,        "공급사", "등록"),
    "/api/suppliers/update":        (supplier_service.update,        "공급사", "수정"),
    "/api/prisms/create":           (prism_service.create,           "프리즘", "등록"),
    "/api/prisms/update":           (prism_service.update,           "프리즘", "수정"),
    "/api/prisms/active":           (prism_service.set_active,       "프리즘", "사용여부"),
    "/api/inspection-items/create": (inspection_item_service.create, "검사항목", "등록"),
    "/api/inspection-items/update": (inspection_item_service.update, "검사항목", "수정"),
    "/api/inspection-items/active": (inspection_item_service.set_active, "검사항목", "사용여부"),
    "/api/products/create":         (product_service.create,         "제품마스터", "등록"),
    "/api/products/update":         (product_service.update,         "제품마스터", "수정"),
    "/api/products/active":         (product_service.set_active,     "제품마스터", "사용여부"),
    "/api/receipts/create":         (receipt_service.create,         "입고", "등록"),
    "/api/receipts/add-lot":        (receipt_service.add_lot,        "로트", "추가"),
    "/api/receipts/delete-lot":     (receipt_service.delete_lot,     "로트", "삭제"),
    "/api/inspection/save":         (inspection_service.save,        "검사", "저장"),
    "/api/paint/create":            (paint_service.create_job,       "페인트", "발송"),
    "/api/paint/return":            (paint_service.add_return,       "페인트", "회수"),
    "/api/paint/delete":            (paint_service.delete_job,       "페인트", "발송삭제"),
    "/api/stock/adjust":            (stock_service.add_adjustment,   "재고", "기초/보정"),
    "/api/plan/preview":            (plan_service.preview,           "구매계획", "미리보기"),
    "/api/plan/commit":             (plan_service.commit,            "구매계획", "확정"),
    "/api/plan/delete":             (plan_service.delete_plan,       "구매계획", "취소"),
    "/api/paint-batch/save":        (paint_batch_service.save,       "페인트후", "저장"),
    "/api/paint-batch/delete":      (paint_batch_service.delete,     "페인트후", "삭제"),
    "/api/paint-batch/preview":     (paint_batch_service.preview_excel, "페인트후", "미리보기"),
    "/api/paint-batch/commit":      (paint_batch_service.commit_excel,  "페인트후", "업로드"),
    "/api/ledger/preview":          (ledger_service.preview,         "수불부", "미리보기"),
    "/api/ledger/commit":           (ledger_service.commit,          "수불부", "확정"),
}


# 기준정보(마스터) 편집은 관리자 전용 — 담당자(manager)는 운영 데이터만
MASTERS_ADMIN_ONLY = frozenset({
    "/api/suppliers/create", "/api/suppliers/update",
    "/api/prisms/create", "/api/prisms/update", "/api/prisms/active",
    "/api/inspection-items/create", "/api/inspection-items/update", "/api/inspection-items/active",
    "/api/products/create", "/api/products/update", "/api/products/active",
})


def log_activity(category: str, action: str, target: str = "", detail=None, operator: str = ""):
    """이력 로그 한 줄 기록(로그인은 없지만 행위는 남긴다)."""
    try:
        conn = db.connect()
        conn.execute(
            "INSERT INTO activity_log(ts,category,action,target,detail,operator) VALUES (?,?,?,?,?,?)",
            (db.now_str(), category, action, target,
             json.dumps(detail, ensure_ascii=False) if detail is not None else None, operator))
        conn.commit()
        conn.close()
    except Exception:  # noqa: BLE001 — 로깅 실패(SQLite/PG)가 본 기능을 막지 않도록
        pass


class Handler(SimpleHTTPRequestHandler):
    """정적 파일 + /api/* 라우팅."""

    # 04_웹앱 을 정적 루트로
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB_ROOT), **kwargs)

    # ── 응답 헬퍼 ────────────────────────────────────────────
    def _send_json(self, obj, status=200, cookie=None):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, data_bytes, filename, content_type):
        # 한글 파일명은 RFC5987(filename*) 로 — 다운로드 시 깨지지 않게
        ascii_name = filename.encode("ascii", "ignore").decode()
        # 응답헤더 인젝션 방지: 개행·따옴표·역슬래시·제어문자 제거 (filename* 는 quote 로 이미 안전)
        ascii_name = "".join(c for c in ascii_name if c.isprintable() and c not in '"\\') or "download.xlsx"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition",
                         "attachment; filename=\"%s\"; filename*=UTF-8''%s" % (ascii_name, quote(filename)))
        self.send_header("Content-Length", str(len(data_bytes)))
        self.end_headers()
        self.wfile.write(data_bytes)

    def _read_json_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    # ── 인증 게이트 ──────────────────────────────────────────
    def _get_cookie(self, name):
        raw = self.headers.get("Cookie")
        if not raw:
            return None
        try:
            m = SimpleCookie(raw).get(name)
            return m.value if m else None
        except Exception:  # noqa: BLE001
            return None

    def _current_uid(self):
        return session_manager.validate(self._get_cookie(SESSION_COOKIE))

    def _is_public(self, path):
        return path in PUBLIC_PATHS or path.startswith("/assets/") or path == "/favicon.ico"

    def _gate(self, path):
        """공개 경로가 아니면 세션 검사. 통과하면 self._uid 설정 후 True."""
        if self._is_public(path):
            self._uid = None
            return True
        uid = self._current_uid()
        if uid:
            self._uid = uid
            return True
        if path.startswith("/api/"):
            self._send_json({"ok": False, "error": "로그인이 필요합니다.", "auth": False}, status=401)
        else:
            self.send_response(302)
            self.send_header("Location", "/login.html")
            self.end_headers()
        return False

    # ── 인증 라우트 핸들러 ───────────────────────────────────
    def _handle_login(self):
        body = self._read_json_body()
        uid = (body.get("id") or "").strip()
        if not user_store.verify(uid, body.get("password") or ""):
            log_activity("인증", "로그인실패", target=uid)
            return self._send_json({"ok": False, "error": "아이디 또는 비밀번호가 올바르지 않습니다."}, status=401)
        token = session_manager.issue(uid)
        cookie = f"{SESSION_COOKIE}={token}; HttpOnly; Path=/; SameSite=Lax; Max-Age={auth.SessionManager.TTL}"
        log_activity("인증", "로그인", target=uid, operator=uid)
        return self._send_json({"ok": True, "user": user_store.public(uid)}, cookie=cookie)

    def _handle_logout(self):
        session_manager.revoke(self._get_cookie(SESSION_COOKIE))
        log_activity("인증", "로그아웃", target=self._uid or "", operator=self._uid or "")
        return self._send_json({"ok": True}, cookie=f"{SESSION_COOKIE}=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0")

    def _handle_changepw(self):
        body = self._read_json_body()
        if not user_store.verify(self._uid, body.get("current_password") or ""):
            return self._send_json({"ok": False, "error": "현재 비밀번호가 올바르지 않습니다."}, status=400)
        ok, msg = user_store.change_password(self._uid, body.get("new_password") or "")
        if ok:
            log_activity("인증", "비번변경", target=self._uid, operator=self._uid)
        return self._send_json({"ok": True} if ok else {"ok": False, "error": msg}, status=200 if ok else 400)

    def _handle_changeid(self):
        body = self._read_json_body()
        ok, msg = user_store.change_id(self._uid, body.get("new_id"), body.get("current_password") or "")
        if ok:
            session_manager.revoke_user(self._uid)   # 모든 세션 만료 → 새 ID 로 재로그인
            log_activity("인증", "ID변경", target=str(body.get("new_id") or ""), operator=self._uid)
        return self._send_json({"ok": True} if ok else {"ok": False, "error": msg}, status=200 if ok else 400)

    def _handle_user_add(self):
        if not user_store.is_admin(self._uid):
            return self._send_json({"ok": False, "error": "관리자만 가능합니다."}, status=403)
        body = self._read_json_body()
        ok, msg = user_store.add(body.get("id"), body.get("name"), body.get("password"), body.get("role") or "user")
        if ok:
            log_activity("사용자", "추가", target=str(body.get("id") or ""), operator=self._uid)
        return self._send_json({"ok": True} if ok else {"ok": False, "error": msg}, status=200 if ok else 400)

    def _handle_user_remove(self):
        if not user_store.is_admin(self._uid):
            return self._send_json({"ok": False, "error": "관리자만 가능합니다."}, status=403)
        uid = str(self._read_json_body().get("id") or "")
        if uid == self._uid:
            return self._send_json({"ok": False, "error": "본인 계정은 삭제할 수 없습니다."}, status=400)
        ok, msg = user_store.remove(uid)
        if ok:
            log_activity("사용자", "삭제", target=uid, operator=self._uid)
        return self._send_json({"ok": True} if ok else {"ok": False, "error": msg}, status=200 if ok else 400)

    def _handle_user_update(self):
        if not user_store.is_admin(self._uid):
            return self._send_json({"ok": False, "error": "관리자만 가능합니다."}, status=403)
        body = self._read_json_body()
        ok, msg = user_store.update_user(str(body.get("id") or ""), name=body.get("name"), role=body.get("role"))
        if ok:
            log_activity("사용자", "수정", target=str(body.get("id") or ""), operator=self._uid)
        return self._send_json({"ok": True} if ok else {"ok": False, "error": msg}, status=200 if ok else 400)

    def _handle_user_resetpw(self):
        if not user_store.is_admin(self._uid):
            return self._send_json({"ok": False, "error": "관리자만 가능합니다."}, status=403)
        body = self._read_json_body()
        target = str(body.get("id") or "")
        ok, msg = user_store.change_password(target, body.get("password") or "")
        if ok:
            session_manager.revoke_user(target)   # 해당 사용자 재로그인
            log_activity("사용자", "비번재설정", target=target, operator=self._uid)
        return self._send_json({"ok": True} if ok else {"ok": False, "error": msg}, status=200 if ok else 400)

    # ── GET ──────────────────────────────────────────────────
    def do_GET(self):
        path = urlparse(self.path).path
        if not self._gate(path):     # 미로그인 → 로그인 페이지로 리다이렉트 / API는 401
            return
        if path == "/api/auth/me":
            return self._send_json({"ok": True, "user": user_store.public(self._uid)})
        if path == "/api/auth/users":
            if not user_store.is_admin(self._uid):
                return self._send_json({"ok": False, "error": "관리자만 가능합니다."}, status=403)
            return self._send_json({"ok": True, "items": user_store.list_users()})
        if path == "/":
            self.path = "/index.html"
            return super().do_GET()
        if path.startswith("/api/"):
            return self._route_get(path)
        # 그 외는 정적 파일
        return super().do_GET()

    def _route_get(self, path):
        try:
            if path == "/api/status":
                info = db.db_info()
                try:
                    c = db.connect(); c.execute("SELECT 1"); c.close(); alive = True
                except Exception:  # noqa: BLE001
                    alive = False
                return self._send_json({
                    "app": "Prism 검사·재고 관리",
                    "port": self.server.server_address[1],
                    "db_kind": info["kind"],       # PostgreSQL / SQLite
                    "db_desc": info["desc"],       # 호스트:포트/DB (비밀번호 제외)
                    "db_path": str(db.DB_PATH),    # (하위호환)
                    "db_exists": alive,            # 실제 연결 확인
                    "time": db.now_str(),
                })
            if path == "/api/health":
                conn = db.connect()
                counts = db.table_counts(conn)
                conn.close()
                return self._send_json({"ok": True, "db_exists": db.DB_PATH.exists(), "counts": counts})
            if path == "/api/masters/summary":
                return self._send_json(self._masters_summary())
            if path == "/api/receipts/detail":
                qs = parse_qs(urlparse(self.path).query)
                return self._send_json(receipt_service.detail(qs.get("id", [None])[0]))
            if path == "/api/inspection/lot":
                qs = parse_qs(urlparse(self.path).query)
                return self._send_json(inspection_service.get_for_lot({"id": qs.get("id", [None])[0]}))
            if path == "/api/stock":
                return self._send_json(stock_service.stock_status())
            if path == "/api/inbound-history":
                return self._send_json(inbound_history_service.inbound_history())
            if path == "/api/report/summary":
                qs = parse_qs(urlparse(self.path).query)
                return self._send_json(report_service.summary(product=qs.get("product", [None])[0]))
            if path == "/api/report/lot-excel":
                qs = parse_qs(urlparse(self.path).query)
                data_bytes, fn = report_service.lot_excel(qs.get("lot_id", [None])[0], qs.get("label", [None])[0])
                if not data_bytes:
                    return self._send_json({"ok": False, "error": "로트를 찾을 수 없습니다."}, status=404)
                return self._send_file(data_bytes, fn, XLSX_MIME)
            if path == "/api/report/excel":
                qs = parse_qs(urlparse(self.path).query)
                data_bytes, fn = report_service.report_excel(product=qs.get("product", [None])[0])
                return self._send_file(data_bytes, fn, XLSX_MIME)
            if path in GET_LIST_ROUTES:
                # 목록 함수는 list 를 반환 → {ok, items} 로 감싼다
                return self._send_json({"ok": True, "items": GET_LIST_ROUTES[path]()})
            return self._send_json({"ok": False, "error": "unknown_endpoint", "path": path}, status=404)
        except Exception as exc:  # noqa: BLE001 — API는 항상 JSON 으로 실패 반환
            return self._send_json({"ok": False, "error": str(exc)}, status=500)

    def _masters_summary(self):
        """기준정보 요약 — 대시보드/기준정보 탭용."""
        conn = db.connect()
        try:
            suppliers = [dict(r) for r in conn.execute(
                "SELECT id,name,status,is_active,note FROM supplier ORDER BY id").fetchall()]
            prisms = [dict(r) for r in conn.execute(
                "SELECT id,item_code,prism_type,spec,unit,is_active FROM prism_master ORDER BY id").fetchall()]
            items = [dict(r) for r in conn.execute(
                "SELECT id,name,category,applies_to_incoming,applies_to_post_paint,sort_order,is_active "
                "FROM inspection_item ORDER BY sort_order,id").fetchall()]
            products = conn.execute("SELECT COUNT(*) AS c FROM product").fetchone()["c"]
            return {"ok": True, "suppliers": suppliers, "prisms": prisms,
                    "inspection_items": items, "product_count": products}
        finally:
            conn.close()

    # ── POST (인증 + 기준정보 CRUD 등) ───────────────────────
    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/auth/login":          # 로그인은 게이트 없이
            return self._handle_login()
        if not self._gate(path):               # 그 외는 로그인 필요
            return
        if path == "/api/auth/logout":
            return self._handle_logout()
        if path == "/api/auth/changepw":
            return self._handle_changepw()
        if path == "/api/auth/changeid":
            return self._handle_changeid()
        if path == "/api/auth/users/add":
            return self._handle_user_add()
        if path == "/api/auth/users/remove":
            return self._handle_user_remove()
        if path == "/api/auth/users/update":
            return self._handle_user_update()
        if path == "/api/auth/users/reset-pw":
            return self._handle_user_resetpw()
        if not path.startswith("/api/"):
            return self._send_json({"ok": False, "error": "not_api"}, status=404)
        # 업무 변경(POST)은 담당자 이상만 — 사용자(user)는 조회 전용
        if not user_store.is_manager_or_above(self._uid):
            return self._send_json({"ok": False, "error": "권한이 없습니다 (조회 전용 사용자)."}, status=403)
        # 기준정보(마스터) 편집은 관리자만
        if path in MASTERS_ADMIN_ONLY and not user_store.is_admin(self._uid):
            return self._send_json({"ok": False, "error": "기준정보 편집은 관리자만 가능합니다."}, status=403)
        route = POST_ROUTES.get(path)
        if route is None:
            return self._send_json({"ok": False, "error": "unknown_endpoint", "path": path}, status=404)

        func, category, action = route
        body = self._read_json_body()
        try:
            result = func(body)
        except Exception as exc:  # noqa: BLE001 — 항상 JSON 으로 실패 반환
            return self._send_json({"ok": False, "error": str(exc)}, status=500)

        # 성공한 변경만 이력에 남긴다 (누가 = 로그인 사용자)
        if result.get("ok"):
            target = str(body.get("name") or body.get("product_code") or body.get("plan_month")
                         or body.get("filename") or body.get("id") or "")
            safe = {k: v for k, v in body.items() if k != "content"}  # 큰 파일 b64 는 로그 제외
            log_activity(category, action, target=target, detail=safe, operator=self._uid or "")
        return self._send_json(result, status=200 if result.get("ok") else 400)

    def end_headers(self):
        # 정적 자원(HTML/JS/CSS)은 캐시 재검증 강제 → 코드 업데이트가 새로고침 시 즉시 반영
        # (API 응답은 _send_json 이 이미 no-store 를 설정하므로 중복 방지)
        if not urlparse(self.path).path.startswith("/api/"):
            self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    # 콘솔 로그를 조용히(필요 시 주석 해제)
    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))


def main():
    port = DEFAULT_PORT
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass

    # DB 준비(스키마+시드)
    db.init_db()
    log_activity("시스템", "서버시작", target=f"port={port}")

    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"[OK] Prism 관리 서버 시작 → http://127.0.0.1:{port}/")
    print(f"[INFO] DB = {db.DB_PATH}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] 서버 종료")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
