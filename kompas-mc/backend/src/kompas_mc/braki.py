"""Panel źródeł: inwentarz materiałów MC, braki, rozbieżności i pytania do mentorów."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from kompas_core.zrodla import ElementAdnotowany, Rozbieznosc, SourceRef, waliduj_adnotacje
from pydantic import BaseModel

from .korpus_mc import KorpusMC

TypBraku = Literal["BRAK", "ROZBIEŻNOŚĆ", "DUPLIKAT"]


class AdnotacjaPanelu(BaseModel):
    adnotacja: SourceRef
    dokument: str | None = None
    plik: str | None = None
    cytat_w_korpusie: bool | None = None
    """None: adnotacja bez cytatu (np. BRAK_ŹRÓDŁA, DECYZJA_PROJEKTOWA)."""


class Brak(BaseModel):
    id: str
    typ: TypBraku
    tytul: str
    opis: str
    wplyw: str | None = None
    pliki: list[str]
    """Wszystkie pliki z „materialy mc”, których wpis dotyczy (z adnotacji i z listy)."""
    adnotacje: list[AdnotacjaPanelu]
    rozbieznosc: Rozbieznosc | None = None


class PytanieDoMentorow(BaseModel):
    id: str
    dotyczy: str
    pytanie: str


class PanelBrakow(BaseModel):
    braki: list[Brak]
    pytania_do_mentorow: list[PytanieDoMentorow]


def zbuduj_panel(plik: str | Path, korpus: KorpusMC) -> PanelBrakow:
    dane = yaml.safe_load(Path(plik).read_text(encoding="utf-8")) or {}
    braki: list[Brak] = []

    for b in dane.get("braki") or []:
        el = ElementAdnotowany.model_validate(
            {k: b[k] for k in ("id", "adnotacje", "rozbieżność") if k in b}
        )
        adnotacje, pliki = [], list(b.get("pliki") or [])
        for ref in el.adnotacje:
            dok = korpus.dokumenty.get(ref.doc_id) if ref.doc_id else None
            if dok and dok.plik.name not in pliki:
                pliki.append(dok.plik.name)
            adnotacje.append(
                AdnotacjaPanelu(
                    adnotacja=ref,
                    dokument=dok.nazwa if dok else None,
                    plik=dok.plik.name if dok else None,
                    cytat_w_korpusie=(
                        None
                        if ref.cytat_doslowny is None
                        else not waliduj_adnotacje(ref, korpus.korpus, el.id)
                    ),
                )
            )
        braki.append(
            Brak(
                id=el.id,
                typ=b["typ"],
                tytul=b["tytul"],
                opis=b["opis"],
                wplyw=b.get("wplyw"),
                pliki=pliki,
                adnotacje=adnotacje,
                rozbieznosc=el.rozbieznosc,
            )
        )

    for d in korpus.duplikaty:
        zrodlo = korpus.dokumenty[d.duplikat_z]
        braki.append(
            Brak(
                id=f"duplikat.{d.duplikat_z}",
                typ="DUPLIKAT",
                tytul=f"Duplikat: {d.plik.name}",
                opis=(
                    f"{d.opis or ''} {round(d.pokrycie * 100)}% fragmentów pliku występuje "
                    f"w dokumencie „{zrodlo.nazwa}”. "
                    + (
                        "Plik nie jest osobnym źródłem."
                        if d.potwierdzony
                        else "Pokrycie poniżej progu: sprawdź plik ręcznie."
                    )
                ).strip(),
                wplyw="Plik nie trafia do korpusu; cytujemy pełny akt.",
                pliki=[d.plik.name, zrodlo.plik.name],
                adnotacje=[],
            )
        )

    return PanelBrakow(
        braki=braki,
        pytania_do_mentorow=[
            PytanieDoMentorow.model_validate(p) for p in dane.get("pytania_do_mentorow") or []
        ],
    )
