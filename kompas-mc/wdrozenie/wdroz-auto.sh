#!/usr/bin/env bash
# Automatyczne wdrożenie: gdy origin/main ma nowy commit, wdroż go (uruchamia kompas-auto.timer co 2 min).
# Nieudane wdrożenie nie jest ponawiane dla tego samego SHA (plik /opt/kompas/nieudane), żeby nie zapętlić restartów.
set -euo pipefail
REPO=/opt/kompas-repo
git -C "$REPO" fetch -q origin main
NOWY=$(git -C "$REPO" rev-parse --short origin/main)
OBECNY=$(cat /opt/kompas/WERSJA 2>/dev/null || true)
[ "$NOWY" = "$OBECNY" ] && exit 0
grep -qx "$NOWY" /opt/kompas/nieudane 2>/dev/null && exit 0
if ! /opt/kompas-repo/kompas-mc/wdrozenie/wdroz.sh main; then
  echo "$NOWY" >> /opt/kompas/nieudane
  [ -n "$OBECNY" ] && /opt/kompas-repo/kompas-mc/wdrozenie/wdroz.sh "$OBECNY" || true
  exit 1
fi
