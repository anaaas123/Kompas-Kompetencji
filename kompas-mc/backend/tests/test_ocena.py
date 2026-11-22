"""Kroki 3–5 (#31): zachowania i przykłady, sugerowany poziom, decyzja przełożonego."""

from datetime import UTC, date, datetime, timedelta

import pytest
from kompas_core.zrodla import cytat_w_korpusie
from pydantic import ValidationError

from kompas_mc.ocena import (
    BladOceny,
    KonfiguracjaOceny,
    OcenaWskaznika,
    Przyklad,
    ZapisDecyzji,
    ostrzezenia_wskaznika,
    scal_decyzje,
    sugestia,
)


@pytest.fixture(scope="module")
def konf(ustawienia):
    return KonfiguracjaOceny.z_pliku(ustawienia.ocena)


def O(poziom, przyklad=False):  # noqa: N802
    p = [Przyklad(sytuacja="S", dzialanie="D", rezultat="R")] if przyklad else []
    return OcenaWskaznika(poziom=poziom, przyklady=p)


BRAK = OcenaWskaznika(brak_podstaw=True)


# ---------------------------------------------------------------- metodyka sugestii


def test_brak_podstaw_nie_obniza_sugestii(konf):
    bez = sugestia([O(3), O(5), O(5)], "okresowa", konf)
    z = sugestia([O(3), O(5), O(5), BRAK], "okresowa", konf)
    assert bez.punkty == z.punkty == 5
    assert z.rozklad["brak_podstaw"] == 1 and z.oceniono == 3 and z.wybrano == 4


def test_remis_pokazuje_dwie_wartosci_i_nie_wybiera(konf):
    s = sugestia([O(3), O(7)], "okresowa", konf)
    assert s.status == "REMIS"
    assert s.punkty is None and s.poziom_modelu is None
    assert s.remis == [3, 7] and s.punkty_remisu == [3, 7]


def test_remis_o_rownych_srodkowych_to_zwykly_poziom(konf):
    s = sugestia([O(3), O(5), O(5), O(9)], "okresowa", konf)
    assert s.status == "POZIOM" and s.punkty == 5


@pytest.mark.parametrize(
    "oceny",
    [[None, None], [BRAK, BRAK], [O(9), BRAK, BRAK], [O(5), None, None]],
)
def test_niewystarczajace_dane(konf, oceny):
    s = sugestia(oceny, "okresowa", konf)
    assert s.status == "NIEWYSTARCZAJACE_DANE" and s.punkty is None


def test_polowa_ocenionych_wystarcza(konf):
    assert sugestia([O(7), BRAK], "okresowa", konf).punkty == 7


@pytest.mark.parametrize(("poziom", "punkty"), [(1, 3), (3, 3), (5, 5), (7, 7), (9, 7)])
def test_mapowanie_5_na_3_w_pierwszej_ocenie(konf, poziom, punkty):
    s = sugestia([O(poziom)], "pierwsza", konf)
    assert s.poziom_modelu == poziom and s.punkty == punkty
    assert "mapowanie 5→3" in s.opis


def test_remis_w_pierwszej_ocenie_po_mapowaniu(konf):
    assert sugestia([O(1), O(3)], "pierwsza", konf).punkty == 3  # 1 i 3 → 3 pkt
    s = sugestia([O(3), O(7)], "pierwsza", konf)
    assert s.status == "REMIS" and s.punkty_remisu == [3, 7]


def test_etykieta_metodyki_przy_kazdej_sugestii(konf):
    for oceny in ([O(5)], [O(3), O(7)], [None]):
        s = sugestia(oceny, "okresowa", konf)
        assert "DECYZJA_PROJEKTOWA" in s.metodyka and "wymaga zatwierdzenia" in s.metodyka


def test_ocena_wskaznika_poziom_albo_brak_podstaw():
    with pytest.raises(ValidationError):
        OcenaWskaznika(poziom=5, brak_podstaw=True)
    with pytest.raises(ValidationError):
        OcenaWskaznika()
    with pytest.raises(ValidationError):
        OcenaWskaznika(poziom=4)
    with pytest.raises(ValidationError):
        Przyklad(sytuacja=" ", dzialanie="D", rezultat="R")


def test_cytaty_konfiguracji_oceny_sa_w_korpusie(konf, korpus_mc):
    refs = [*konf.metodyka.adnotacje, *konf.mapowanie_pierwsza.adnotacje, *konf.przyklady.adnotacje]
    refs += [a for s in konf.skale.values() for a in s.adnotacje]
    for r in refs:
        if r.cytat_doslowny:
            assert cytat_w_korpusie(r.cytat_doslowny, korpus_mc.korpus, r.doc_id), r


