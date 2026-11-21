"""Dziennik zmian dowolnego zasobu w SQLite."""

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


def _json(wartosc) -> str:
    return json.dumps(wartosc, default=str, sort_keys=True, ensure_ascii=False)
