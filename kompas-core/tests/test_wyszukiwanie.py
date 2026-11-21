from kompas_core.zrodla import Korpus
from kompas_core.zrodla.korpus import rdzen, tokeny


def test_proste_formy_polskie_maja_wspolny_rdzen():
    assert rdzen("ocena") == rdzen("oceny") == rdzen("ocenie") == rdzen("oceną")
    assert rdzen("terminu") == rdzen("terminów") == rdzen("Termin")
    assert rdzen("pracownika") == rdzen("pracownikowi")


def test_wyszukiwanie_zwraca_id_wynik_i_fragment(manifest):
    korpus = Korpus.z_manifestu(manifest)
    trafienia = korpus.wyszukaj("odwołanie w terminie", k=3)
    assert trafienia, "brak trafień"
    pierwsze = trafienia[0]
    assert pierwsze.fragment.lokalizator == "art. 83 ust. 1"
    assert pierwsze.fragment_id == pierwsze.fragment.id
    assert pierwsze.wynik > 0
    assert [t.wynik for t in trafienia] == sorted((t.wynik for t in trafienia), reverse=True)


def test_wyszukiwanie_odmiana_i_zawezenie(manifest):
    korpus = Korpus.z_manifestu(manifest)
    assert korpus.wyszukaj("negatywnej oceny")[0].fragment.lokalizator == "art. 83 § 11 ust. 1"
    assert korpus.wyszukaj("kryterium", doc_ids=["excel"])[0].fragment.doc_id == "excel"
    assert korpus.wyszukaj("xyzzy") == []


def test_wyraz_podzielony_na_koncu_wiersza_jest_jednym_tokenem():
    assert tokeny("rozmowę wstęp-\nną") == tokeny("rozmowę wstępną")