# ---------------------------------------------------------------- API


def _proces_z_krokiem2(klient, naglowek, osoba_id, sciezka, login):
    h = naglowek(login)
    proces = next(
        (p for p in klient.get("/api/procesy", headers=h).json()
         if p["osoba_id"] == osoba_id and p["status"] == "W_TOKU"),
        None,
    )
    if proces is None:
        r = klient.post("/api/procesy", json={"osoba_id": osoba_id, "sciezka": sciezka}, headers=h)
        assert r.status_code == 201, r.text
        proces = r.json()
    if proces["krok2"] is None:
        p = klient.get(f"/api/procesy/{proces['id']}/krok2", headers=h).json()
        wsk = {
            k["kompetencja_id"]: [w["wskaznik_id"] for w in k["wskazniki"][:2]]
            for k in p["kryteria"]
            if k["rodzaj"] == "OBOWIAZKOWE"
        }
        r = klient.put(f"/api/procesy/{proces['id']}/krok2", json={"wskazniki": wsk}, headers=h)
        assert r.status_code == 200, r.text
        proces = r.json()
    return proces


def test_bez_kroku2_409(klient, naglowek):
    h = naglowek("przelozony2")
    r = klient.post("/api/procesy", json={"osoba_id": "P-204", "sciezka": "pierwsza"}, headers=h)
    assert r.status_code == 201, r.text
    assert klient.get(f"/api/procesy/{r.json()['id']}/ocena", headers=h).status_code == 409


def test_pelny_przebieg_okresowej(klient, naglowek):
    h = naglowek("przelozony2")
    proces = _proces_z_krokiem2(klient, naglowek, "P-103", "okresowa", "przelozony2")
    url = f"/api/procesy/{proces['id']}/ocena"

    stan = klient.get(url, headers=h).json()
    assert stan["skala"]["punkty"] == [1, 3, 5, 7, 9]
    assert len(stan["kryteria"]) == 5
    k = stan["kryteria"][0]
    assert len(k["wskazniki"][0]["poziomy"]) == 5
    assert k["sugestia"]["status"] == "NIEWYSTARCZAJACE_DANE" and k["decyzja"] is None
    w1, w2 = (w["wskaznik_id"] for w in k["wskazniki"])

    # krok 3: poziom 7 bez przykładu → ostrzeżenie, ale zapis przechodzi
    przyklad = {"sytuacja": "Pilny incydent", "dzialanie": "Zwołała zespół", "rezultat": "Raport na czas",
                "powtarzalnosc": "REGULARNE", "zlozonosc": "WYSOKA"}
    r = klient.put(f"{url}/wskazniki", headers=h, json={"wskazniki": {
        w1: {"poziom": 7}, w2: {"poziom": 7, "przyklady": [przyklad]},
    }})
    assert r.status_code == 200, r.text
    stan = r.json()
    k = stan["kryteria"][0]
    assert k["wskazniki"][0]["ostrzezenia"] and not k["wskazniki"][1]["ostrzezenia"]
    assert stan["ostrzezenia"]
    # krok 4: sugestia, ale bez automatycznej decyzji
    assert k["sugestia"]["status"] == "POZIOM" and k["sugestia"]["punkty"] == 7
    assert "DECYZJA_PROJEKTOWA" in k["sugestia"]["metodyka"]
    assert k["decyzja"] is None
    assert klient.get(f"/api/procesy/{proces['id']}", headers=h).json()["krok"] >= 3

    # krok 5: odejście od sugestii zapisuje się także bez uzasadnienia (opcjonalne, Karol 21.11)
    kid = k["kompetencja_id"]
    r = klient.put(f"{url}/decyzje", headers=h, json={"decyzje": {kid: {"punkty": 5}}})
    assert r.status_code == 200 and r.json()["kryteria"][0]["decyzja"]["zgodna_z_sugestia"] is False
    r = klient.put(f"{url}/decyzje", headers=h, json={"decyzje": {kid: {"punkty": 5, "uzasadnienie": "Jeden przykład."}}})
    assert r.status_code == 200
    d = r.json()["kryteria"][0]["decyzja"]
    assert d["punkty"] == 5 and d["zgodna_z_sugestia"] is False and d["zapisal"] == "przelozony2"
    r = klient.put(f"{url}/decyzje", headers=h, json={"decyzje": {kid: {"punkty": 7}}})
    assert r.json()["kryteria"][0]["decyzja"]["zgodna_z_sugestia"] is True

    # skala ścieżki
    r = klient.put(f"{url}/decyzje", headers=h, json={"decyzje": {kid: {"punkty": 4}}})
    assert r.status_code == 422

    # decyzje dla wszystkich kryteriów → krok 5
    reszta = {k["kompetencja_id"]: {"punkty": 5, "uzasadnienie": "Ocena przełożonego."} for k in stan["kryteria"][1:]}
    stan = klient.put(f"{url}/decyzje", headers=h, json={"decyzje": reszta}).json()
    assert stan["kompletnosc"]["kryteria_z_decyzja"] == 5
    assert klient.get(f"/api/procesy/{proces['id']}", headers=h).json()["krok"] == 5

    # dane dla #36 przechodzą przez /api/rozwoj/propozycje
    assert stan["dla_rozwoju"]
    r = klient.post("/api/rozwoj/propozycje", headers=h,
                    json={"sciezka": "okresowa", "wskazniki": stan["dla_rozwoju"]})
    assert r.status_code == 200, r.text

    historia = klient.app.state.dziennik.historia("proces", str(proces["id"]))
    assert any("decyzje" in w.roznica for w in historia)
    assert any("oceny_wskaznikow" in w.roznica for w in historia)


