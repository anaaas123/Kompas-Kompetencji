"""Krok 2 (#30): model kompetencji, kryteria obowiązkowe i dodatkowe, wskaźniki z zadaniami OSP."""

from datetime import UTC, date, datetime, timedelta

import pytest
from kompas_core.zrodla import cytat_w_korpusie, cytat_w_tekscie

from kompas_mc.kompetencje import odczytaj
from kompas_mc.krok2 import BladWyboru, KonfiguracjaKroku2, ZapisKroku2, zaproponuj, zatwierdz
from kompas_mc.osp import KatalogOsp


@pytest.fixture(scope="module")
def model(korpus_mc):
    return odczytaj(korpus_mc)


@pytest.fixture(scope="module")
def konf(ustawienia):
    return KonfiguracjaKroku2.z_pliku(ustawienia.krok2)


def _zal1(korpus_mc, doc_id):
    return [
        f
        for f in korpus_mc.korpus.fragmenty
        if f.doc_id == doc_id and (f.lokalizator or "").startswith("zał. 1")
    ]


def _proces(klient, naglowek, osoba_id, sciezka, login):
    h = naglowek(login)
    for p in klient.get("/api/procesy", headers=h).json():
        if p["osoba_id"] == osoba_id and p["status"] == "W_TOKU":
            return p
    r = klient.post("/api/procesy", json={"osoba_id": osoba_id, "sciezka": sciezka}, headers=h)
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------- model kompetencji


def test_model_14_49_5(model):
    assert len(model.kompetencje) == 14
    assert model.liczba_wskaznikow == 49
    for k in model.kompetencje:
        for w in k.wskazniki:
            assert [p.poziom for p in w.poziomy] == [1, 3, 5, 7, 9]
            assert w.poziomy[2].etykieta == "Na poziomie oczekiwań"


def test_nazwy_wskaznikow_doslownie_w_zal1_rozp_2016(model, korpus_mc):
    """Każdy wskaźnik jest w opisie swojego kryterium w zał. 1 rozp. 2016."""
    zal1 = _zal1(korpus_mc, "rozp-2016-okresowe")
    for k in model.kompetencje:
        for w in k.wskazniki:
            fr = [f for f in zal1 if cytat_w_tekscie(w.nazwa, f.tekst)]
            assert fr, w.nazwa
            assert any(cytat_w_tekscie(k.nazwa.split()[0], f.tekst.upper()) for f in fr), (k.nazwa, w.nazwa)


def test_nazwy_wskaznikow_pierwszej_oceny_doslownie_w_zal1_rozp_2015(model, konf, korpus_mc):
    for k_id in konf.obowiazkowe["PIERWSZA"].kompetencje:
        for w in model.kompetencja(k_id).wskazniki:
            assert cytat_w_korpusie(w.nazwa, korpus_mc.korpus, "rozp-2015-pierwsza"), w.nazwa


def test_api_model_kompetencji(klient, naglowek):
    r = klient.get("/api/model-kompetencji", headers=naglowek("przelozony1"))
    assert r.status_code == 200
    m = r.json()
    assert len(m["kompetencje"]) == 14
    assert sum(len(k["wskazniki"]) for k in m["kompetencje"]) == 49
    assert m["instrukcja"][0]["tekst"].startswith("Dobierz wskaźniki do zadań")
    assert klient.get("/api/model-kompetencji").status_code == 401


# ---------------------------------------------------------------- propozycja kryteriów


@pytest.mark.parametrize(
    ("arkusz", "sciezka", "obowiazkowe"),
    [
        ("C", "okresowa", {"wykorzystywanie-wiedzy-i-doskonalenie-zawodowe", "rzetelnosc"}),
        ("B", "okresowa", {"zarzadzanie-ludzmi", "podejmowanie-decyzji-i-odpowiedzialnosc"}),
        ("PIERWSZA", "pierwsza", {"rzetelnosc", "wykorzystywanie-wiedzy-i-doskonalenie-zawodowe"}),
    ],
)
def test_kryteria_obowiazkowe_wedlug_arkusza(model, konf, korpus_mc, arkusz, sciezka, obowiazkowe):
    kat = KatalogOsp(korpus_mc)
    doc = konf.podstawa_wskaznikow[sciezka]
    p = zaproponuj(1, sciezka, arkusz, kat.po_symbolu("DSI WWI 5"), model, _zal1(korpus_mc, doc), konf)
    obow = {k.kompetencja_id for k in p.kryteria if k.rodzaj == "OBOWIAZKOWE"}
    wspolne = {"organizacja-pracy-i-orientacja-na-osiaganie-celow", "wspolpraca", "komunikacja"}
    assert obow == obowiazkowe | wspolne
    assert [k.rodzaj for k in p.kryteria[:5]] == ["OBOWIAZKOWE"] * 5


