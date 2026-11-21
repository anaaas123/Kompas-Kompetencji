"""Asystent rozmowy (#35, krok 6): plan rozmowy jako sugestia, z powiązaniem i uzasadnieniem."""

from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from kompas_core.zrodla.cli import main as waliduj

from kompas_mc.app import utworz_aplikacje
from kompas_mc.ustawienia import KATALOG_MC


@pytest.fixture(scope="module")
def klient(ustawienia, tmp_path_factory):
    """Własna baza: inne testy zostawiają procesy w toku (jedna osoba = jeden proces)."""
    dane = tmp_path_factory.mktemp("rozmowa")
    ust = replace(ustawienia, baza=dane / "rozmowa.db", log_llm=dane / "llm.jsonl")
    with TestClient(utworz_aplikacje(ust)) as k:
        yield k


@pytest.fixture(scope="module")
def naglowek(klient):
    def zaloguj(login: str) -> dict:
        r = klient.post("/api/auth/login", json={"login": login, "hasło": "demo"})
        assert r.status_code == 200
        return {"Authorization": f"Bearer {r.json()['token']}"}

    return zaloguj

PRZYKLAD = {
    "sytuacja": "Pilna opinia do projektu rozporządzenia",
    "dzialanie": "Przygotowała analizę z wariantami",
    "rezultat": "Stanowisko przyjęte bez poprawek",
    "powtarzalnosc": "REGULARNE",
    "zlozonosc": "WYSOKA",
}


def _proces(klient, naglowek, osoba_id, sciezka, login="przelozony1"):
    h = naglowek(login)
    proces = next(
        (p for p in klient.get("/api/procesy", headers=h).json()
         if p["osoba_id"] == osoba_id and p["sciezka"] == sciezka and p["status"] == "W_TOKU"),
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
            for k in p["kryteria"] if k["rodzaj"] == "OBOWIAZKOWE"
        }
        r = klient.put(f"/api/procesy/{proces['id']}/krok2", json={"wskazniki": wsk}, headers=h)
        assert r.status_code == 200, r.text
        proces = r.json()
    return proces


def _okresowa_z_ocenami(klient, naglowek):
    """P-104 (radca, arkusz C): kryterium 0 – mocna strona i brak podstaw; kryterium 1 –
    sugestia 5, decyzja 1 (odchylenie o 2 poziomy i „znacznie poniżej”); kryterium 2 – poziom 3."""
    h = naglowek("przelozony1")
    proces = _proces(klient, naglowek, "P-104", "okresowa")
    url = f"/api/procesy/{proces['id']}/ocena"
    stan = klient.get(url, headers=h).json()
    k0, k1, k2 = stan["kryteria"][:3]
    (a, b), (c, d), (e, f) = ([w["wskaznik_id"] for w in k["wskazniki"][:2]] for k in (k0, k1, k2))
    r = klient.put(f"{url}/wskazniki", headers=h, json={"wskazniki": {
        a: {"poziom": 9, "przyklady": [PRZYKLAD]},
        b: {"brak_podstaw": True},
        c: {"poziom": 5, "przyklady": [PRZYKLAD]},
        d: {"poziom": 5, "przyklady": [PRZYKLAD]},
        e: {"poziom": 3, "przyklady": [PRZYKLAD]},
        f: {"poziom": 3, "przyklady": [PRZYKLAD]},
    }})
    assert r.status_code == 200, r.text
    r = klient.put(f"{url}/decyzje", headers=h, json={"decyzje": {
        k1["kompetencja_id"]: {"punkty": 1, "uzasadnienie": "Test odchylenia od sugestii."},
    }})
    assert r.status_code == 200, r.text
    return proces, r.json(), (k0, k1, k2), (a, b, e)


def test_plan_rozmowy_okresowej(klient, naglowek, korpus_mc):
    h = naglowek("przelozony1")
    proces, stan_przed, (k0, k1, k2), (mocny, brak, slaby) = _okresowa_z_ocenami(klient, naglowek)
    r = klient.post(f"/api/procesy/{proces['id']}/rozmowa", headers=h, json={})
    assert r.status_code == 200, r.text
    plan = r.json()

    # wszystko jest sugestią, bez modelu językowego
    assert plan["status"].startswith("SUGESTIA") and plan["tryb"] == "SZABLONY"
    assert "do edycji" in plan["oznaczenie"]

    # zakres z § 10 rozp. 2016; bez celów nie ma punktu o celach
    assert [z["id"] for z in plan["zakres"]] == ["zakres.okresowa.obowiazki", "zakres.okresowa.rozwoj"]

    # każde pytanie ma uzasadnienie, powiązanie i źródło (kryterium #35)
    assert plan["pytania"]
    for p in plan["pytania"]:
        assert p["uzasadnienie"].strip() and p["adnotacje"], p
        typ = p["powiazanie"]["typ"]
        assert typ in {"wskaznik", "przyklad", "zadanie_osp", "przepis"}
        if typ in {"wskaznik", "przyklad"}:
            assert p["powiazanie"]["wskaznik_id"]
        if typ == "zadanie_osp":
            assert p["powiazanie"]["zadanie_osp"] >= 1
    szablony = {p["szablon"] for p in plan["pytania"]}
    assert {"pyt.osp.zadanie", "pyt.wskaznik.powtarzalnosc", "pyt.wskaznik.standard", "pyt.rozwoj.okresowa"} <= szablony
    assert "Pilna opinia" in next(p["tresc"] for p in plan["pytania"] if p["szablon"] == "pyt.wskaznik.powtarzalnosc")

    # argument: zachowanie dosłownie z modelu, źródło w korpusie
    arg = next(a for a in plan["argumenty"] if a["wskaznik_id"] == mocny)
    assert arg["poziom"] == 9 and arg["rezultat"] == PRZYKLAD["rezultat"]
    zr = arg["zachowanie_zrodlo"]
    zrodlo = next(
        f for f in korpus_mc.korpus.fragmenty
        if f.doc_id == "model-kompetencji" and f.lokalizator == zr["lokalizator"]
    )
    assert zr["doc_id"] == "model-kompetencji"
    assert arg["zachowanie"] == " ".join(zrodlo.tekst.split())

    # szkic informacji zwrotnej
    nazwa = lambda k: k["wskazniki"][0]["nazwa"].rstrip(".")  # noqa: E731
    assert any(nazwa(k0) in s for s in plan["informacja_zwrotna"]["mocne_strony"])
    assert any(nazwa(k2) in s for s in plan["informacja_zwrotna"]["obszary_rozwoju"])
    assert not any(".:" in s or ".”." in s for s in sum(plan["informacja_zwrotna"].values(), []))
    tresci = [p["tresc"] for p in plan["pytania"]]
    assert len(tresci) == len(set(tresci))  # ten sam przykład nie powtarza pytania

    # kwestie do omówienia
    kw = {(k["id"], k.get("wskaznik_id") or k.get("kompetencja")) for k in plan["kwestie"]}
    assert ("kwestia.brak-podstaw", brak) in kw
    assert ("kwestia.odchylenie-od-sugestii", k1["nazwa"]) in kw
    assert ("kwestia.znacznie-ponizej", k1["nazwa"]) in kw
    assert all(k["adnotacje"] for k in plan["kwestie"])

    # plan nie zmienia ocen
    stan_po = klient.get(f"/api/procesy/{proces['id']}/ocena", headers=h).json()
    assert stan_po["kryteria"] == stan_przed["kryteria"]


