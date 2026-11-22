#!/usr/bin/env bash
# Wdrożenie wersji testowej z GitHuba na serwer (Ubuntu 24.04, root).
# Użycie: wdroz.sh [gałąź|SHA]   (domyślnie main – na serwer idzie tylko main)
# Kod: /opt/kompas-repo, front: /opt/kompas/www-<sha> → /opt/kompas/www, dane: /var/lib/kompas (zostają między wersjami).
# Wycofanie: wdroz.sh <poprzedni SHA> (lista w /opt/kompas/historia).
set -euo pipefail
REF="${1:-main}"
REPO=/opt/kompas-repo
UV=/root/.local/bin/uv
[ -d "$REPO/.git" ] || git clone -q https://github.com/harn0ld/Kompas-Kompetencji.git "$REPO"
git -C "$REPO" fetch -q --prune origin
git -C "$REPO" checkout -q --detach "origin/$REF" 2>/dev/null || git -C "$REPO" checkout -q --detach "$REF"
SHA=$(git -C "$REPO" rev-parse --short HEAD)
(cd "$REPO/kompas-mc/backend" && "$UV" sync --frozen --quiet)
(cd "$REPO/kompas-mc/frontend" && npm ci --silent --no-audit --no-fund && npx vite build --outDir "/opt/kompas/www-$SHA" --emptyOutDir >/dev/null)
ln -sfn "/opt/kompas/www-$SHA" /opt/kompas/www
echo "$SHA" > /opt/kompas/WERSJA
echo "$(date -Is) $SHA $REF" >> /opt/kompas/historia
systemctl restart kompas
for _ in $(seq 1 30); do curl -sf -o /dev/null http://127.0.0.1:8000/openapi.json && break; sleep 2; done
curl -sf -o /dev/null http://127.0.0.1:8000/openapi.json && echo "OK: działa $SHA ($REF)" || { echo "BŁĄD: API nie wstało, journalctl -u kompas"; exit 1; }
