"""#72: zakończenie oceny okresowej po zapoznaniu ocenianego z oceną (§ 12 ust. 1 rozp. 2016)."""

from dataclasses import replace

from fastapi.testclient import TestClient
from kompas_core.pdf import znajdz_font
from test_arkusze import _json, _proces, _uzupelnienia, _zapisz_krok6, _zapisz_oceny, api_arkusza  # noqa: F401

from kompas_mc.app import utworz_aplikacje


def _ostatnia(klient, h, osoba_id):
    return next(p for p in _json(klient.get("/api/pracownicy", headers=h)) if p["osoba_id"] == osoba_id)[
        "ostatnia_ocena_okresowa"
    ]


def test_zakonczenie_zamyka_proces_i_zapisuje_ocene_w_kartotece(api_arkusza, ustawienia, tmp_path):  # noqa: F811
    klient, naglowek = api_arkusza
    h = naglowek("przelozony1")
    proces = _proces(klient, h, "P-105")
    url = f"{proces}/arkusz-okresowy"
    _zapisz_oceny(klient, h, proces)
    _zapisz_krok6(klient, h, proces)

    # Bez zatwierdzonego arkusza nie ma czego zakończyć; HR nie prowadzi oceny.
    assert klient.post(f"{url}/zakoncz", headers=h, json={}).status_code in (409, 422)
    _json(klient.put(url, headers=h, json={"pola": _uzupelnienia(), "zatwierdz": True}))
    assert klient.post(f"{url}/zakoncz", headers=naglowek("hr"), json={}).status_code == 403
    # Zapoznanie nie wcześniej niż sporządzenie (20.11.2026); bez daty – 422.
    assert klient.post(f"{url}/zakoncz", headers=h, json={"data_zapoznania_z_ocena": "2026-11-19"}).status_code == 422
    assert klient.post(f"{url}/zakoncz", headers=h, json={}).status_code == 422

    # Arkusz i wynik po zakończeniu pokazują tę samą „poprzednią ocenę” co przy zatwierdzeniu (nie zakończoną).
    poprzednia_przed = _json(klient.get(f"{proces}/wynik-okresowy", headers=h))["poprzednia_ocena"]
    arkusz_przed = {p["id"]: p["wartosc"] for s in _json(klient.get(url, headers=h))["sekcje"] for p in s["pola"]}
    zak = _json(klient.post(f"{url}/zakoncz", headers=h, json={"data_zapoznania_z_ocena": "2026-11-21"}))
    assert _json(klient.get(f"{proces}/wynik-okresowy", headers=h))["poprzednia_ocena"] == poprzednia_przed
    arkusz_po = _json(klient.get(url, headers=h))
    assert {p["id"]: p["wartosc"] for s in arkusz_po["sekcje"] for p in s["pola"]} == arkusz_przed
    assert arkusz_po["zatwierdzony"]
    assert zak["wynik"] == "pozytywna" and zak["srednia"] == "7,00"
    assert zak["data_sporzadzenia_oceny"] == "2026-11-20" and zak["data_zapoznania_z_ocena"] == "2026-11-21"
    p = _json(klient.get(proces, headers=h))
    assert p["status"] == "ZAKONCZONY" and p["krok"] == 8

    # Kartoteka (mock QNT) ma nową ostatnią ocenę; cykl liczy następny okres od ustalenia kryteriów.
    ostatnia = _ostatnia(klient, h, "P-105")
    assert ostatnia["data"] == "2026-11-20" and ostatnia["wynik"] == "pozytywna"
    etap = next(e for e in _json(klient.get("/api/cykl", headers=h)) if e["osoba_id"] == "P-105")
    assert etap["etap"] == "kryteria" and etap["proces_id"] is None

    # Zakończonej oceny nie da się zmienić ani zakończyć drugi raz; PDF dalej jest dostępny.
    assert klient.post(f"{url}/zakoncz", headers=h, json={}).status_code == 409
    assert klient.put(url, headers=h, json={"pola": _uzupelnienia()}).status_code == 409
    try:
        znajdz_font()
    except FileNotFoundError:
        pass  # bez fontu TTF z polskimi znakami PDF nie powstaje w tym środowisku
    else:
        assert klient.get(f"{url}/pdf", headers=h).status_code == 200
    # Następną ocenę można rozpocząć (wcześniej 409: proces w toku).
    assert klient.post("/api/procesy", json={"osoba_id": "P-105", "sciezka": "okresowa"}, headers=h).status_code == 201

    # Po restarcie aplikacji ocena wraca do kartoteki z bazy.
    with TestClient(utworz_aplikacje(replace(ustawienia, baza=tmp_path / "oceny.db", log_llm=tmp_path / "llm.jsonl"))) as k2:
        t = _json(k2.post("/api/auth/login", json={"login": "przelozony1", "hasło": "demo"}))["token"]
        assert _ostatnia(k2, {"Authorization": f"Bearer {t}"}, "P-105")["data"] == "2026-11-20"