def test_cele_dodaja_punkt_zakresu_i_pytanie(klient, naglowek):
    h = naglowek("przelozony1")
    proces, *_ = _okresowa_z_ocenami(klient, naglowek)
    plan = klient.post(
        f"/api/procesy/{proces['id']}/rozmowa", headers=h, json={"cele": ["Wdrożenie rejestru opinii"]}
    ).json()
    assert "zakres.okresowa.cele" in [z["id"] for z in plan["zakres"]]
    assert any(p["szablon"] == "pyt.cele" and "rejestru opinii" in p["tresc"] for p in plan["pytania"])


def test_plan_rozmowy_pierwszej_oceny(klient, naglowek):
    h = naglowek("przelozony1")
    proces = _proces(klient, naglowek, "P-203", "pierwsza")
    url = f"/api/procesy/{proces['id']}/ocena"
    stan = klient.get(url, headers=h).json()
    w = {k["kompetencja_id"]: [x["wskaznik_id"] for x in k["wskazniki"]] for k in stan["kryteria"]}
    klient.put(f"{url}/wskazniki", headers=h, json={"wskazniki": {
        i: {"poziom": 3, "przyklady": [PRZYKLAD]} for ids in list(w.values())[:2] for i in ids
    }})
    kryt = [k["kompetencja_id"] for k in stan["kryteria"][:2]]
    r = klient.put(f"{url}/decyzje", headers=h, json={"decyzje": {
        k: {"punkty": 3, "uzasadnienie": "Test."} for k in kryt
    }})
    assert r.status_code == 200, r.text

    plan = klient.post(f"/api/procesy/{proces['id']}/rozmowa", headers=h, json={
        "sprawozdanie_zlozone_w_terminie": False,
        "egzamin_obowiazkowy": False,
        "fragment_sprawozdania": "Opracowanie analizy barier prawnych",
    }).json()
    zakres = [z["id"] for z in plan["zakres"]]
    assert "zakres.pierwsza.sprawozdanie" in zakres and "zakres.pierwsza.egzamin" not in zakres
    szablony = {p["szablon"] for p in plan["pytania"]}
    assert "pyt.sprawozdanie" in szablony and "pyt.rozwoj.pierwsza" in szablony
    assert "pyt.osp.zadanie" not in szablony and "pyt.cele" not in szablony
    ids = {k["id"] for k in plan["kwestie"]}
    assert {"kwestia.sprawozdanie-niezlozone", "kwestia.dwie-oceny-3pkt"} <= ids
    assert "kwestia.znacznie-ponizej" not in ids  # tylko ocena okresowa


def test_uprawnienia_planu(klient, naglowek):
    proces, *_ = _okresowa_z_ocenami(klient, naglowek)
    url = f"/api/procesy/{proces['id']}/rozmowa"
    assert klient.post(url, json={}).status_code == 401
    assert klient.post(url, json={}, headers=naglowek("hr")).status_code == 403
    assert klient.post(url, json={}, headers=naglowek("oceniany")).status_code == 403
    assert klient.post(url, json={}, headers=naglowek("przelozony2")).status_code == 403
    assert klient.post("/api/procesy/999999/rozmowa", json={}, headers=naglowek("przelozony1")).status_code == 404


def test_cytaty_konfiguracji_rozmowy_sa_w_korpusie():
    konf = KATALOG_MC / "konfiguracja"
    assert waliduj(["--manifest", str(konf / "korpus.yaml"), str(konf / "rozmowa.yaml")]) == 0


def test_dane_osobowe_nie_sa_dozwolone_dla_modelu():
    import yaml

    d = yaml.safe_load((KATALOG_MC / "konfiguracja" / "rozmowa.yaml").read_text(encoding="utf-8"))
    zakazane = set(d["dane_dla_modelu"]["zabronione"])
    assert {"imie", "nazwisko", "przyklad", "notatka", "fragment_sprawozdania"} <= zakazane
    assert not zakazane & set(d["dane_dla_modelu"]["dozwolone"])
