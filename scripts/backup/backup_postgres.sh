#!/bin/sh
set -eu

OUTPUT_DIR="${1:-./backups}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
REMOTE_FILE="/tmp/lef_timesheet_${TIMESTAMP}.dump"
LOCAL_FILE="${OUTPUT_DIR}/lef_timesheet_${TIMESTAMP}.dump"

mkdir -p "$OUTPUT_DIR"
docker compose -f "$COMPOSE_FILE" exec -T db sh -c \
  "pg_dump -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Fc -f '$REMOTE_FILE'"
docker compose -f "$COMPOSE_FILE" cp "db:$REMOTE_FILE" "$LOCAL_FILE"
docker compose -f "$COMPOSE_FILE" exec -T db rm -f "$REMOTE_FILE"
echo "Backup creato: $LOCAL_FILE"
