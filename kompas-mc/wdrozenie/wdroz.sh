#!/usr/bin/env bash
# Wdrożenie wersji testowej z GitHuba na serwer (Ubuntu 24.04, root).
# Użycie: wdroz.sh [main|SHA]   (domyślnie main; SHA tylko z historii main – do wycofania)
# Kod: /opt/kompas-repo, front: /opt/kompas/www-<sha> → /opt/kompas/www, dane: /var/lib/kompas (zostają między wersjami).
# Wycofanie: wdroz.sh <poprzedni SHA> (lista w /opt/kompas/historia).
set -euo pipefail
# Serwer dzielimy z CAOO (2 GB RAM): jeden build naraz. Czekamy na wspólną blokadę, zamiast pomijać, bo
# wyjście z błędem oznaczyłoby SHA jako nieudany w wdroz-auto.sh. Zwalnia się sama przy końcu skryptu.
exec 9>/run/lock/build-sslip.lock
flock 9
REF="${1:-main}"
REPO=/opt/kompas-repo
UV=/root/.local/bin/uv
[ -d "$REPO/.git" ] || git clone -q https://github.com/harn0ld/Kompas-Kompetencji.git "$REPO"
git -C "$REPO" fetch -q --prune origin
# Tylko main albo commit z historii main (wycofanie); żadnych innych gałęzi ani nazw, które udają SHA.
if [ "$REF" = "main" ]; then
  CEL=$(git -C "$REPO" rev-parse --verify refs/remotes/origin/main)
elif [[ "$REF" =~ ^[0-9a-f]{7,40}$ ]]; then
  CEL=$(git -C "$REPO" rev-parse --verify "$REF^{commit}")
  git -C "$REPO" merge-base --is-ancestor "$CEL" refs/remotes/origin/main || { echo "ODMOWA: $REF nie jest w historii main"; exit 2; }
else
  echo "ODMOWA: tylko main albo SHA commita z main"; exit 2
fi
git -C "$REPO" checkout -q --detach "$CEL"
SHA=$(git -C "$REPO" rev-parse HEAD)
(cd "$REPO/kompas-mc/backend" && "$UV" sync --frozen --quiet)
(cd "$REPO/kompas-mc/frontend" && npm ci --silent --no-audit --no-fund && npx vite build --outDir "/opt/kompas/www-$SHA" --emptyOutDir >/dev/null)
# Podmiana atomowa (-T: nigdy link wewnątrz katalogu). 22.11: /opt/kompas/www był katalogiem, `ln -sfn` wstawiał
# link do środka i od 01:49 serwer pokazywał stary front przy nowym API. Zły stan = przerwane wdrożenie, nie cisza.
ln -sfnT "/opt/kompas/www-$SHA" /opt/kompas/www
[ "$(readlink /opt/kompas/www)" = "/opt/kompas/www-$SHA" ] || { echo "BŁĄD: /opt/kompas/www nie wskazuje www-$SHA"; exit 1; }
echo "$SHA" > /opt/kompas/WERSJA
echo "$(date -Is) $SHA $REF" >> /opt/kompas/historia
systemctl restart kompas
for _ in $(seq 1 30); do curl -sf -o /dev/null http://127.0.0.1:8000/openapi.json && break; sleep 2; done
curl -sf -o /dev/null http://127.0.0.1:8000/openapi.json && echo "OK: działa $SHA ($REF)" || { echo "BŁĄD: API nie wstało, journalctl -u kompas"; exit 1; }
