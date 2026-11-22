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

    zak = _json(klient.post(f"{url}/zakoncz", headers=h, json={"data_zapoznania_z_ocena": "2026-11-21"}))
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
