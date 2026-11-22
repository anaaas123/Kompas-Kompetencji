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


# --- odmiany imion i nazwisk (#135, Helix G3) ------------------------------------------

import pytest  # noqa: E402

OSOBY_ODMIANY = [
    ("X-001", "Paweł", "Dąbrowski-Demo"),
    ("X-002", "Łukasz", "Wiśniewski-Demo"),
    ("X-003", "Błażej", "Żak-Demo"),
    ("X-004", "Grażyna", "Świątek-Demo"),
    ("X-005", "Marta", "Kowalczyk-Demo"),
    ("X-006", "Kacper", "Mazur-Demo"),
    ("X-007", "Michał", "Śliwa-Demo"),
    ("X-008", "Robert", "Maj-Demo"),
]


def _qnt_odmiany(ustawienia) -> MockQnt:
    """Fikcyjne osoby na wzorze pierwszego rekordu demo; X-001 jest ocenianym, bez przełożonego w QNT."""
    wzor = MockQnt.z_pliku(ustawienia.qnt)
    szablon = wzor.pracownicy[0]
    osoby = [
        szablon.model_copy(update={"osoba_id": oid, "imie": imie, "nazwisko": nazwisko, "przelozony_id": "X-000"})
        for oid, imie, nazwisko in OSOBY_ODMIANY
    ]
    return MockQnt(osoby, wzor.dzis_demo)


@pytest.mark.parametrize(
    "tekst,oczekiwany",
    [
        # dopełniacz, celownik, narzędnik, miejscownik: pełne imię i nazwisko z łącznikiem
        ("Ocena Pawła Dąbrowskiego-Demo jest gotowa.", "Ocena Oceniany jest gotowa."),
        ("Przekazano uwagi Pawłowi Dąbrowskiemu-Demo.", "Przekazano uwagi Oceniany."),
        ("Rozmowa z Pawłem Dąbrowskim-Demo trwała godzinę.", "Rozmowa z Oceniany trwała godzinę."),
        ("Notatka o Pawle Dąbrowskim-Demo.", "Notatka o Oceniany."),
        # samo imię z „ł” i ruchomym „e”
        ("Pawła nie było, Pawłowi wysłano pismo, z Pawłem ustalono termin.",
         "Oceniany nie było, Oceniany wysłano pismo, z Oceniany ustalono termin."),
        ("Michała zastąpił Kacper, a Michałowi i Kacprowi podziękowano.",
         "Osoba zastąpił Osoba, a Osoba i Osoba podziękowano."),
        ("O Michale i Kacprze rozmawiano z Kacprem.", "O Osoba i Osoba rozmawiano z Osoba."),
        # nazwiska na -ski: końcówki 4-literowe; litery ś i ł
        ("Zadanie Łukasza Wiśniewskiego-Demo.", "Zadanie Osoba."),
        ("Pismo do Łukasza przekazano Łukaszowi Wiśniewskiemu-Demo.", "Pismo do Osoba przekazano Osoba."),
        ("Z Łukaszem Wiśniewskim-Demo.", "Z Osoba."),
        # imiona i nazwiska z ż i ś
        ("Projekt Błażeja Żaka-Demo, uwagi dla Błażeja i Błażejowi.", "Projekt Osoba, uwagi dla Osoba i Osoba."),
        ("Z Błażejem Żakiem-Demo.", "Z Osoba."),
        ("Raport Grażyny Świątek-Demo, Grażynie i z Grażyną.", "Raport Osoba, Osoba i z Osoba."),
        ("Michałowi Śliwie-Demo i z Michałem Śliwą-Demo.", "Osoba i z Osoba."),
        # wymiana spółgłoski: Marta → Marcie, Mazur → Mazurze
        ("Przekazano Marcie Kowalczyk-Demo, z Martą uzgodniono.", "Przekazano Osoba, z Osoba uzgodniono."),
        ("O Kacprze Mazurze-Demo i Kacprowi Mazurowi-Demo.", "O Osoba i Osoba."),
        # zapis ze spacją zamiast łącznika
        ("Paweł Dąbrowski Demo i Pawła Dąbrowskiego Demo.", "Oceniany i Oceniany."),
        ("Łukaszowi Wiśniewskiemu Demo.", "Osoba."),
        # samo nazwisko i jego pierwszy człon, bez wspólnego „Demo”
        ("Pan Dąbrowski-Demo, pana Dąbrowskiego i z Wiśniewskim.", "Pan Oceniany, pana Oceniany i z Osoba."),
        # kolejność nazwisko, imię
        ("Dąbrowski-Demo Paweł oraz Wiśniewskiego-Demo Łukasza.", "Oceniany oraz Osoba."),
        # małe litery wpisane przez użytkownika
        ("rozmowa z pawłem dąbrowskim-demo", "rozmowa z Oceniany"),
    ],
)
def test_odmienione_imiona_i_nazwiska_sa_zastepowane(ustawienia, tekst, oczekiwany):
    assert Pseudonimizator(_qnt_odmiany(ustawienia)).tekst(tekst, "X-001") == oczekiwany


@pytest.mark.parametrize(
    "tekst",
    [
        "Wersja demo aplikacji działa.",  # wspólny człon nazwisk nie jest danymi osoby
        "Termin 12 maja, w maju i do końca maja.",  # miesiąc to nie nazwisko „Maj”
        "Adres urzędu i martwy termin bez zmian merytorycznych w kryterium Współpraca.",
    ],
)
def test_zwyklych_slow_nie_zastepuje(ustawienia, tekst):
    assert Pseudonimizator(_qnt_odmiany(ustawienia)).tekst(tekst, "X-001") == tekst


def test_krotkie_nazwisko_samo_tylko_wielka_litera(ustawienia):
    p = Pseudonimizator(_qnt_odmiany(ustawienia))
    assert p.tekst("Pana Maja nie było, z Majem ustalono termin na 3 maja.", "X-001") == (
        "Pana Osoba nie było, z Osoba ustalono termin na 3 maja."
    )
    assert p.tekst("Roberta Maja-Demo i Robertowi Majowi-Demo.", "X-001") == "Osoba i Osoba."


def test_dane_demo_w_odmianie_nie_zostaja(ustawienia):
    """Rzeczywiste osoby z qnt.yaml: żadna forma imienia ani nazwiska nie przechodzi do wyniku."""
    qnt = MockQnt.z_pliku(ustawienia.qnt)
    tekst = (
        "Ocena Tomasza Wiśniewskiego-Demo, uwagi Pawłowi Dąbrowskiemu-Demo, rozmowa z Zofią Szymańską-Demo, "
        "o Annie Zielińskiej-Demo, z Kacprem Mazurem-Demo, Julii Kamińskiej-Demo, Michałowi Wójcikowi-Demo."
    )
    wynik = Pseudonimizator(qnt).tekst(tekst, "P-101").lower()
    for rdzen in ("tomasz", "wiśniewsk", "pawł", "dąbrowsk", "zofi", "szymańsk", "anni", "zielińsk",
                  "kacpr", "mazur", "juli", "kamińsk", "michał", "wójcik", "demo"):
        assert rdzen not in wynik, rdzen
