#!/usr/bin/env bash
# 프리즘 리눅스 배포 설치 — systemd 서비스 + 자동백업 타이머 등록.
#
# 설계 원칙(중요):
#   - 경로/사용자/파이썬 위치를 **자동 감지**한다. 특정 PC 전용 값을 코드에 박지 않는다.
#   - 기계마다 다른 값(포트·백업위치 등)은 /etc/prism/prism.env 에 둔다.
#   - 따라서 WSL·Hyper-V VM·클라우드 VPS 어디서 실행해도 동일하게 동작한다.
#
# 사용법:  sudo bash 08_배포/linux/install.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "[ERROR] 관리자 권한이 필요합니다:  sudo bash $0" >&2
  exit 1
fi

# ── 환경 자동 감지 ───────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"     # 08_배포/linux/ 의 두 단계 위 = 프로젝트 루트
RUN_USER="${SUDO_USER:-$(id -un)}"
RUN_HOME="$(getent passwd "$RUN_USER" | cut -d: -f6)"
PYTHON_BIN="$(command -v python3 || true)"
ENTRY="$PROJECT_DIR/run_server.py"
CONF_DIR="/etc/prism"
CONF="$CONF_DIR/prism.env"

[ -n "$PYTHON_BIN" ] || { echo "[ERROR] python3 를 찾을 수 없습니다." >&2; exit 1; }
[ -f "$ENTRY" ]      || { echo "[ERROR] 진입점이 없습니다: $ENTRY" >&2; exit 1; }

echo "── 감지된 환경 ──────────────────────────────"
echo "  프로젝트 : $PROJECT_DIR"
echo "  실행 사용자 : $RUN_USER (홈: $RUN_HOME)"
echo "  파이썬   : $PYTHON_BIN"
echo ""

# ── 1) 설정 파일 (기계별 값) ─────────────────────────────────
mkdir -p "$CONF_DIR"
if [ ! -f "$CONF" ]; then
  cat > "$CONF" <<EOF
# 프리즘 서비스 설정 — 기계마다 다른 값만 여기에 둔다.
PRISM_PORT=10500
PRISM_DB_NAME=prism
PRISM_BACKUP_DIR=$RUN_HOME/prism-backups
PRISM_BACKUP_KEEP_DAYS=14
EOF
  echo "[생성] $CONF"
else
  echo "[유지] $CONF (이미 있음 — 덮어쓰지 않음)"
fi
chmod 644 "$CONF"

# 로그 디렉터리
mkdir -p "$PROJECT_DIR/logs"
chown "$RUN_USER":"$RUN_USER" "$PROJECT_DIR/logs" || true

# ── 2) 웹서버 서비스 ─────────────────────────────────────────
cat > /etc/systemd/system/prism.service <<EOF
[Unit]
Description=Prism inspection and inventory web server
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=$CONF
ExecStart=$PYTHON_BIN $ENTRY \${PRISM_PORT}
Restart=always
RestartSec=5
StandardOutput=append:$PROJECT_DIR/logs/server.log
StandardError=append:$PROJECT_DIR/logs/server.log

[Install]
WantedBy=multi-user.target
EOF
echo "[생성] /etc/systemd/system/prism.service"

# ── 3) 자동 백업 (서비스 + 타이머) ───────────────────────────
cat > /etc/systemd/system/prism-backup.service <<EOF
[Unit]
Description=Prism database backup
After=postgresql.service
Wants=postgresql.service

[Service]
Type=oneshot
User=$RUN_USER
EnvironmentFile=$CONF
ExecStart=/usr/bin/env bash $SCRIPT_DIR/backup_db.sh
EOF

cat > /etc/systemd/system/prism-backup.timer <<EOF
[Unit]
Description=Prism database backup (daily)

[Timer]
OnCalendar=*-*-* 03:30:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
echo "[생성] prism-backup.service / prism-backup.timer (매일 03:30)"

chmod +x "$SCRIPT_DIR/backup_db.sh" 2>/dev/null || true

# ── 4) 등록 및 시작 ──────────────────────────────────────────
systemctl daemon-reload
systemctl enable postgresql >/dev/null 2>&1 && echo "[활성] postgresql 자동시작" || echo "[경고] postgresql 자동시작 등록 실패(수동 확인 필요)"
systemctl enable prism.service >/dev/null 2>&1 && echo "[활성] prism 자동시작"
systemctl enable prism-backup.timer >/dev/null 2>&1 && echo "[활성] prism-backup 타이머"

echo ""
echo "설치 완료. 다음 명령으로 시작/확인:"
echo "  sudo systemctl start prism"
echo "  systemctl status prism --no-pager"
echo "  sudo systemctl start prism-backup   # 백업 즉시 1회 실행(테스트)"
