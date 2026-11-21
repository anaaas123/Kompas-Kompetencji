"""Wersja MC nie czyta folderu „materiały” ani niczego z wersji 1."""

import re
import unicodedata
from pathlib import Path

from kompas_mc.ustawienia import KATALOG_MC

ZRODLA_MC = (KATALOG_MC.parent / "materialy mc").resolve()
ZAKAZANE = re.compile(r"materiały|kompas[-_]v1", re.IGNORECASE)
ROZSZERZENIA = {".py", ".yaml", ".yml", ".json", ".toml", ".ts", ".tsx", ".js", ".html"}
POMIJANE_KATALOGI = {"node_modules", ".venv", "dist", "__pycache__", ".pytest_cache"}


def _pliki_wersji():
    for p in KATALOG_MC.rglob("*"):
        if POMIJANE_KATALOGI & set(p.relative_to(KATALOG_MC).parts):
            continue
        if p.is_file() and p.suffix in ROZSZERZENIA and p.resolve() != Path(__file__).resolve():
            yield p


def test_kod_i_konfiguracja_nie_odwoluja_sie_do_wersji_1():
    naruszenia = []
    for p in _pliki_wersji():
        tekst = unicodedata.normalize("NFC", p.read_text(encoding="utf-8"))
        for nr, linia in enumerate(tekst.splitlines(), start=1):
            if ZAKAZANE.search(linia):
                naruszenia.append(f"{p.relative_to(KATALOG_MC)}:{nr}: {linia.strip()}")
    assert not naruszenia, "\n".join(naruszenia)


def test_korpus_czyta_wylacznie_materialy_mc(korpus_mc):
    pliki = [d.plik for d in korpus_mc.dokumenty.values()]
    pliki += [d.plik for d in korpus_mc.duplikaty] + [p.plik for p in korpus_mc.pominiete]
    pliki += [Path(w.plik) for w in korpus_mc.korpus.raport]
    for p in pliki:
        assert p.resolve().is_relative_to(ZRODLA_MC), p


def test_kazdy_plik_z_materialow_mc_jest_uwzgledniony(korpus_mc):
    """Każdy plik z „materialy mc” jest źródłem, duplikatem albo świadomie pominięty."""
    znane = {d.plik.resolve() for d in korpus_mc.dokumenty.values()}
    znane |= {d.plik.resolve() for d in korpus_mc.duplikaty}
    znane |= {p.plik.resolve() for p in korpus_mc.pominiete}
    wszystkie = {
        p.resolve() for p in ZRODLA_MC.rglob("*")
        if p.is_file() and p.name not in {".DS_Store", "Thumbs.db"}
    }
    assert wszystkie - znane == set()
