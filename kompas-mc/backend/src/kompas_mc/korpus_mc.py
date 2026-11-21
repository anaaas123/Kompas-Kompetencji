"""Korpus aplikacji: manifest z „materialy mc”, podział na fragmenty i duplikaty."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from kompas_core.zrodla import (
    Fragment,
    Kategoria,
    Korpus,
    StatusEkstrakcji,
    WynikEkstrakcji,
    cytat_w_korpusie,
    ekstrahuj,
)

PROG_DUPLIKATU = 0.8
"""Duplikat: co najmniej tyle fragmentów pliku występuje w dokumencie źródłowym.
Reszta różni się zwykle tylko kolejnością kolumn tabeli w warstwie tekstowej PDF."""


@dataclass(frozen=True)
class Dokument:
    doc_id: str
    nazwa: str
    plik: Path
    sciezka: str
    kategoria: Kategoria
    podzial: str
    doc_version: str | None = None
    asystent: bool = True


@dataclass(frozen=True)
class Duplikat:
    plik: Path
    duplikat_z: str
    pokrycie: float
    potwierdzony: bool
    opis: str | None = None


@dataclass(frozen=True)
class Pominiety:
    plik: Path
    powod: str


@dataclass
class KorpusMC:
    korpus: Korpus
    dokumenty: dict[str, Dokument]
    duplikaty: list[Duplikat] = field(default_factory=list)
    pominiete: list[Pominiety] = field(default_factory=list)

    def doc_ids_dla(self, sciezka: str | None) -> list[str]:
        """Dokumenty asystenta dla ścieżki (pierwsza / okresowa) plus wspólne;
        None = wszystkie. Pomija dokumenty z ``asystent: false``."""
        return [
            d.doc_id
            for d in self.dokumenty.values()
            if d.asystent and (sciezka is None or d.sciezka in (sciezka, "wspolne"))
        ]


def _po_stronach(w: WynikEkstrakcji) -> WynikEkstrakcji:
    """Jeden fragment na stronę (poradniki): lokalizator „s. N”."""
    strony: dict[int | None, list[Fragment]] = defaultdict(list)
    for f in w.fragmenty:
        strony[f.strona].append(f)
    prefiks = f"{w.doc_id}@{w.doc_version}" if w.doc_version else w.doc_id
    fragmenty = [
        Fragment(
            id=f"{prefiks}#s{nr}",
            doc_id=w.doc_id,
            doc_version=w.doc_version,
            lokalizator=f"s. {nr}",
            strona=nr,
            tekst="\n".join(f.tekst for f in fr),
        )
        for nr, fr in strony.items()
    ]
    return w.model_copy(update={"fragmenty": fragmenty})


def zaladuj(manifest: str | Path) -> KorpusMC:
    sciezka = Path(manifest)
    dane = yaml.safe_load(sciezka.read_text(encoding="utf-8")) or {}
    baza = sciezka.parent

    dokumenty: dict[str, Dokument] = {}
    wyniki: list[WynikEkstrakcji] = []
    for p in dane.get("dokumenty") or []:
        d = Dokument(
            doc_id=p["doc_id"],
            nazwa=p.get("nazwa", p["doc_id"]),
            plik=(baza / p["plik"]).resolve(),
            sciezka=p.get("sciezka", "wspolne"),
            kategoria=Kategoria(p.get("kategoria", "OBJAŚNIENIE_MATERIAŁU")),
            podzial=p.get("podzial", "jednostki"),
            doc_version=None if p.get("doc_version") is None else str(p["doc_version"]),
            asystent=bool(p.get("asystent", True)),
        )
        if d.doc_id in dokumenty:
            raise ValueError(f"powtórzone doc_id w manifeście: {d.doc_id}")
        dokumenty[d.doc_id] = d
        w = ekstrahuj(d.plik, d.doc_id, d.doc_version)
        if d.podzial == "strony" and w.status is StatusEkstrakcji.OK:
            w = _po_stronach(w)
        wyniki.append(w)

    korpus = Korpus(wyniki)

    duplikaty = []
    for p in dane.get("duplikaty") or []:
        plik = (baza / p["plik"]).resolve()
        zrodlo = p["duplikat_z"]
        w = ekstrahuj(plik, "duplikat")
        pokryte = sum(
            cytat_w_korpusie(f.tekst, korpus, zrodlo) for f in w.fragmenty if f.tekst.strip()
        )
        pokrycie = pokryte / len(w.fragmenty) if w.fragmenty else 0.0
        duplikaty.append(
            Duplikat(
                plik=plik,
                duplikat_z=zrodlo,
                pokrycie=round(pokrycie, 3),
                potwierdzony=pokrycie >= PROG_DUPLIKATU,
                opis=p.get("opis"),
            )
        )

    pominiete = [
        Pominiety(plik=(baza / p["plik"]).resolve(), powod=p["powod"])
        for p in dane.get("pominiete") or []
    ]
    return KorpusMC(korpus=korpus, dokumenty=dokumenty, duplikaty=duplikaty, pominiete=pominiete)
