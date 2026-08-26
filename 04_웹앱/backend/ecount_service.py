# -*- coding: utf-8 -*-
"""이카운트(ECOUNT) OpenAPI 연동 — Zone → 로그인(SESSION_ID) → 조회.

인증정보는 00_설정/ecount.env 에서 읽는다(git 제외, API 키 비노출):
  EC_COM_CODE, EC_USER_ID, EC_API_CERT_KEY, EC_TEST(1/0), EC_ZONE(선택)

흐름(이카운트 OAPI V2):
  1) Zone:  POST https://{host}.ecount.com/OAPI/V2/Zone   body={COM_CODE}          → ZONE
  2) Login: POST https://{host}{ZONE}.ecount.com/OAPI/V2/OAPILogin                 → SESSION_ID
  3) 조회:  POST https://{host}{ZONE}.ecount.com/OAPI/V2/...?SESSION_ID=...         → 데이터
  host = 'sboapi'(테스트) / 'oapi'(운영)
외부 의존성 없이 표준 urllib 사용.
"""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / "00_설정" / "ecount.env"


def _load_cfg() -> dict:
    cfg = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    return cfg


def _host(cfg) -> str:
    return "sboapi" if str(cfg.get("EC_TEST", "1")).strip() != "0" else "oapi"


def _post(url: str, body: dict, timeout=20) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_zone(cfg) -> tuple[str | None, str | None]:
    """회사코드로 ZONE 조회. (zone, error)"""
    if cfg.get("EC_ZONE"):
        return cfg["EC_ZONE"], None
    host = _host(cfg)
    try:
        r = _post(f"https://{host}.ecount.com/OAPI/V2/Zone", {"COM_CODE": cfg.get("EC_COM_CODE", "")})
    except Exception as exc:  # noqa: BLE001
        return None, f"Zone 호출 실패: {exc}"
    zone = (r.get("Data") or {}).get("ZONE") or r.get("ZONE")
    if not zone:
        return None, f"ZONE 을 못 받음: {json.dumps(r, ensure_ascii=False)[:300]}"
    return zone, None


def login(cfg, zone) -> tuple[str | None, str | None]:
    """SESSION_ID 발급. (session_id, error)"""
    host = _host(cfg)
    body = {
        "COM_CODE": cfg.get("EC_COM_CODE", ""),
        "USER_ID": cfg.get("EC_USER_ID", ""),
        "API_CERT_KEY": cfg.get("EC_API_CERT_KEY", ""),
        "LAN_TYPE": "ko-KR",
        "ZONE": zone,
    }
    try:
        r = _post(f"https://{host}{zone}.ecount.com/OAPI/V2/OAPILogin", body)
    except Exception as exc:  # noqa: BLE001
        return None, f"로그인 호출 실패: {exc}"
    datas = ((r.get("Data") or {}).get("Datas") or {})
    sid = datas.get("SESSION_ID") or (r.get("Data") or {}).get("SESSION_ID")
    if not sid:
        return None, f"SESSION_ID 없음(인증 확인): {json.dumps(r, ensure_ascii=False)[:400]}"
    return sid, None


def test_connection(data=None) -> dict:
    """설정된 인증정보로 Zone→로그인까지 확인. 키는 노출하지 않음."""
    cfg = _load_cfg()
    if not ENV_FILE.exists():
        return {"ok": False, "error": "00_설정/ecount.env 가 없습니다. ecount.env.example 을 참고해 만드세요."}
    miss = [k for k in ("EC_COM_CODE", "EC_USER_ID", "EC_API_CERT_KEY") if not cfg.get(k)]
    if miss:
        return {"ok": False, "error": f"ecount.env 에 값 누락: {', '.join(miss)}"}
    zone, err = get_zone(cfg)
    if err:
        return {"ok": False, "step": "zone", "error": err}
    sid, err = login(cfg, zone)
    if err:
        return {"ok": False, "step": "login", "zone": zone, "error": err}
    return {"ok": True, "zone": zone, "env": "테스트(sboapi)" if _host(cfg) == "sboapi" else "운영(oapi)",
            "session": (sid[:4] + "…") if sid else None, "message": "Zone·로그인 성공"}


if __name__ == "__main__":
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    print(json.dumps(test_connection(), ensure_ascii=False, indent=1))
