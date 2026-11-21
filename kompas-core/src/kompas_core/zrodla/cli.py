"""CLI walidatora do CI.

    kompas-waliduj --manifest korpus.yaml konfiguracja/*.yaml

Z plików YAML/JSON konfiguracji wersji zbiera każdy słownik z kluczem ``adnotacje``
jako element (``ElementAdnotowany``). ``id`` elementu jest opcjonalne; bez niego
raport podaje ścieżkę w pliku. Kody wyjścia:

- 0: wszystkie elementy mają adnotacje, a cytaty są w korpusie;
- 1: brak pokrycia lub błędna adnotacja (raport na stdout);
- 2: błąd użycia (brak pliku, zły manifest).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator
from pathlib import Path

import yaml
from pydantic import ValidationError

from .korpus import Korpus
from .model import ElementAdnotowany, Rozbieznosc, SourceRef, StatusEkstrakcji
from .walidator import BladWalidacji, KodBledu, waliduj_elementy


def _wczytaj(plik: Path) -> object:
    tekst = plik.read_text(encoding="utf-8")
    if plik.suffix.lower() == ".json":
        return json.loads(tekst)
    return yaml.safe_load(tekst)


def _elementy(dane: object, sciezka: str) -> Iterator[tuple[str, dict]]:
    """Każdy słownik z kluczem ``adnotacje`` (rekurencyjnie)."""
    if isinstance(dane, dict):
        if "adnotacje" in dane:
            yield sciezka, dane
        for k, v in dane.items():
            if k != "adnotacje":
                yield from _elementy(v, f"{sciezka}.{k}")
    elif isinstance(dane, list):
        for i, v in enumerate(dane):
            yield from _elementy(v, f"{sciezka}[{i}]")


def _zbuduj(
    plik: Path, sciezka: str, surowy: dict
) -> tuple[ElementAdnotowany | None, list[BladWalidacji]]:
    el_id = str(surowy.get("id") or f"{plik}:{sciezka}")
    bledy: list[BladWalidacji] = []
    adnotacje: list[SourceRef] = []
    surowe = surowy.get("adnotacje") or []
    if not isinstance(surowe, list):
        surowe = [surowe]
    for i, a in enumerate(surowe):
        try:
            adnotacje.append(SourceRef.model_validate(a))
        except ValidationError as e:
            bledy.append(
                BladWalidacji(
                    element_id=el_id,
                    kod=KodBledu.NIEPOPRAWNA_ADNOTACJA,
                    komunikat=f"adnotacje[{i}]: {_opis(e)}",
                )
            )
    rozb = surowy.get("rozbieżność", surowy.get("rozbieznosc"))
    try:
        el = ElementAdnotowany(
            id=el_id,
            adnotacje=adnotacje,
            rozbieznosc=None if rozb is None else Rozbieznosc.model_validate(rozb),
        )
    except ValidationError as e:
        bledy.append(
            BladWalidacji(element_id=el_id, kod=KodBledu.NIEPOPRAWNA_ADNOTACJA, komunikat=_opis(e))
        )
        el = ElementAdnotowany(id=el_id, adnotacje=adnotacje)
    if surowe and not adnotacje:
        # wszystkie adnotacje błędne: błąd już zgłoszony, nie dubluj BRAK_ADNOTACJI
        return None, bledy
    return el, bledy


def _opis(e: ValidationError) -> str:
    return "; ".join(err["msg"].removeprefix("Value error, ") for err in e.errors())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="kompas-waliduj",
        description="Sprawdza, czy każdy element konfiguracji ma adnotację "
        "i czy każdy cytat występuje dosłownie w korpusie.",
    )
    p.add_argument("--manifest", required=True, type=Path, help="manifest korpusu (YAML)")
    p.add_argument("pliki", nargs="+", type=Path, help="pliki konfiguracji YAML/JSON")
    args = p.parse_args(argv)

    try:
        korpus = Korpus.z_manifestu(args.manifest)
        konfiguracje = [(f, _wczytaj(f)) for f in args.pliki]
    except (OSError, ValueError, yaml.YAMLError) as e:
        print(f"błąd: {e}", file=sys.stderr)
        return 2

    for w in korpus.raport:
        if w.status is not StatusEkstrakcji.OK or w.komunikat:
            print(f"uwaga: {w.doc_id} ({w.plik}): {w.status.value} {w.komunikat or ''}".rstrip())

    elementy: list[ElementAdnotowany] = []
    bledy: list[BladWalidacji] = []
    for plik, dane in konfiguracje:
        for sciezka, surowy in _elementy(dane, "$"):
            el, b = _zbuduj(plik, sciezka, surowy)
            bledy.extend(b)
            if el is not None:
                elementy.append(el)

    wynik = waliduj_elementy(elementy, korpus)
    bledy.extend(wynik.bledy)
    for b in bledy:
        print(f"BŁĄD {b.kod.value} [{b.element_id}]: {b.komunikat}")
    print(
        f"elementy: {wynik.sprawdzone_elementy}, cytaty: {wynik.sprawdzone_cytaty}, "
        f"fragmenty korpusu: {len(korpus.fragmenty)}, błędy: {len(bledy)}"
    )
    return 1 if bledy else 0


if __name__ == "__main__":
    sys.exit(main())
