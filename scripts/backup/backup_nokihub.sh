#!/bin/sh
set -eu

OUTPUT_DIR="${1:-./backups}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
BUNDLE="$OUTPUT_DIR/nokihub_$TIMESTAMP"
mkdir -p "$BUNDLE"

DB_REMOTE="/tmp/nokihub_$TIMESTAMP.dump"
PRIVATE_REMOTE="/tmp/private_media_$TIMESTAMP.tar.gz"
MEDIA_REMOTE="/tmp/media_$TIMESTAMP.tar.gz"

DB_USER="$(docker compose -f "$COMPOSE_FILE" exec -T db printenv POSTGRES_USER | tr -d '\r')"
DB_NAME="$(docker compose -f "$COMPOSE_FILE" exec -T db printenv POSTGRES_DB | tr -d '\r')"

printf '%s\n' "1/3 Backup PostgreSQL..."
docker compose -f "$COMPOSE_FILE" exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc -f "$DB_REMOTE"
docker compose -f "$COMPOSE_FILE" cp "db:$DB_REMOTE" "$BUNDLE/database.dump"

printf '%s\n' "2/3 Backup private_media..."
docker compose -f "$COMPOSE_FILE" exec -T web python -c "import tarfile,pathlib; root=pathlib.Path('/app/private_media'); root.mkdir(parents=True,exist_ok=True); tf=tarfile.open('$PRIVATE_REMOTE','w:gz'); tf.add(root,arcname='private_media'); tf.close()"
docker compose -f "$COMPOSE_FILE" cp "web:$PRIVATE_REMOTE" "$BUNDLE/private_media.tar.gz"

printf '%s\n' "3/3 Backup media..."
docker compose -f "$COMPOSE_FILE" exec -T web python -c "import tarfile,pathlib; root=pathlib.Path('/app/media'); root.mkdir(parents=True,exist_ok=True); tf=tarfile.open('$MEDIA_REMOTE','w:gz'); tf.add(root,arcname='media'); tf.close()"
docker compose -f "$COMPOSE_FILE" cp "web:$MEDIA_REMOTE" "$BUNDLE/media.tar.gz"

cat > "$BUNDLE/manifest.txt" <<EOF
created_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
database=database.dump
private_media=private_media.tar.gz
media=media.tar.gz
EOF

sha256sum "$BUNDLE/database.dump" "$BUNDLE/private_media.tar.gz" "$BUNDLE/media.tar.gz" > "$BUNDLE/SHA256SUMS"

docker compose -f "$COMPOSE_FILE" exec -T db rm -f "$DB_REMOTE" || true
docker compose -f "$COMPOSE_FILE" exec -T web rm -f "$PRIVATE_REMOTE" "$MEDIA_REMOTE" || true

printf 'Backup completo creato: %s\n' "$BUNDLE"
