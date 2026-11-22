# Wdrożenie wersji testowej

Na serwer idzie wyłącznie gałąź `main` z GitHuba. Zmiany robimy na gałęziach i scalamy do `main` przez PR po sprawdzeniu (Karol 22.11).

Serwer: Scaleway DEV1-S (pl-waw-2), Ubuntu 24.04, `https://151-115-86-8.sslip.io`. Działający commit: `/wersja`.

Pierwsze przygotowanie serwera (raz, jako root):

```sh
apt-get install -y caddy fonts-dejavu-core nodejs npm git
curl -LsSf https://astral.sh/uv/install.sh | sh
mkdir -p /opt/kompas /var/lib/kompas
cp kompas.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable kompas
cp Caddyfile /etc/caddy/Caddyfile && systemctl reload caddy
cp wdroz-auto.sh /opt/kompas/ && cp kompas-auto.service kompas-auto.timer /etc/systemd/system/ && systemctl daemon-reload && systemctl enable --now kompas-auto.timer
# /etc/kompas.env (600): SCALEWAY_API_KEY=… (klucz IAM tylko z GenerativeApisModelAccess na projekt)
#   i SCALEWAY_BASE_URL=https://api.scaleway.ai/<id projektu>/v1; bez klucza asystent działa w trybie ekstrakcyjnym
```

Automatycznie: `kompas-auto.timer` co 2 min sprawdza `origin/main` i wdraża nowy commit (`wdroz-auto.sh`, kopia w `/opt/kompas/`); nieudany SHA nie jest ponawiany, serwer wraca do poprzedniej wersji. Ręcznie: `wdroz.sh` (main) albo `wdroz.sh <SHA>`; wycofanie: `wdroz.sh <poprzedni SHA>` z `/opt/kompas/historia`. Baza SQLite w `/var/lib/kompas` zostaje między wersjami.

Serwer dzieli z CAOO (`caoo.151-115-86-8.sslip.io`, port 8001, osobny blok w `/etc/caddy/Caddyfile`). Przy ponownym przygotowaniu serwera nie nadpisuj Caddyfile plikiem z repo, bo zniknie blok CAOO: dopisz tylko blok Kompasu. Oba wdrożenia budują front na serwerze pod jedną blokadą `/run/lock/build-sslip.lock`, więc dwa buildy nie idą naraz.
