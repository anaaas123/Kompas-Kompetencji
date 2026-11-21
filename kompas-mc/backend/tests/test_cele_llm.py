"""Podpowiedzi celów z LLM i RAG (#12): walidacja celów, fallback regułowy, pseudonimizacja zapytania."""

import json
from dataclasses import replace
from datetime import date

import pytest
from fastapi.testclient import TestClient
from kompas_core.llm import Cytat, Odpowiedz, OpenAiZgodny, Tryb
from kompas_core.zrodla import Fragment

from kompas_mc.app import utworz_aplikacje
from kompas_mc.cele_llm import waliduj_cele
from kompas_mc.kompetencje import odczytaj

DZIS = date(2026, 11, 21)


@pytest.fixture(scope="module")
def model(korpus_mc):
    return odczytaj(korpus_mc)


@pytest.fixture(scope="module")
def fragment(korpus_mc) -> Fragment:
    return next(f for f in korpus_mc.korpus.fragmenty if f.id == "poradnik-okresowa#s29")


def _cel(**zmiany) -> dict:
    return {
        "nazwa": "Rzetelne przygotowanie dokumentów",
        "opis": "Stosowanie listy kontrolnej przed przekazaniem dokumentu.",
        "miernik": "Trzy kolejne dokumenty bez istotnych poprawek",
        "termin": "2027-06-30",
        "wskaznik_id": "rzetelnosc.1",
        "fragment_id": "poradnik-okresowa#s29",
        "cytat": "Wnioski do indywidualnego programu rozwoju zawodowego",
        **zmiany,
    }


def test_cel_z_nieistniejacym_wskaznikiem_albo_cytatem_bez_pokrycia_jest_odrzucony(model, fragment):
    tresc = json.dumps({"cele": [
        _cel(),
        _cel(nazwa="Wymyślony wskaźnik", wskaznik_id="nie-ma-takiego"),
        _cel(nazwa="Zmyślony cytat", cytat="Każdy urzędnik musi ukończyć kurs coachingu"),
        _cel(nazwa="Obcy fragment", fragment_id="rozp-2016-okresowe#1"),
    ]}, ensure_ascii=False)

    przyjete, odrzucone = waliduj_cele(tresc, [fragment], model, DZIS)

    assert [c.nazwa for c in przyjete] == ["Rzetelne przygotowanie dokumentów"]
    cel = przyjete[0]
    assert cel.zrodlo == "llm" and cel.status == "propozycja" and cel.oznaczenie == "Sugestia asystenta – do edycji"
    assert cel.wskaznik_id == "rzetelnosc.1" and cel.kompetencja and cel.wskaznik
    assert cel.cytat.fragment_id == "poradnik-okresowa#s29" and cel.cytat.strona == 29
    assert cel.termin == date(2027, 6, 30)
    assert len(odrzucone) == 3
    assert any("nie-ma-takiego" in o for o in odrzucone)
    assert any("Zmyślony cytat" in o for o in odrzucone)


def test_najwyzej_trzy_cele_i_termin_z_przeszlosci_do_uzupelnienia(model, fragment):
    tresc = json.dumps({"cele": [_cel(nazwa=f"Cel {i}", termin="2020-01-01") for i in range(5)]})
    przyjete, _ = waliduj_cele(tresc, [fragment], model, DZIS)
    assert len(przyjete) == 3 and all(c.termin is None for c in przyjete)


def test_tresc_bez_json_nie_daje_celow(model, fragment):
    przyjete, odrzucone = waliduj_cele("To nie jest JSON", [fragment], model, DZIS)
    assert przyjete == [] and odrzucone


# ---------------------------------------------------------------- API z atrapą dostawcy

URL = "/api/pracownicy/P-101/cele"
PRZYKLAD = {"sytuacja": "Anna Zielińska-Demo przygotowała raport", "dzialanie": "Pominęła kontrolę",
            "rezultat": "Raport wrócił do poprawy"}


@pytest.fixture(scope="module")
def srodowisko(ustawienia, tmp_path_factory):
    """Aplikacja z procesem P-101: wskaźnik oceniony na 3 (z przykładem z nazwiskiem) i 7, jeden cel."""
    dane = tmp_path_factory.mktemp("cele-llm")
    with TestClient(utworz_aplikacje(replace(ustawienia, baza=dane / "c.db", log_llm=dane / "llm.jsonl"))) as kl:
        def h(login):
            r = kl.post("/api/auth/login", json={"login": login, "hasło": "demo"})
            return {"Authorization": f"Bearer {r.json()['token']}"}

        hp = h("przelozony1")
        pid = kl.post("/api/procesy", json={"osoba_id": "P-101", "sciezka": "okresowa"}, headers=hp).json()["id"]
        p = kl.get(f"/api/procesy/{pid}/krok2", headers=hp).json()
        wsk = {kr["kompetencja_id"]: [w["wskaznik_id"] for w in kr["wskazniki"][:1]]
               for kr in p["kryteria"] if kr["rodzaj"] == "OBOWIAZKOWE"}
        assert kl.put(f"/api/procesy/{pid}/krok2", json={"wskazniki": wsk}, headers=hp).status_code == 200
        slaby, mocny = [w for lista in wsk.values() for w in lista][:2]
        r = kl.put(f"/api/procesy/{pid}/ocena/wskazniki", headers=hp, json={"wskazniki": {
            slaby: {"poziom": 3, "przyklady": [PRZYKLAD]}, mocny: {"poziom": 7, "przyklady": [PRZYKLAD]}}})
        assert r.status_code == 200, r.text
        r = kl.post(URL, headers=hp, json={"nazwa": "Mentoring dla Anny Zielińskiej-Demo", "opis": "Z P-001",
                                           "miernik": "Spotkania co miesiąc", "termin": "2027-03-31"})
        assert r.status_code == 201, r.text
        yield kl, h, slaby


