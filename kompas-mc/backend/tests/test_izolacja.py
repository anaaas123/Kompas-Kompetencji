"""Aplikacja czyta wyłącznie przeznaczony dla niej folder materiałów."""

from pathlib import Path

from kompas_mc.ustawienia import KATALOG_MC

ZRODLA = (KATALOG_MC.parent / "materialy mc").resolve()


def test_korpus_czyta_wylacznie_materialy_aplikacji(korpus_mc):
    pliki = [d.plik for d in korpus_mc.dokumenty.values()]
    pliki += [d.plik for d in korpus_mc.duplikaty] + [p.plik for p in korpus_mc.pominiete]
    pliki += [Path(w.plik) for w in korpus_mc.korpus.raport]
    for plik in pliki:
        assert plik.resolve().is_relative_to(ZRODLA), plik


def test_kazdy_plik_z_materialow_jest_uwzgledniony(korpus_mc):
    """Każdy materiał jest źródłem, duplikatem albo świadomie pominięty."""
    znane = {d.plik.resolve() for d in korpus_mc.dokumenty.values()}
    znane |= {d.plik.resolve() for d in korpus_mc.duplikaty}
    znane |= {p.plik.resolve() for p in korpus_mc.pominiete}
    wszystkie = {
        plik.resolve()
        for plik in ZRODLA.rglob("*")
        if plik.is_file() and plik.name not in {".DS_Store", "Thumbs.db"}
    }
    assert wszystkie - znane == set()
