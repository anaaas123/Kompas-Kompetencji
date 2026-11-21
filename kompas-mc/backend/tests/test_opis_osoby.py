"""Opis osoby na karcie pracownika (#55): fakty per rola, szablon, walidacja zdań z modelu, dane do modelu."""

import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from kompas_core.llm import Cytat, DziennikPamiec, Ekstrakcyjny, Odpowiedz, OpenAiZgodny, Tryb

from kompas_mc.app import utworz_aplikacje
from kompas_mc.cele import OZNACZENIE
from kompas_mc.opis_osoby import Fakt, opis_z_modelu, waliduj_opis

URL = "/api/pracownicy/P-104/opis"


@pytest.fixture(scope="module")
def k(ustawienia, tmp_path_factory):
    dane = tmp_path_factory.mktemp("opis")
    with TestClient(utworz_aplikacje(replace(ustawienia, baza=dane / "o.db", log_llm=dane / "llm.jsonl"))) as kl:
        yield kl


@pytest.fixture(scope="module")
def h(k):
    def zaloguj(login: str) -> dict:
        r = k.post("/api/auth/login", json={"login": login, "hasło": "demo"})
        assert r.status_code == 200
        return {"Authorization": f"Bearer {r.json()['token']}"}

    return zaloguj


def _ids(opis: dict) -> set[str]:
    return {f["id"] for z in opis["zdania"] for f in z["fakty"]}


def test_szablon_przelozonego_z_ocena_czastkowa(k, h):
    r = k.get(URL, headers=h("przelozony1"))
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["tryb"] == "SZABLON" and o["dostawca"] is None and o["odrzucone"] == []
    assert o["oznaczenie"] == OZNACZENIE
    assert 2 <= len(o["zdania"]) <= 4 and all(z["fakty"] for z in o["zdania"])
    assert "oceny_czastkowe.komunikacja" in _ids(o)
    assert any("Komunikacja – 3 pkt" in z["tekst"] for z in o["zdania"])
    assert "radca" in o["zdania"][0]["tekst"] and "2027-10-15" in o["zdania"][1]["tekst"]
    # Szablon spełnia te same zasady co zdania z modelu (liczby z faktów, bez werdyktów).
    fakty = [Fakt(**f) for z in o["zdania"] for f in z["fakty"]]
    zdania = [{"tekst": z["tekst"], "fakty": [f["id"] for f in z["fakty"]]} for z in o["zdania"]]
    assert waliduj_opis(json.dumps({"zdania": zdania}), fakty)[1] == []


def test_hr_bez_tresci_ocen(k, h):
    r = k.get(URL, headers=h("hr"))
    assert r.status_code == 200, r.text
    assert "oceny_czastkowe" not in r.text and "pkt" not in r.text
    assert "biezaca" not in r.text and "samoocena" not in r.text
    assert "ocena.ostatnia" in _ids(r.json())  # wynik i data są w danych kadrowych widocznych dla HR


def test_dostep(k, h):
    assert k.get(URL, headers=h("przelozony2")).status_code == 403
    assert k.get(URL, headers=h("oceniany")).status_code == 403
    assert k.get(URL).status_code == 401
    assert k.get("/api/pracownicy/P-999/opis", headers=h("hr")).status_code == 404


def test_pracownik_bez_biezacych_decyzji_przed_przekazaniem_samooceny(k, h):
    hp = h("przelozony1")
    pid = k.post("/api/procesy", json={"osoba_id": "P-101", "sciezka": "okresowa"}, headers=hp).json()["id"]
    k2 = k.get(f"/api/procesy/{pid}/krok2", headers=hp).json()
    wsk = {kr["kompetencja_id"]: [w["wskaznik_id"] for w in kr["wskazniki"][:1]]
           for kr in k2["kryteria"] if kr["rodzaj"] == "OBOWIAZKOWE"}
    assert k.put(f"/api/procesy/{pid}/krok2", json={"wskazniki": wsk}, headers=hp).status_code == 200
    kr = k.get(f"/api/procesy/{pid}/ocena", headers=hp).json()["kryteria"][0]
    w = kr["wskazniki"][0]["wskaznik_id"]
    k.put(f"/api/procesy/{pid}/ocena/wskazniki", headers=hp, json={"wskazniki": {w: {"poziom": 9, "przyklady": [
        {"sytuacja": "S", "dzialanie": "D", "rezultat": "R"}]}}})
    r = k.put(f"/api/procesy/{pid}/ocena/decyzje", headers=hp, json={"decyzje": {kr["kompetencja_id"]: {"punkty": 9}}})
    assert r.status_code == 200, r.text

    przelozony = k.get("/api/pracownicy/P-101/opis", headers=hp).json()
    assert "biezaca.decyzje" in _ids(przelozony)
    pracownik = k.get("/api/pracownicy/P-101/opis", headers=h("oceniany"))
    assert pracownik.status_code == 200 and "biezaca" not in pracownik.text
    assert "oceny_czastkowe.komunikacja" in _ids(pracownik.json())  # własna ostatnia ocena: ocena.tresc


