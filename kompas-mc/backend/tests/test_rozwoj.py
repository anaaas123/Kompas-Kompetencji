import pytest

from kompas_mc.rozwoj import DaneRozwoju, KonfiguracjaRozwoju, zaproponuj
from kompas_mc.ustawienia import Ustawienia

KONF = KonfiguracjaRozwoju.z_pliku(Ustawienia.ze_srodowiska().rozwoj)

WSKAZNIKI = [
    {"kompetencja": "ZARZĄDZANIE LUDŹMI", "wskaznik": "Delegowanie zadań", "poziom": 3,
     "przyklady": ["W projekcie X przydzielił zadania bez terminów; zespół spóźnił się o 2 tygodnie."]},
    {"kompetencja": "RZETELNOŚĆ", "wskaznik": "Wykonywanie zadań zgodnie ze standardami", "poziom": 1,
     "przyklady": ["Pismo do wojewody wysłane bez wymaganej kontroli prawnej."]},
    {"kompetencja": "KOMUNIKACJA", "wskaznik": "Dopasowanie przekazu", "poziom": 9,
     "przyklady": ["Prowadził szkolenie wewnętrzne ocenione najwyżej w ankiecie."]},
    {"kompetencja": "WSPÓŁPRACA", "wskaznik": "Włączanie się w działania", "poziom": 5, "przyklady": []},
    {"kompetencja": "KREATYWNOŚĆ", "wskaznik": "Nowe rozwiązania", "poziom": None},
]


def _dane(**kw):
    return DaneRozwoju.model_validate({"sciezka": "okresowa", "wskazniki": WSKAZNIKI, **kw})


def test_propozycje_powiazane_ze_wskaznikiem_i_przykladem():
    w = zaproponuj(_dane(), KONF)
    assert w.dostepne
    for p in w.propozycje:
        assert p.wskaznik and p.kompetencja and p.przyklady
        assert p.formy, p.wskaznik
        assert all(f.adnotacje for f in p.formy)


def test_obszary_rozwojowe_od_najnizszego_potem_mocne_strony():
    w = zaproponuj(_dane(), KONF)
    assert [(p.typ, p.poziom) for p in w.propozycje] == [
        ("OBSZAR_ROZWOJOWY", 1),
        ("OBSZAR_ROZWOJOWY", 3),
        ("MOCNA_STRONA", 9),
    ]
    assert {p.wskaznik: p.powod for p in w.pominiete} == {
        "Włączanie się w działania": "na poziomie oczekiwań",
        "Nowe rozwiązania": "brak podstaw do oceny",
    }


def test_formy_dobrane_do_kompetencji():
    w = zaproponuj(_dane(), KONF)
    zl = next(p for p in w.propozycje if p.kompetencja == "ZARZĄDZANIE LUDŹMI")
    rz = next(p for p in w.propozycje if p.kompetencja == "RZETELNOŚĆ")
    assert {"coaching", "warsztaty", "szkolenie"} <= {f.id for f in zl.formy}
    assert "coaching" not in {f.id for f in rz.formy}
    assert "samoksztalcenie" in {f.id for f in rz.formy}


def test_asystent_nie_wpisuje_tresci():
    w = zaproponuj(_dane(), KONF)
    assert w.tresc_wnioskow is None
    assert w.status.startswith("PROPOZYCJA")
    assert "rozwoj.tresc-pisze-przelozony" in {r.id for r in w.reguly}


def test_pierwsza_ocena_negatywna_bez_wnioskow():
    w = zaproponuj(_dane(sciezka="pierwsza", wynik_pozytywny=False), KONF)
    assert not w.dostepne and w.propozycje == []
    assert w.reguly[0].id == "rozwoj.pierwsza-tylko-pozytywna"


def test_pierwsza_ocena_bez_wyniku_ostrzega():
    w = zaproponuj(_dane(sciezka="pierwsza"), KONF)
    assert w.dostepne and "tylko przy ocenie pozytywnej" in w.komunikat


def test_brak_przykladu_daje_uwage():
    dane = DaneRozwoju.model_validate({"sciezka": "okresowa", "wskazniki": [
        {"kompetencja": "RZETELNOŚĆ", "wskaznik": "x", "poziom": 3}]})
    (p,) = zaproponuj(dane, KONF).propozycje
    assert p.uwagi and "Brak przykładu" in p.uwagi[0]


def test_kompetencje_w_konfiguracji_istnieja_w_modelu(korpus_mc):
    nazwy = {
        f.tekst for f in korpus_mc.korpus.fragmenty
        if f.doc_id == "model-kompetencji" and f.lokalizator.startswith("Model kompetencji!B")
    }
    for forma in KONF.formy:
        assert set(forma.kompetencje or []) <= nazwy, forma.id


@pytest.mark.parametrize("login, kod", [("przelozony1", 200), ("hr", 403), ("oceniany", 403)])
def test_api_tylko_dla_przelozonego(klient, naglowek, login, kod):
    r = klient.post("/api/rozwoj/propozycje", json=_dane().model_dump(), headers=naglowek(login))
    assert r.status_code == kod
    if kod == 200:
        assert r.json()["tresc_wnioskow"] is None and len(r.json()["propozycje"]) == 3
