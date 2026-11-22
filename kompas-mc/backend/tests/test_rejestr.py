"""Rejestr operacji: kto, co, komu i z jakim skutkiem (Karol 22.11 02:11, rada 3/3 CONDITIONAL_GO)."""

from __future__ import annotations

import csv
import io
import sqlite3
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from kompas_mc.app import utworz_aplikacje


@pytest.fixture(scope="module")
def klient(ustawienia, tmp_path_factory):
    dane = tmp_path_factory.mktemp("rejestr")
    with TestClient(utworz_aplikacje(replace(ustawienia, baza=dane / "r.db", log_llm=dane / "llm.jsonl"))) as k:
        yield k


def _h(klient, login: str) -> dict:
    r = klient.post("/api/auth/login", json={"login": login, "hasło": "demo"})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _wpisy(klient, **filtry) -> list[dict]:
    r = klient.get("/api/rejestr", params={**filtry, "na_stronie": 200}, headers=_h(klient, "hr"))
    assert r.status_code == 200, r.text
    return r.json()["wpisy"]


def test_zapis_odmowa_logowanie_i_odczyt(klient):
    h = _h(klient, "przelozony1")
    r = klient.post("/api/procesy", json={"osoba_id": "P-104", "sciezka": "okresowa"}, headers=h)
    assert r.status_code == 201
    pid = r.json()["id"]
    assert klient.get(f"/api/procesy/{pid}/krok2", headers=_h(klient, "oceniany")).status_code == 403
    assert klient.post("/api/auth/login", json={"login": "nieznany", "hasło": "zle-haslo"}).status_code == 401
    assert klient.get("/api/pracownicy/P-104", headers=h).status_code == 200

    wpisy = _wpisy(klient)
    start = next(w for w in wpisy if w["metoda"] == "POST" and w["trasa"] == "/api/procesy")
    assert (start["aktor_login"], start["aktor_rola"], start["wynik"], start["status"]) == ("przelozony1", "przelozony", "ok", 201)
    assert start["request_id"] and start["akcja"] and start["etykieta"]
    assert start["oceniany_osoba"] == "P-104", "osoba z treści żądania (ustaw_osobe)"
    odmowa = next(w for w in wpisy if w["wynik"] == "odmowa" and w["aktor_login"] == "oceniany")
    assert (odmowa["status"], odmowa["oceniany_osoba"]) == (403, "P-104"), "osoba oceniana z procesu"
    nieudane = next(w for w in wpisy if w["szczegoly"].get("deklarowany_login") == "nieznany")
    assert (nieudane["wynik"], nieudane["aktor_login"]) == ("odmowa", None)
    assert all("zle-haslo" not in str(w) for w in wpisy), "hasło nigdy w rejestrze"
    udane = next(w for w in wpisy if w["szczegoly"].get("deklarowany_login") == "przelozony1" and w["wynik"] == "ok")
    assert (udane["aktor_login"], udane["aktor_rola"]) == ("przelozony1", "przelozony")
    odczyt = next(w for w in wpisy if w["trasa"] == "/api/pracownicy/{osoba_id}")
    assert (odczyt["metoda"], odczyt["oceniany_osoba"]) == ("GET", "P-104")
    assert not any(w["trasa"] == "/api/zdrowie" for w in wpisy)


def test_tylko_hr_filtry_i_csv_bez_formul(klient):
    assert klient.get("/api/rejestr", headers=_h(klient, "przelozony1")).status_code == 403
    assert klient.get("/api/rejestr.csv", headers=_h(klient, "oceniany")).status_code == 403
    # osoba z parametru ścieżki trafia do kolumny „osoba_oceniana”; arkusz nie może jej wykonać jako formuły
    klient.get("/api/pracownicy/=SUM(1)", headers=_h(klient, "hr"))
    assert all(w["wynik"] == "odmowa" for w in _wpisy(klient, wynik="odmowa"))
    assert all(w["aktor_login"] == "przelozony1" for w in _wpisy(klient, uzytkownik="przelozony1"))

    r = klient.get("/api/rejestr.csv", headers=_h(klient, "hr"))
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    wiersze = list(csv.reader(io.StringIO(r.text.lstrip("﻿")), delimiter=";"))
    assert wiersze[0][:4] == ["czas", "uzytkownik", "rola", "akcja"]
    komorki = [k for w in wiersze[1:] for k in w]
    assert not any(k.startswith(("=", "+", "-", "@")) for k in komorki), "formuły zneutralizowane"
    assert "'=SUM(1)" in komorki


def test_asystent_zapisuje_tryb_bez_tresci(klient):
    r = klient.post("/api/asystent", headers=_h(klient, "przelozony1"), json={"pytanie": "Kiedy przeprowadza się rozmowę wstępną?"})
    assert r.status_code == 200
    wpis = next(w for w in _wpisy(klient) if w["trasa"] == "/api/asystent")
    assert {"tryb", "dostawca", "walidacja"} <= set(wpis["szczegoly"])
    assert "rozmowę wstępną" not in str(wpis), "bez treści pytania"


def test_tylko_dopisywanie(klient):
    baza = sqlite3.connect(klient.app.state.ustawienia.baza)
    for polecenie in ("UPDATE operacje SET wynik = 'ok'", "DELETE FROM operacje"):
        with pytest.raises(sqlite3.DatabaseError, match="tylko dopisywanie"):
            baza.execute(polecenie)
    baza.close()



def test_kazda_rejestrowana_trasa_ma_nazwe_dla_hr(klient):
    """G2 22.11: w kolumnie „Operacja” nazwa czynności, nie opis trasy z kodu. Nowa trasa = nowy wpis w ETYKIETY."""
    from kompas_mc.rejestr import ETYKIETY, czy_rejestrowac

    braki = [
        f"{m.upper()} {p}" for p, ops in klient.app.openapi()["paths"].items() for m in ops
        if czy_rejestrowac(m.upper(), p, 200) and f"{m.upper()} {p}" not in ETYKIETY
    ]
    assert not braki, braki
    assert all("`" not in e and "403" not in e for e in ETYKIETY.values())
    wpis = next(w for w in _wpisy(klient) if w["trasa"] == "/api/pracownicy/{osoba_id}")
    assert (wpis["akcja"], wpis["etykieta"]) == ("GET /api/pracownicy/{osoba_id}", "Odczyt karty pracownika")


def test_logowanie_i_cel_maja_nazwe_i_osobe_w_rejestrze(klient):
    """Przegląd zrzutów 22.11: logowanie (trasa z prefiksem /api) było „Czynnością w aplikacji”, a zatwierdzenie
    celu bez osoby w kolumnie „Dotyczy”."""
    h = {"Authorization": f"Bearer {klient.post('/api/auth/login', json={'login': 'przelozony1', 'hasło': 'demo'}).json()['token']}"}
    cel = klient.post("/api/pracownicy/P-101/cele", headers=h, json={
        "nazwa": "Cel do rejestru", "miernik": "jeden", "termin": "2027-06-30"}).json()
    klient.post(f"/api/cele/{cel['id']}/zatwierdz", headers=h)
    wpisy = _wpisy(klient)
    login = next(w for w in wpisy if w["metoda"] == "POST" and w["trasa"].endswith("/auth/login"))
    assert (login["trasa"], login["akcja"], login["etykieta"]) == ("/api/auth/login", "POST /api/auth/login", "Logowanie")
    zatw = next(w for w in wpisy if w["trasa"] == "/api/cele/{cel_id}/zatwierdz")
    assert (zatw["etykieta"], zatw["oceniany_osoba"]) == ("Zatwierdzenie celu", "P-101")
