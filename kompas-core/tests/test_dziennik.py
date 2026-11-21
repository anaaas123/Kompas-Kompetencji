from datetime import UTC, date, datetime, timedelta

from kompas_core.auth import Dziennik

START = datetime(2026, 11, 21, 15, tzinfo=UTC)


def test_kazda_zmiana_tworzy_wpis_z_autorem_czasem_roznica_i_wersja():
    teraz = [START]
    d = Dziennik(zegar=lambda: teraz[0])
    d.zapisz("p1", "ocena", "O1", None, {"wynik": 5, "termin": date(2026, 12, 1)}, "2016")
    teraz[0] += timedelta(minutes=5)
    d.zapisz("p1", "ocena", "O1", {"wynik": 5}, {"wynik": 7}, "2016")
    assert d.zapisz("p1", "ocena", "O1", {"wynik": 7}, {"wynik": 7}, "2016") is None
    d.zapisz("hr", "ocena", "O2", None, {"wynik": 3}, "2016")

    wpisy = d.historia("ocena", "O1")
    assert [(w.autor, w.czas, w.wersja_regul) for w in wpisy] == [
        ("p1", START, "2016"),
        ("p1", START + timedelta(minutes=5), "2016"),
    ]
    assert wpisy[0].roznica == {
        "termin": {"przed": None, "po": "2026-12-01"},
        "wynik": {"przed": None, "po": 5},
    }
    assert wpisy[1].roznica == {"wynik": {"przed": 5, "po": 7}}


def test_dziennik_w_pliku_przetrwa_ponowne_otwarcie(tmp_path):
    baza = tmp_path / "dziennik.db"
    Dziennik(baza, zegar=lambda: START).zapisz("p1", "ocena", "O1", None, {"wynik": 5}, "2016")
    assert [w.roznica for w in Dziennik(baza).historia("ocena", "O1")] == [
        {"wynik": {"przed": None, "po": 5}}
    ]