def test_model_bez_klucza_zwraca_szablon(k, h, monkeypatch):
    # Konfiguracja testów ma tylko dostawcę ekstrakcyjnego, który zdań nie układa.
    o = k.get(f"{URL}?model=true", headers=h("przelozony1")).json()
    assert o["tryb"] == "SZABLON" and o["odrzucone"] == ["brak skonfigurowanego dostawcy LLM"] and o["zdania"]

    monkeypatch.delenv("KOMPAS_TEST_BRAK_KLUCZA", raising=False)
    deepseek = OpenAiZgodny(base_url="http://127.0.0.1:9", model="deepseek-v4-flash",
                            zmienna_klucza="KOMPAS_TEST_BRAK_KLUCZA")
    monkeypatch.setattr(k.app.state.asystent, "dostawcy", [deepseek])
    o = k.get(f"{URL}?model=true", headers=h("przelozony1")).json()
    assert o["tryb"] == "SZABLON" and o["dostawca"] is None and o["zdania"]
    assert o["odrzucone"] == ["openai_zgodny: brak poprawnej odpowiedzi"]  # bez szczegółów konfiguracji


# ---------------------------------------------------------------- atrapa dostawcy


class Atrapa:
    nazwa = "atrapa"
    model = "test"
    tryb = Tryb.NA_ZYWO

    def __init__(self, zdania):
        self.zdania = zdania
        self.zapytania = []

    def odpowiedz(self, zapytanie):
        self.zapytania.append(zapytanie)
        f = zapytanie.fragmenty[0]
        return Odpowiedz(
            cytaty=[Cytat(fragment_id=f.id, cytat=f.tekst)],
            tresc=json.dumps({"zdania": self.zdania}, ensure_ascii=False),
        )


FAKTY = [
    Fakt(id="cykl.termin", tekst="termin (sporządzenie oceny na piśmie): 2027-10-15, za 328 dni", zrodlo="cykl oceny"),
    Fakt(id="oceny_czastkowe.komunikacja", tekst="Komunikacja – 3 pkt", zrodlo="ostatnia ocena okresowa"),
]


def test_walidacja_zdan_modelu():
    poprawne = "Ocenę na piśmie trzeba sporządzić do 15.10.2027, za 328 dni."
    atrapa = Atrapa([
        {"tekst": poprawne, "fakty": ["cykl.termin"]},
        {"tekst": "Pracuje w zespole od lat.", "fakty": []},
        {"tekst": "Komunikacja oceniona na 4 pkt.", "fakty": ["oceny_czastkowe.komunikacja"]},
        {"tekst": "Komunikacja – 3 pkt, więc zasługuje na szkolenie.", "fakty": ["oceny_czastkowe.komunikacja"]},
        {"tekst": "Ma 3 pkt z komunikacji.", "fakty": ["nie-ma"]},
    ])
    # Ekstrakcyjny na początku łańcucha musi zostać pominięty, inaczej odpowiedziałby bez JSON.
    w = opis_z_modelu(FAKTY, [Ekstrakcyjny(), atrapa], DziennikPamiec())
    assert [z.tekst for z in w.zdania] == [poprawne] and w.zdania[0].fakty == ["cykl.termin"]
    assert w.dostawca == "atrapa" and w.tryb == Tryb.NA_ZYWO
    assert len(w.odrzucone) == 4
    assert "brak podstawy" in w.odrzucone[0]
    assert "liczby bez pokrycia" in w.odrzucone[1] and ": 4" in w.odrzucone[1]
    assert "werdykt" in w.odrzucone[2]
    assert "nie-ma" in w.odrzucone[3]


def test_limit_zdan_i_odpowiedz_bez_json():
    zdania = [{"tekst": t, "fakty": ["cykl.termin"]} for t in ("Raz.", "Dwa.", "Trzy.", "Cztery.", "Pięć.")]
    przyjete, odrzucone = waliduj_opis(json.dumps({"zdania": zdania}), FAKTY)
    assert len(przyjete) == 4 and len(odrzucone) == 1 and "limit" in odrzucone[0]
    assert waliduj_opis("To nie jest JSON", FAKTY) == ([], ["odpowiedź modelu nie zawiera listy zdań w formacie JSON"])


def test_opis_z_modelu_bez_danych_identyfikujacych(k, h, monkeypatch):
    atrapa = Atrapa([{"tekst": "Trwa okres oceny okresowej.", "fakty": ["cykl.etap"]}])
    monkeypatch.setattr(k.app.state.asystent, "dostawcy", [atrapa])
    r = k.get(f"{URL}?model=true", headers=h("przelozony1"))
    assert r.status_code == 200, r.text
    o = r.json()
    assert o["tryb"] == "NA_ŻYWO" and o["dostawca"] == "atrapa" and o["oznaczenie"] == OZNACZENIE
    assert [z["tekst"] for z in o["zdania"]] == ["Trwa okres oceny okresowej."]
    assert o["zdania"][0]["fakty"][0]["id"] == "cykl.etap" and o["zdania"][0]["fakty"][0]["zrodlo"] == "cykl oceny"

    z = atrapa.zapytania[0]
    wyslane = z.pytanie + json.dumps([f.model_dump() for f in z.fragmenty], ensure_ascii=False)
    for identyfikator in ("Michał", "Wójcik", "P-104", "P-001", "Departament", "Wydział", "radca", "kadry.stanowisko"):
        assert identyfikator not in wyslane, identyfikator
    assert {f.id for f in z.fragmenty} >= {"cykl.etap", "oceny_czastkowe.komunikacja"}