def _gotowy_do_zakonczenia(klient, h, osoba="P-105", **krok6):
    proces = _proces(klient, h, osoba)
    _zapisz_oceny(klient, h, proces)
    _zapisz_krok6(klient, h, proces, **krok6)
    _json(klient.put(f"{proces}/arkusz-okresowy", headers=h, json={"pola": _uzupelnienia(), "zatwierdz": True}))
    return proces


def test_zakonczenie_odrzuca_daty_z_przyszlosci(api_arkusza):  # noqa: F811
    """Helix G3 (8): zdarzenie z przyszłości nie zamyka procesu ani nie zapisuje kartoteki."""
    klient, naglowek = api_arkusza
    h = naglowek("przelozony1")
    proces = _gotowy_do_zakonczenia(klient, h)
    r = klient.post(f"{proces}/arkusz-okresowy/zakoncz", headers=h, json={"data_zapoznania_z_ocena": "2035-01-01"})
    assert r.status_code == 422, r.text
    assert _json(klient.get(proces, headers=h))["status"] == "W_TOKU"
    assert _ostatnia(klient, h, "P-105")["data"] != "2026-11-20"


def test_zakonczenie_jedna_data_zapoznania(api_arkusza):  # noqa: F811
    """Helix G3 (7): data zapoznania zapisana w ocenie na piśmie jest wiążąca; brak daty w wyniku uzupełnia
    zakończenie, a wynik zakończonego procesu pokazuje ją i liczy termin sprzeciwu."""
    klient, naglowek = api_arkusza
    h = naglowek("przelozony1")
    proces = _gotowy_do_zakonczenia(klient, h, data_zapoznania_z_ocena="2026-11-20")
    url = f"{proces}/arkusz-okresowy/zakoncz"
    assert klient.post(url, headers=h, json={"data_zapoznania_z_ocena": "2026-11-21"}).status_code == 422
    zak = _json(klient.post(url, headers=h, json={}))
    assert zak["data_zapoznania_z_ocena"] == "2026-11-20"


def test_zakonczenie_uzupelnia_date_w_wyniku(api_arkusza):  # noqa: F811
    klient, naglowek = api_arkusza
    h = naglowek("przelozony1")
    proces = _gotowy_do_zakonczenia(klient, h)
    przed = _json(klient.get(f"{proces}/wynik-okresowy", headers=h))
    assert przed["dane"]["data_zapoznania_z_ocena"] is None
    _json(klient.post(f"{proces}/arkusz-okresowy/zakoncz", headers=h, json={"data_zapoznania_z_ocena": "2026-11-21"}))
    po = _json(klient.get(f"{proces}/wynik-okresowy", headers=h))
    assert po["dane"]["data_zapoznania_z_ocena"] == "2026-11-21"
    assert po["terminy"]["termin_sprzeciwu"] is not None
