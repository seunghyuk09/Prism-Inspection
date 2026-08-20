# -*- coding: utf-8 -*-
"""ASCII 경로 런처 — run_web.bat 가 호출한다.

배치파일(cmd)은 한글 Windows에서 CP949로 읽혀서 파일 안의 한글(주석/경로 `04_웹앱`)이
깨지기 쉽다. 그래서 배치는 영문만 두고, 한글이 들어간 실제 경로
(C:\\Users\\승혁\\...\\04_웹앱\\backend\\local_server.py)는 파이썬이 처리하게 한다.
배치는 이 파일을 `python run_server.py 10000` 처럼 상대 ASCII 이름으로 실행한다.
"""
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVER = ROOT / "04_웹앱" / "backend" / "local_server.py"

# pythonw(창 없는 실행)에서는 sys.stdout/stderr 가 None 이라 print/로그(sys.stderr.write)가
# 예외를 내고 요청 처리 스레드가 죽는다(응답 없이 연결 끊김). → 헤드리스면 로그파일로 우회.
if sys.stdout is None or sys.stderr is None:
    _logf = open(ROOT / "server_headless.log", "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = _logf
    if sys.stderr is None:
        sys.stderr = _logf

port = sys.argv[1] if len(sys.argv) > 1 else "10000"

if not SERVER.exists():
    print(f"[ERROR] 서버 파일을 찾을 수 없습니다: {SERVER}")
    sys.exit(1)

# local_server.py 의 main() 이 sys.argv[1] 을 포트로 읽으므로 맞춰서 넘긴다.
sys.argv = [str(SERVER), port]
runpy.run_path(str(SERVER), run_name="__main__")