class Atrapa:
    nazwa = "atrapa"
    model = "test"
    tryb = Tryb.NA_ZYWO

    def __init__(self, cele):
        self.cele = cele
        self.zapytania = []

    def odpowiedz(self, zapytanie):
        self.zapytania.append(zapytanie)
        poradnik = next(f for f in zapytanie.fragmenty if f.id == "poradnik-okresowa#s29")
        cytat = "Wnioski do indywidualnego programu rozwoju zawodowego"
        cele = [{**c, "fragment_id": poradnik.id, "cytat": c.get("cytat", cytat)} for c in self.cele]
        return Odpowiedz(
            cytaty=[Cytat(fragment_id=poradnik.id, cytat=cytat)],
            wybor=[c["wskaznik_id"] for c in self.cele if c["wskaznik_id"] in zapytanie.katalog],
            tresc=json.dumps({"cele": cele}, ensure_ascii=False),
        )


def _z_dostawcami(kl, dostawcy):
    stan = kl.app.state.cele_llm
    poprzedni, stan.dostawcy = stan.dostawcy, dostawcy
    return poprzedni


def test_podpowiedzi_z_llm_odrzucaja_niepoprawny_cel_i_nie_zawieraja_danych_identyfikujacych(srodowisko):
    kl, h, slaby = srodowisko
    hp = h("przelozony1")
    atrapa = Atrapa([
        {"nazwa": "Lista kontrolna", "opis": "Sprawdzanie dokumentu", "miernik": "3 dokumenty bez poprawek",
         "termin": "2027-06-30", "wskaznik_id": slaby},
        {"nazwa": "Zmyślony", "opis": "", "miernik": "x", "termin": "2027-06-30", "wskaznik_id": "nie-ma"},
    ])
    poprzedni = _z_dostawcami(kl, [atrapa])
    try:
        r = kl.get(f"{URL}/podpowiedzi", headers=hp)
    finally:
        _z_dostawcami(kl, poprzedni)

    assert r.status_code == 200, r.text
    wynik = r.json()
    assert wynik["zrodlo"] == "llm" and wynik["dostawca"] == "atrapa"
    assert [p["nazwa"] for p in wynik["podpowiedzi"]] == ["Lista kontrolna"]
    pod = wynik["podpowiedzi"][0]
    assert pod["status"] == "propozycja" and pod["oznaczenie"] == "Sugestia asystenta – do edycji"
    assert pod["cytat"]["fragment_id"] == "poradnik-okresowa#s29"
    assert len(wynik["odrzucone"]) == 1 and "nie-ma" in wynik["odrzucone"][0]
    assert len(kl.get(URL, headers=hp).json()["cele"]) == 1  # podpowiedź nie zapisuje się sama

    z = atrapa.zapytania[0]
    assert slaby in z.katalog
    assert {f.doc_id for f in z.fragmenty} >= {"model-kompetencji", "poradnik-okresowa"}
    tekst = z.pytanie + json.dumps(z.katalog, ensure_ascii=False)
    for identyfikator in ("Anna", "Anny", "Zielińsk", "P-101", "P-001", "Departament", "Wydział"):
        assert identyfikator not in tekst, identyfikator
    assert "Oceniany" in z.pytanie and "Mentoring dla" in z.pytanie and "Raport wrócił" in z.pytanie


def test_bez_klucza_zwracane_sa_podpowiedzi_regulowe(srodowisko, monkeypatch):
    kl, h, slaby = srodowisko
    monkeypatch.delenv("KOMPAS_TEST_BRAK_KLUCZA", raising=False)
    deepseek = OpenAiZgodny(base_url="http://127.0.0.1:9", model="deepseek-v4-flash",
                            zmienna_klucza="KOMPAS_TEST_BRAK_KLUCZA")
    poprzedni = _z_dostawcami(kl, [deepseek])
    try:
        wynik = kl.get(f"{URL}/podpowiedzi", headers=h("przelozony1")).json()
    finally:
        _z_dostawcami(kl, poprzedni)

    assert wynik["zrodlo"] == "reguly"
    assert [p["wskaznik_id"] for p in wynik["podpowiedzi"]] == [slaby]
    assert wynik["podpowiedzi"][0]["zrodlo"] == "reguly"
    assert any("KOMPAS_TEST_BRAK_KLUCZA" in o for o in wynik["odrzucone"])


def test_gdy_llm_zwroci_same_niepoprawne_cele_zostaja_regulowe(srodowisko):
    kl, h, slaby = srodowisko
    atrapa = Atrapa([{"nazwa": "Zły cytat", "miernik": "x", "wskaznik_id": slaby, "cytat": "tego nie ma w poradniku"}])
    poprzedni = _z_dostawcami(kl, [atrapa])
    try:
        wynik = kl.get(f"{URL}/podpowiedzi", headers=h("przelozony1")).json()
    finally:
        _z_dostawcami(kl, poprzedni)
    assert wynik["zrodlo"] == "reguly" and wynik["podpowiedzi"][0]["zrodlo"] == "reguly"
    assert any("bez pokrycia" in o for o in wynik["odrzucone"])