def test_brak_podstaw_i_usuwanie_oceny(klient, naglowek):
    h = naglowek("przelozony2")
    proces = _proces_z_krokiem2(klient, naglowek, "P-103", "okresowa", "przelozony2")
    url = f"/api/procesy/{proces['id']}/ocena"
    k = klient.get(url, headers=h).json()["kryteria"][1]
    w1, w2 = (w["wskaznik_id"] for w in k["wskazniki"])
    stan = klient.put(f"{url}/wskazniki", headers=h,
                      json={"wskazniki": {w1: {"brak_podstaw": True}, w2: {"poziom": 3}}}).json()
    s = next(x for x in stan["kryteria"] if x["kompetencja_id"] == k["kompetencja_id"])["sugestia"]
    assert s["punkty"] == 3 and s["rozklad"]["brak_podstaw"] == 1
    stan = klient.put(f"{url}/wskazniki", headers=h, json={"wskazniki": {w2: None}}).json()
    s = next(x for x in stan["kryteria"] if x["kompetencja_id"] == k["kompetencja_id"])["sugestia"]
    assert s["status"] == "NIEWYSTARCZAJACE_DANE"


def test_bledne_zapisy_wskaznikow(klient, naglowek):
    h = naglowek("przelozony2")
    proces = _proces_z_krokiem2(klient, naglowek, "P-103", "okresowa", "przelozony2")
    url = f"/api/procesy/{proces['id']}/ocena/wskazniki"
    assert klient.put(url, headers=h, json={"wskazniki": {"negocjowanie.1": {"poziom": 5}}}).status_code == 422
    k = klient.get(f"/api/procesy/{proces['id']}/ocena", headers=h).json()["kryteria"][0]
    w = k["wskazniki"][0]["wskaznik_id"]
    for zle in ({"poziom": 5, "brak_podstaw": True}, {"poziom": 6},
                {"poziom": 5, "przyklady": [{"sytuacja": "", "dzialanie": "D", "rezultat": "R"}]}):
        assert klient.put(url, headers=h, json={"wskazniki": {w: zle}}).status_code == 422, zle


def test_uprawnienia_oceny(klient, naglowek):
    proces = _proces_z_krokiem2(klient, naglowek, "P-103", "okresowa", "przelozony2")
    url = f"/api/procesy/{proces['id']}/ocena"
    assert klient.get(url, headers=naglowek("hr")).status_code == 403
    assert klient.get(url, headers=naglowek("przelozony1")).status_code == 403
    body = {"decyzje": {}}
    assert klient.put(f"{url}/decyzje", headers=naglowek("hr"), json=body).status_code == 403
    assert klient.get("/api/procesy/99999/ocena", headers=naglowek("przelozony2")).status_code == 404


def test_pierwsza_ocena_skala_3_5_7(klient, naglowek):
    h = naglowek("przelozony1")
    proces = _proces_z_krokiem2(klient, naglowek, "P-203", "pierwsza", "przelozony1")
    url = f"/api/procesy/{proces['id']}/ocena"
    stan = klient.get(url, headers=h).json()
    assert stan["skala"]["punkty"] == [3, 5, 7] and stan["mapowanie"] is not None
    k = stan["kryteria"][0]
    w1, w2 = (w["wskaznik_id"] for w in k["wskazniki"])
    stan = klient.put(f"{url}/wskazniki", headers=h, json={"wskazniki": {
        w1: {"poziom": 9, "przyklady": [{"sytuacja": "S", "dzialanie": "D", "rezultat": "R"}]},
        w2: {"poziom": 9, "przyklady": [{"sytuacja": "S", "dzialanie": "D", "rezultat": "R"}]},
    }}).json()
    s = stan["kryteria"][0]["sugestia"]
    assert s["poziom_modelu"] == 9 and s["punkty"] == 7
    r = klient.put(f"{url}/decyzje", headers=h, json={"decyzje": {k["kompetencja_id"]: {"punkty": 9}}})
    assert r.status_code == 422  # 9 pkt nie istnieje w pierwszej ocenie


