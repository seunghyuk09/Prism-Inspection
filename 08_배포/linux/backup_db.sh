#!/usr/bin/env bash
# 프리즘 DB 자동 백업 — pg_dump 로 덤프 후 오래된 백업 정리.
# 설정은 /etc/prism/prism.env 에서 읽는다(기계마다 다른 값은 코드에 넣지 않는다).
set -euo pipefail

CONF="/etc/prism/prism.env"
if [ -f "$CONF" ]; then
  # shellcheck disable=SC1090
  . "$CONF"
fi

DB_NAME="${PRISM_DB_NAME:-prism}"
BACKUP_DIR="${PRISM_BACKUP_DIR:-$HOME/prism-backups}"
KEEP_DAYS="${PRISM_BACKUP_KEEP_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d_%H%M%S)"
OUT="$BACKUP_DIR/prism_${STAMP}.sql.gz"

# pg_dump 는 원본을 수정하지 않는다(읽기 전용)
pg_dump -d "$DB_NAME" | gzip > "$OUT"

# 보관기간이 지난 백업 삭제
find "$BACKUP_DIR" -maxdepth 1 -name 'prism_*.sql.gz' -type f -mtime +"$KEEP_DAYS" -delete

SIZE="$(du -h "$OUT" | cut -f1)"
echo "[OK] backup: $OUT ($SIZE) / keep ${KEEP_DAYS}d / dir=$BACKUP_DIR"