def test_pierwsza_ocena_bez_kryteriow_dodatkowych(model, konf, korpus_mc):
    kat = KatalogOsp(korpus_mc)
    p = zaproponuj(
        1, "pierwsza", "PIERWSZA", kat.po_symbolu("DC WZKSOiC 6"), model,
        _zal1(korpus_mc, "rozp-2015-pierwsza"), konf,
    )
    assert p.limit_dodatkowych == 0
    assert {k.rodzaj for k in p.kryteria} == {"OBOWIAZKOWE", "NIEDOSTEPNE"}
    assert p.podstawa_dodatkowych[0].lokalizator == "§ 2"
    for k in p.kryteria:
        if k.rodzaj == "OBOWIAZKOWE":
            for w in k.wskazniki:
                assert w.podstawa and w.podstawa.doc_id == "rozp-2015-pierwsza"


def test_propozycje_dodatkowych_z_osp(model, konf, korpus_mc):
    kat = KatalogOsp(korpus_mc)
    p = zaproponuj(
        1, "okresowa", "C", kat.po_symbolu("DC WZKSOiC 6"), model,
        _zal1(korpus_mc, "rozp-2016-okresowe"), konf,
    )
    proponowane = [k for k in p.kryteria if k.rodzaj == "DODATKOWE_PROPONOWANE"]
    assert 0 < len(proponowane) <= 3
    ids = [k.kompetencja_id for k in proponowane]
    assert ids[0] == "radzenie-sobie-w-sytuacjach-kryzysowych"
    analityczne = next(k for k in proponowane if k.kompetencja_id == "myslenie-analityczne")
    assert "kompetencja miękka wymagana w OSP" in analityczne.propozycja.powody
    assert all(k.propozycja and k.propozycja.punkty > 0 for k in proponowane)


def test_wskaznik_pokazuje_zadania_z_osp(model, konf, korpus_mc):
    kat = KatalogOsp(korpus_mc)
    p = zaproponuj(
        1, "okresowa", "C", kat.po_symbolu("DC WZKSOiC 6"), model,
        _zal1(korpus_mc, "rozp-2016-okresowe"), konf,
    )
    kryzys = next(k for k in p.kryteria if k.kompetencja_id == "radzenie-sobie-w-sytuacjach-kryzysowych")
    w = kryzys.wskazniki[0]
    assert w.proponowany and w.zadania
    z = w.zadania[0]
    assert z.nr == 1 and z.rodzaj == "DOMINUJACE" and "kryzys" in z.slowa
    assert z.adnotacja.doc_id == "osp-starszy-specjalista"
    assert cytat_w_korpusie(z.adnotacja.cytat_doslowny, korpus_mc.korpus, z.adnotacja.doc_id)


def test_metodyka_oznaczona_jako_decyzja_projektowa(model, konf, korpus_mc):
    p = zaproponuj(1, "okresowa", "C", None, model, _zal1(korpus_mc, "rozp-2016-okresowe"), konf)
    assert "DECYZJA_PROJEKTOWA" in p.metodyka.status and "wymaga zatwierdzenia" in p.metodyka.status
    # bez OSP: brak zadań, więc brak propozycji dodatkowych i wskaźników
    assert not any(k.rodzaj == "DODATKOWE_PROPONOWANE" for k in p.kryteria)
    assert not any(w.proponowany for k in p.kryteria for w in k.wskazniki)


# ---------------------------------------------------------------- walidacja wyboru


def _wszystkie_wskazniki(model, ids):
    return {k: [w.id for w in model.kompetencja(k).wskazniki] for k in ids}


def _zatwierdz(model, konf, dodatkowe, wskazniki, sciezka="okresowa", arkusz="C"):
    return zatwierdz(
        ZapisKroku2(dodatkowe=dodatkowe, wskazniki=wskazniki),
        sciezka, arkusz, model, konf, "przelozony1", datetime.now(UTC),
    )


def test_limit_3_dodatkowych(model, konf):
    obow = konf.obowiazkowe["C"].kompetencje
    dod = ["kreatywnosc", "negocjowanie", "myslenie-analityczne", "wystapienia-publiczne"]
    with pytest.raises(BladWyboru) as e:
        _zatwierdz(model, konf, dod, _wszystkie_wskazniki(model, obow + dod))
    assert any("Najwyżej 3" in b for b in e.value.args[0])
    w = _zatwierdz(model, konf, dod[:3], _wszystkie_wskazniki(model, obow + dod[:3]))
    assert [k.rodzaj for k in w.kryteria].count("DODATKOWE") == 3


def test_pierwsza_ocena_odrzuca_dodatkowe(model, konf):
    obow = konf.obowiazkowe["PIERWSZA"].kompetencje
    with pytest.raises(BladWyboru) as e:
        _zatwierdz(
            model, konf, ["kreatywnosc"], _wszystkie_wskazniki(model, [*obow, "kreatywnosc"]),
            sciezka="pierwsza", arkusz="PIERWSZA",
        )
    assert any("Pierwsza ocena nie przewiduje" in b for b in e.value.args[0])


