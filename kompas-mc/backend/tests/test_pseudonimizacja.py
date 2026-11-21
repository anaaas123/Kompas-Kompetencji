from kompas_mc.pseudonimizacja import Pseudonimizator
from kompas_mc.qnt import MockQnt


def test_usuwa_dane_kazdej_osoby_z_qnt(ustawienia):
    qnt = MockQnt.z_pliku(ustawienia.qnt)
    pseudonimizator = Pseudonimizator(qnt)
    kontekst = {
        "osoby": [
            {
                "osoba_id": osoba.osoba_id,
                "imie": osoba.imie,
                "nazwisko": osoba.nazwisko,
                "komorka": osoba.komorka,
            }
            for osoba in qnt.pracownicy
        ]
    }

    wynik = pseudonimizator.json(kontekst, "P-101")

    for osoba in qnt.pracownicy:
        assert osoba.osoba_id.lower() not in wynik.lower()
        assert osoba.imie.lower() not in wynik.lower()
        assert osoba.nazwisko.lower() not in wynik.lower()
        assert osoba.komorka.lower() not in wynik.lower()
    assert "Oceniany" in wynik and "Przełożony" in wynik and "Komórka" in wynik


def test_oczyszcza_imie_w_tresci_przykladu(ustawienia):
    qnt = MockQnt.z_pliku(ustawienia.qnt)
    pseudonimizator = Pseudonimizator(qnt)
    przyklad = {
        "sytuacja": "Anna Zielińska-Demo uzgadniała dokument z Martą Kowalczyk-Demo.",
        "dzialanie": "Anna poprosiła Martę o akceptację.",
        "rezultat": "P-101 przekazała wynik P-001.",
    }

    wynik = pseudonimizator.dane(przyklad, "P-101")

    assert wynik == {
        "sytuacja": "Oceniany uzgadniała dokument z Przełożony.",
        "dzialanie": "Oceniany poprosiła Przełożony o akceptację.",
        "rezultat": "Oceniany przekazała wynik Przełożony.",
    }


def test_nie_zmienia_danych_merytorycznych(ustawienia):
    qnt = MockQnt.z_pliku(ustawienia.qnt)
    dane = {"wskaznik": "Współpraca", "poziom": 5, "decyzja": True}
    assert Pseudonimizator(qnt).dane(dane, "P-101") == dane
