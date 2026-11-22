"""Dziennik zmian dowolnego zasobu i rejestr operacji (kto, co, komu, z jakim skutkiem) w SQLite."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock

from .model import WpisDziennika


class Dziennik:
    def __init__(
        self, baza: str | Path = ":memory:", zegar: Callable[[], datetime] | None = None
    ) -> None:
        """``zegar`` wstrzykiwany w testach; domyślnie bieżący czas UTC."""
        self._zegar = zegar or (lambda: datetime.now(UTC))
        self._blokada = Lock()
        self._db = sqlite3.connect(str(baza), check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS dziennik (id INTEGER PRIMARY KEY, czas TEXT, autor TEXT,"
            " zasob TEXT, zasob_id TEXT, roznica TEXT, wersja_regul TEXT)"
        )
        # Rejestr operacji: tylko dopisywanie. Triggery blokują UPDATE i DELETE także spoza tej klasy
        # (chronią przed pomyłką, nie przed administratorem pliku bazy).
        self._db.executescript(_SCHEMAT_OPERACJI)

    def zapisz(
        self,
        autor: str,
        zasob: str,
        zasob_id: str,
        przed: dict | None,
        po: dict | None,
        wersja_regul: str,
    ) -> WpisDziennika | None:
        """Zapisuje różnicę ``przed`` → ``po``. ``None``, gdy nic się nie zmieniło."""
        przed, po = przed or {}, po or {}
        roznica = {
            pole: {"przed": przed.get(pole), "po": po.get(pole)}
            for pole in sorted(przed.keys() | po.keys())
            if pole not in przed or pole not in po or _json(przed[pole]) != _json(po[pole])
        }
        if not roznica:
            return None
        czas = self._zegar()
        roznica = json.loads(_json(roznica))
        with self._blokada, self._db:
            kursor = self._db.execute(
                "INSERT INTO dziennik (czas, autor, zasob, zasob_id, roznica, wersja_regul)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (czas.isoformat(), autor, zasob, zasob_id, _json(roznica), wersja_regul),
            )
        return WpisDziennika(
            id=kursor.lastrowid,
            czas=czas,
            autor=autor,
            zasob=zasob,
            zasob_id=zasob_id,
            roznica=roznica,
            wersja_regul=wersja_regul,
        )

    def operacja(self, **pola: object) -> int:
        """Dopisuje wpis rejestru operacji; pola spoza ``KOLUMNY_OPERACJI`` są błędem."""
        nieznane = set(pola) - set(KOLUMNY_OPERACJI)
        if nieznane:
            raise ValueError(f"nieznane pola rejestru: {sorted(nieznane)}")
        pola.setdefault("czas", self._zegar().isoformat())
        pola["szczegoly"] = _json(pola.get("szczegoly") or {})
        kolumny = [k for k in KOLUMNY_OPERACJI if k in pola]
        with self._blokada, self._db:
            kursor = self._db.execute(
                f"INSERT INTO operacje ({', '.join(kolumny)}) VALUES ({', '.join('?' * len(kolumny))})",
                [pola[k] for k in kolumny],
            )
        return kursor.lastrowid

    def operacje(
        self, *, od: str | None = None, do: str | None = None, aktor: str | None = None,
        akcja: str | None = None, wynik: str | None = None, osoba: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> tuple[list[dict], int]:
        """Wpisy od najnowszych i liczba wszystkich pasujących. ``od``/``do``: czas ISO, ``do`` wyłącznie."""
        warunki, parametry = [], []
        for kolumna, znak, wartosc in (
            ("czas", ">=", od), ("czas", "<", do), ("aktor_login", "=", aktor),
            ("akcja", "=", akcja), ("wynik", "=", wynik), ("oceniany_osoba", "=", osoba),
        ):
            if wartosc:
                warunki.append(f"{kolumna} {znak} ?")
                parametry.append(wartosc)
        gdzie = f" WHERE {' AND '.join(warunki)}" if warunki else ""
        with self._blokada:
            razem = self._db.execute(f"SELECT COUNT(*) FROM operacje{gdzie}", parametry).fetchone()[0]
            wiersze = self._db.execute(
                f"SELECT id, {', '.join(KOLUMNY_OPERACJI)} FROM operacje{gdzie} ORDER BY id DESC LIMIT ? OFFSET ?",
                [*parametry, limit, offset],
            ).fetchall()
        wpisy = [dict(zip(("id", *KOLUMNY_OPERACJI), w, strict=True)) for w in wiersze]
        for w in wpisy:
            w["szczegoly"] = json.loads(w["szczegoly"] or "{}")
        return wpisy, razem

    def historia(self, zasob: str, zasob_id: str) -> list[WpisDziennika]:
        """Wpisy zasobu chronologicznie."""
        with self._blokada:
            wiersze = self._db.execute(
                "SELECT id, czas, autor, zasob, zasob_id, roznica, wersja_regul FROM dziennik"
                " WHERE zasob = ? AND zasob_id = ? ORDER BY id",
                (zasob, zasob_id),
            ).fetchall()
        return [
            WpisDziennika(
                id=i,
                czas=datetime.fromisoformat(c),
                autor=a,
                zasob=z,
                zasob_id=zi,
                roznica=json.loads(r),
                wersja_regul=w,
            )
            for i, c, a, z, zi, r, w in wiersze
        ]


KOLUMNY_OPERACJI = (
    "czas", "request_id", "aktor_login", "aktor_rola", "aktor_osoba", "akcja", "etykieta", "metoda",
    "trasa", "obiekt", "oceniany_osoba", "wynik", "status", "czas_ms", "szczegoly",
)

_SCHEMAT_OPERACJI = """
CREATE TABLE IF NOT EXISTS operacje (
  id INTEGER PRIMARY KEY, czas TEXT NOT NULL, request_id TEXT, aktor_login TEXT, aktor_rola TEXT,
  aktor_osoba TEXT, akcja TEXT NOT NULL, etykieta TEXT, metoda TEXT, trasa TEXT, obiekt TEXT,
  oceniany_osoba TEXT, wynik TEXT NOT NULL, status INTEGER, czas_ms INTEGER, szczegoly TEXT
);
CREATE INDEX IF NOT EXISTS operacje_czas ON operacje (czas);
CREATE INDEX IF NOT EXISTS operacje_aktor ON operacje (aktor_login);
CREATE INDEX IF NOT EXISTS operacje_oceniany ON operacje (oceniany_osoba);
CREATE TRIGGER IF NOT EXISTS operacje_bez_zmian BEFORE UPDATE ON operacje
BEGIN SELECT RAISE(ABORT, 'rejestr operacji: tylko dopisywanie'); END;
CREATE TRIGGER IF NOT EXISTS operacje_bez_usuwania BEFORE DELETE ON operacje
BEGIN SELECT RAISE(ABORT, 'rejestr operacji: tylko dopisywanie'); END;
"""


def _json(wartosc) -> str:
    return json.dumps(wartosc, default=str, sort_keys=True, ensure_ascii=False)