def test_bledne_wybory(model, konf):
    obow = konf.obowiazkowe["C"].kompetencje
    wsk = _wszystkie_wskazniki(model, obow)
    with pytest.raises(BladWyboru, match="obowiązkowym"):
        _zatwierdz(model, konf, ["rzetelnosc"], wsk)
    with pytest.raises(BladWyboru, match="nie należą"):
        _zatwierdz(model, konf, [], {**wsk, "rzetelnosc": ["komunikacja.1"]})
    with pytest.raises(BladWyboru, match="nie ma żadnego wskaźnika"):
        _zatwierdz(model, konf, [], {**wsk, "rzetelnosc": []})
    with pytest.raises(BladWyboru, match="nie jest wybrane"):
        _zatwierdz(model, konf, [], {**wsk, "kreatywnosc": ["kreatywnosc.1"]})
    with pytest.raises(BladWyboru, match="Nieznane"):
        _zatwierdz(model, konf, ["xyz"], wsk)


# ---------------------------------------------------------------- API procesu


def test_api_krok2_i_zapis(klient, naglowek, model, konf):
    proces = _proces(klient, naglowek, "P-102", "okresowa", "przelozony2")
    h = naglowek("przelozony2")
    r = klient.get(f"/api/procesy/{proces['id']}/krok2", headers=h)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["arkusz"] == "C" and p["limit_dodatkowych"] == 3 and p["wybor"] is None
    proponowane = [k["kompetencja_id"] for k in p["kryteria"] if k["rodzaj"] == "DODATKOWE_PROPONOWANE"]
    obow = [k["kompetencja_id"] for k in p["kryteria"] if k["rodzaj"] == "OBOWIAZKOWE"]

    wskazniki = {
        k["kompetencja_id"]: [w["wskaznik_id"] for w in k["wskazniki"] if w["proponowany"]]
        or [k["wskazniki"][0]["wskaznik_id"]]
        for k in p["kryteria"]
        if k["kompetencja_id"] in obow + proponowane[:2]
    }
    body = {"dodatkowe": proponowane[:2], "wskazniki": wskazniki}
    r = klient.put(f"/api/procesy/{proces['id']}/krok2", json=body, headers=h)
    assert r.status_code == 200, r.text
    po = r.json()
    assert po["krok"] == 2 and po["krok2"]["zapisal"] == "przelozony2"
    assert [k["kompetencja_id"] for k in po["krok2"]["kryteria"]] == obow + proponowane[:2]

    p = klient.get(f"/api/procesy/{proces['id']}/krok2", headers=h).json()
    assert p["wybor"]["kryteria"][0]["kompetencja_id"] == obow[0]
    assert klient.get(f"/api/procesy/{proces['id']}", headers=h).json()["krok2"] is not None
    historia = klient.app.state.dziennik.historia("proces", str(proces["id"]))
    assert any("krok2" in w.roznica for w in historia)


def test_api_limit_i_uprawnienia(klient, naglowek):
    proces = _proces(klient, naglowek, "P-102", "okresowa", "przelozony2")
    url = f"/api/procesy/{proces['id']}/krok2"
    body = {"dodatkowe": ["kreatywnosc", "negocjowanie", "myslenie-analityczne", "wystapienia-publiczne"],
            "wskazniki": {}}
    r = klient.put(url, json=body, headers=naglowek("przelozony2"))
    assert r.status_code == 422
    assert any("Najwyżej 3" in b for b in r.json()["detail"]["bledy"])
    assert klient.put(url, json=body, headers=naglowek("hr")).status_code == 403
    assert klient.put(url, json=body, headers=naglowek("przelozony1")).status_code == 403
    assert klient.get(url, headers=naglowek("przelozony1")).status_code == 403
    assert klient.get(url, headers=naglowek("hr")).status_code == 200
    assert klient.get("/api/procesy/99999/krok2", headers=naglowek("hr")).status_code == 404


def test_api_pierwsza_ocena_bez_dodatkowych(klient, naglowek):
    proces = _proces(klient, naglowek, "P-202", "pierwsza", "przelozony1")
    h = naglowek("przelozony1")
    url = f"/api/procesy/{proces['id']}/krok2"
    p = klient.get(url, headers=h).json()
    assert p["limit_dodatkowych"] == 0
    assert not any(k["rodzaj"].startswith("DODATKOWE") for k in p["kryteria"])
    r = klient.put(url, json={"dodatkowe": ["kreatywnosc"], "wskazniki": {}}, headers=h)
    assert r.status_code == 422
    assert any("Pierwsza ocena nie przewiduje" in b for b in r.json()["detail"]["bledy"])