def test_decyzja_przy_niewystarczajacych_danych_bez_uzasadnienia(konf):
    from kompas_mc.ocena import KryteriumOceny, StanOceny

    s = sugestia([None, None], "okresowa", konf)
    stan = StanOceny.model_construct(
        sciezka="okresowa",
        kryteria=[KryteriumOceny(kompetencja_id="k", nazwa="K", rodzaj="OBOWIAZKOWE", wskazniki=[],
                                 sugestia=s, decyzja=None)],
    )
    wynik = scal_decyzje({}, ZapisDecyzji(decyzje={"k": {"punkty": 3}}), stan, konf, "x", datetime.now(UTC))
    assert wynik["k"].zgodna_z_sugestia is None
    with pytest.raises(BladOceny):
        scal_decyzje({}, ZapisDecyzji(decyzje={"zzz": {"punkty": 3}}), stan, konf, "x", datetime.now(UTC))


def test_uwagi_zastepuja_przyklad_w_ostrzezeniu(konf):
    """Uwagi z rozmowy przy wskaźniku zdejmują ostrzeżenie o poziomie innym niż oczekiwany bez przykładu."""
    assert ostrzezenia_wskaznika(OcenaWskaznika(poziom=7), konf)
    assert not ostrzezenia_wskaznika(OcenaWskaznika(poziom=7, uwagi="Wyjaśniła akt UODO prostym językiem."), konf)
    assert ostrzezenia_wskaznika(OcenaWskaznika(poziom=7, uwagi="   "), konf)


def test_zapis_rozmowy_i_zakonczenie(klient, naglowek):
    """Rozmowa oceniająca (§ 10) zapisuje się w API, a data przy komplecie ocen kończy ją (krok 6)."""
    h = naglowek("przelozony2")
    proces = _proces_z_krokiem2(klient, naglowek, "P-103", "okresowa", "przelozony2")
    url = f"/api/procesy/{proces['id']}/ocena"
    body = {"notatki": {"obowiazki": "Omówiono trzy zadania z OSP."}, "mocne_strony": "Jasne pisma."}
    r = klient.put(f"{url}/rozmowa", json=body, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["rozmowa"]["notatki"]["obowiazki"] == "Omówiono trzy zadania z OSP."
    assert klient.get(url, headers=h).json()["rozmowa"]["mocne_strony"] == "Jasne pisma."
    jutro = (date.today() + timedelta(days=1)).isoformat()
    assert klient.put(f"{url}/rozmowa", json={"data": jutro}, headers=h).status_code == 422
    assert klient.put(f"{url}/rozmowa", json={"notatki": {"inne": "x"}}, headers=h).status_code == 422
    stan = klient.get(url, headers=h).json()
    for kr in stan["kryteria"]:
        klient.put(f"{url}/decyzje", json={kr["kompetencja_id"]: {"punkty": 5}}, headers=h)
    r = klient.put(f"{url}/rozmowa", json={**body, "data": date.today().isoformat()}, headers=h)
    assert r.status_code == 200, r.text
    assert klient.get(f"/api/procesy/{proces['id']}", headers=h).json()["krok"] >= 6
    assert klient.put(f"{url}/rozmowa", json={}, headers=naglowek("hr")).status_code == 403


def test_przyklad_z_pola_uwag_liczy_sie_dla_rozwoju(klient, naglowek):
    """#72 pkt 7: przykład wpisany przy wskaźniku (pole uwag) trafia do propozycji rozwoju."""
    h = naglowek("przelozony2")
    proces = _proces_z_krokiem2(klient, naglowek, "P-103", "okresowa", "przelozony2")
    url = f"/api/procesy/{proces['id']}/ocena"
    w = klient.get(url, headers=h).json()["kryteria"][0]["wskazniki"][0]["wskaznik_id"]
    r = klient.put(f"{url}/wskazniki", json={"wskazniki": {w: {"poziom": 7, "uwagi": "Przygotowała opinię w 2 dni."}}}, headers=h)
    assert r.status_code == 200, r.text
    dla = {x["wskaznik_id"]: x for x in r.json()["dla_rozwoju"]}
    assert dla[w]["przyklady"] == ["Przygotowała opinię w 2 dni."]
