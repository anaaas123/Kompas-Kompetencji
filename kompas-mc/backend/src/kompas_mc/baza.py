"""Baza SQLite aplikacji Kompas Kompetencji."""

from __future__ import annotations

import sqlite3
from pathlib import Path

WERSJA_SCHEMATU = "7"


def polacz(plik: str | Path) -> sqlite3.Connection:
    plik = Path(plik)
    plik.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(plik, check_same_thread=False)
    conn.execute("CREATE TABLE IF NOT EXISTS meta (klucz TEXT PRIMARY KEY, wartosc TEXT NOT NULL)")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS notatki (id INTEGER PRIMARY KEY, osoba_id TEXT NOT NULL,"
        " autor TEXT NOT NULL, tresc TEXT NOT NULL, czas TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS procesy (id INTEGER PRIMARY KEY, osoba_id TEXT NOT NULL,"
        " sciezka TEXT NOT NULL, arkusz TEXT NOT NULL, krok INTEGER NOT NULL, status TEXT NOT NULL,"
        " rozpoczal TEXT NOT NULL, rozpoczeto TEXT NOT NULL, zgodna_z_propozycja INTEGER NOT NULL,"
        " uzasadnienie TEXT, krok1 TEXT NOT NULL, krok2 TEXT)"
    )
    kolumny = {w[1] for w in conn.execute("PRAGMA table_info(procesy)")}
    # Kolejne kroki mogą otworzyć bazę utworzoną przez starszą wersję.
    for nazwa in ("krok2", "oceny_wskaznikow", "decyzje", "wynik_okresowy", "arkusz_okresowy", "pierwsza_ocena"):
        if nazwa not in kolumny:
            conn.execute(f"ALTER TABLE procesy ADD COLUMN {nazwa} TEXT")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS rejestr_ezd (id INTEGER PRIMARY KEY, proces_id INTEGER NOT NULL,"
        " odcisk TEXT NOT NULL, zarejestrowano TEXT NOT NULL, sha256_pdf TEXT NOT NULL,"
        " pdf BLOB NOT NULL, UNIQUE (proces_id, odcisk))"
    )
    conn.execute(
        "INSERT OR IGNORE INTO meta (klucz, wartosc) VALUES ('wersja_aplikacji', 'mc-bdg')"
    )
    conn.execute(
        "INSERT INTO meta (klucz, wartosc) VALUES ('wersja_schematu', ?)"
        " ON CONFLICT(klucz) DO UPDATE SET wartosc = excluded.wartosc"
        " WHERE CAST(meta.wartosc AS INTEGER) < CAST(excluded.wartosc AS INTEGER)",
        (WERSJA_SCHEMATU,),
    )
    conn.commit()
    return conn