def test_cytaty_kroku2_sa_w_korpusie(klient, naglowek, korpus_mc):
    proces = _proces(klient, naglowek, "P-102", "okresowa", "przelozony2")
    p = klient.get(f"/api/procesy/{proces['id']}/krok2", headers=naglowek("hr")).json()
    refs = p["podstawa_obowiazkowych"] + p["podstawa_dodatkowych"] + p["metodyka"]["adnotacje"]
    for k in p["kryteria"]:
        for w in k["wskazniki"]:
            refs += [w["podstawa"]] + [z["adnotacja"] for z in w["zadania"]]
        if k["propozycja"]:
            refs += k["propozycja"]["adnotacje"]
    for ref in refs:
        if ref and ref.get("cytat_dosłowny"):
            assert cytat_w_korpusie(ref["cytat_dosłowny"], korpus_mc.korpus, ref["doc_id"]), ref


def test_zakonczenie_czesci_i_zapisuje_date_zapoznania(klient, naglowek):
    """Część I kończy się datą rozmowy i zapoznania z kryteriami (rozp. 2016 § 5 ust. 1, § 6 ust. 2)."""
    from datetime import date, timedelta

    h = naglowek("przelozony2")
    proces = _proces(klient, naglowek, "P-102", "okresowa", "przelozony2")
    url = f"/api/procesy/{proces['id']}/krok2"
    dzis = date.today().isoformat()
    p = klient.get(url, headers=h).json()
    wsk = {k["kompetencja_id"]: [w["wskaznik_id"] for w in k["wskazniki"][:1]] for k in p["kryteria"] if k["rodzaj"] == "OBOWIAZKOWE"}
    assert klient.put(url, json={"wskazniki": wsk}, headers=h).status_code == 200
    jutro = (date.today() + timedelta(days=1)).isoformat()
    assert klient.put(f"{url}/zapoznanie", json={"data": jutro}, headers=h).status_code == 422
    # Przed początkiem okresu (poprzednia ocena P-102: 16.11.2026) nie wolno; część I sprzed miesięcy na końcu
    # okresu wolno (przepisanie z podpisanej części I) — sprawdza to test cyklu poniżej.
    assert klient.put(f"{url}/zapoznanie", json={"data": "2026-11-15"}, headers=h).status_code == 422
    r = klient.put(f"{url}/zapoznanie", json={"data": dzis, "ustalenia": "  Opinie w 14 dni\nSzkolenie z AI Act  "}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["krok2"]["zapoznanie"] == dzis
    # Oczekiwania i cele z rozmowy na początku okresu (§ 5 ust. 1 pkt 3–4) zapisują się przy zakończeniu części I.
    assert r.json()["krok2"]["ustalenia"] == "Opinie w 14 dni\nSzkolenie z AI Act"
    # Nowy zapis kryteriów kasuje datę: część I trzeba podpisać od nowa.
    assert klient.put(url, json={"wskazniki": wsk}, headers=h).json()["krok2"]["zapoznanie"] is None
    assert klient.put(f"{url}/zapoznanie", json={"data": dzis}, headers=naglowek("hr")).status_code == 403


def test_czesc_i_przepisana_na_koncu_okresu(klient, naglowek):
    """#72: na końcu okresu przełożony przepisuje datę z podpisanej części I sprzed miesięcy; cykl liczy
    ustalenie kryteriów od tej daty, nie od dnia przepisania (bez błędu kolejności dat)."""
    h = naglowek("przelozony1")
    proces = _proces(klient, naglowek, "P-105", "okresowa", "przelozony1")
    url = f"/api/procesy/{proces['id']}/krok2"
    p = klient.get(url, headers=h).json()
    wsk = {k["kompetencja_id"]: [w["wskaznik_id"] for w in k["wskazniki"][:1]] for k in p["kryteria"] if k["rodzaj"] == "OBOWIAZKOWE"}
    assert klient.put(url, json={"wskazniki": wsk}, headers=h).status_code == 200
    poprzednia = klient.get("/api/pracownicy/P-105", headers=h).json()["ostatnia_ocena_okresowa"]["data"]
    rok_temu = (date.fromisoformat(poprzednia) + timedelta(days=20)).isoformat()
    r = klient.put(f"{url}/zapoznanie", json={"data": rok_temu}, headers=h)
    assert r.status_code == 200, r.text
    cykl = klient.get("/api/cykl", headers=h)
    assert cykl.status_code == 200, cykl.text
    e = {x["osoba_id"]: x for x in cykl.json()}["P-105"]
    assert e["kryteria_ustalone"] == rok_temu
    przed = (date.fromisoformat(poprzednia) - timedelta(days=1)).isoformat()
    assert klient.put(f"{url}/zapoznanie", json={"data": przed}, headers=h).status_code == 422
