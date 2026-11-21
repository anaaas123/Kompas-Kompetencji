"""Cele rozwojowe (#10): przejścia statusów dla obu wartości przełącznika, uprawnienia, podpowiedzi regułowe."""

from dataclasses import replace

import pytest
import yaml
from fastapi.testclient import TestClient

from kompas_mc.app import utworz_aplikacje

CEL = {
    "nazwa": "Lepsza komunikacja pisemna",
    "opis": "Pisanie krótszych i jaśniejszych notatek służbowych.",
    "miernik": "Trzy notatki przyjęte bez poprawek redakcyjnych",
    "termin": "2027-06-30",
}


def _klient(ustawienia, tmp_path_factory, edytowac: bool):
    dane = tmp_path_factory.mktemp(f"cele-{edytowac}")
    konf = dane / "cele.yaml"
    zrodlo = yaml.safe_load(ustawienia.cele.read_text(encoding="utf-8"))
    zrodlo["pracownik_moze_edytowac"] = edytowac
    konf.write_text(yaml.safe_dump(zrodlo, allow_unicode=True), encoding="utf-8")
    return TestClient(
        utworz_aplikacje(replace(ustawienia, baza=dane / "c.db", log_llm=dane / "llm.jsonl", cele=konf))
    )


@pytest.fixture(scope="module")
def k(ustawienia, tmp_path_factory):
    with _klient(ustawienia, tmp_path_factory, True) as kl:
        yield kl


@pytest.fixture(scope="module")
def k_bez(ustawienia, tmp_path_factory):
    """Przełącznik ``pracownik_moze_edytowac: false``."""
    with _klient(ustawienia, tmp_path_factory, False) as kl:
        yield kl


def _naglowki(kl):
    def zaloguj(login: str) -> dict:
        r = kl.post("/api/auth/login", json={"login": login, "hasło": "demo"})
        assert r.status_code == 200
        return {"Authorization": f"Bearer {r.json()['token']}"}

    return zaloguj


@pytest.fixture(scope="module")
def h(k):
    return _naglowki(k)


@pytest.fixture(scope="module")
def h_bez(k_bez):
    return _naglowki(k_bez)


URL = "/api/pracownicy/P-101/cele"


def test_pracownik_proponuje_cel(k, h):
    r = k.post(URL, json=CEL, headers=h("oceniany"))
    assert r.status_code == 201, r.text
    cel = r.json()
    assert cel["status"] == "propozycja" and cel["autor"] == "oceniany" and cel["osoba_id"] == "P-101"
    assert cel["nazwa"] == CEL["nazwa"] and cel["termin"] == "2027-06-30"

    lista = k.get(URL, headers=h("przelozony1")).json()
    assert [c["id"] for c in lista["cele"]] == [cel["id"]]
    assert lista["pracownik_moze_edytowac"] is True


def _nowy(kl, hd, login="oceniany", **zmiany) -> dict:
    r = kl.post(URL, json={**CEL, **zmiany}, headers=hd(login))
    assert r.status_code == 201, r.text
    return r.json()


def test_zmiana_zatwierdzonego_celu_przez_pracownika_wraca_do_propozycji(k, h):
    cel = _nowy(k, h)
    url = f"/api/cele/{cel['id']}"
    assert k.post(f"{url}/zatwierdz", headers=h("oceniany")).status_code == 403

    r = k.post(f"{url}/zatwierdz", headers=h("przelozony1"))
    assert r.status_code == 200 and r.json()["status"] == "zatwierdzony"
    assert k.post(f"{url}/zatwierdz", headers=h("przelozony1")).status_code == 409

    r = k.put(url, json={**CEL, "miernik": "Pięć notatek bez poprawek"}, headers=h("oceniany"))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "propozycja" and r.json()["miernik"] == "Pięć notatek bez poprawek"

    historia = k.get(f"{url}/historia", headers=h("przelozony1")).json()
    assert historia[-1]["różnica"]["miernik"]["po"] == "Pięć notatek bez poprawek"
    assert historia[-1]["różnica"]["status"] == {"przed": "zatwierdzony", "po": "propozycja"}


def test_zmiana_przez_przelozonego_nie_cofa_akceptacji(k, h):
    cel = _nowy(k, h)
    url = f"/api/cele/{cel['id']}"
    k.post(f"{url}/zatwierdz", headers=h("przelozony1"))
    r = k.put(url, json={**CEL, "termin": "2027-09-30"}, headers=h("przelozony1"))
    assert r.status_code == 200 and r.json()["status"] == "zatwierdzony"


def test_odrzucenie_wymaga_komentarza_i_wraca_do_pracownika(k, h):
    cel = _nowy(k, h)
    url = f"/api/cele/{cel['id']}"
    assert k.post(f"{url}/odrzuc", json={"komentarz": "  "}, headers=h("przelozony1")).status_code == 422
    assert k.post(f"{url}/odrzuc", json={"komentarz": "Za ogólne"}, headers=h("oceniany")).status_code == 403

    r = k.post(f"{url}/odrzuc", json={"komentarz": "Doprecyzuj miernik"}, headers=h("przelozony1"))
    assert r.status_code == 200 and r.json()["status"] == "odrzucony"
    assert r.json()["komentarz"] == "Doprecyzuj miernik"
    assert k.post(f"{url}/zatwierdz", headers=h("przelozony1")).status_code == 409

    r = k.put(url, json={**CEL, "miernik": "Dwie notatki tygodniowo bez poprawek"}, headers=h("oceniany"))
    assert r.json()["status"] == "propozycja"
    r = k.post(f"{url}/zatwierdz", headers=h("przelozony1"))
    assert r.json()["status"] == "zatwierdzony" and r.json()["komentarz"] is None


def test_postep_i_potwierdzenie_osiagniecia(k, h):
    cel = _nowy(k, h)
    url = f"/api/cele/{cel['id']}"
    ho, hp = h("oceniany"), h("przelozony1")
    assert k.post(f"{url}/status", json={"status": "w_realizacji"}, headers=ho).status_code == 409  # przed akceptacją
    k.post(f"{url}/zatwierdz", headers=hp)

    r = k.post(f"{url}/status", json={"status": "w_realizacji"}, headers=ho)
    assert r.status_code == 200 and r.json()["status"] == "w_realizacji"

    # Pracownik zgłasza osiągnięcie; status zmienia dopiero przełożony.
    r = k.post(f"{url}/status", json={"status": "osiągnięty"}, headers=ho)
    assert r.status_code == 200
    assert r.json()["status"] == "w_realizacji" and r.json()["zgloszono_osiagniecie"] is True
    assert k.post(f"{url}/status", json={"status": "porzucony"}, headers=ho).status_code == 403

    r = k.post(f"{url}/status", json={"status": "osiągnięty"}, headers=hp)
    assert r.json()["status"] == "osiągnięty" and r.json()["zgloszono_osiagniecie"] is False

    # Cel zamknięty: bez zmian treści i statusu.
    assert k.put(url, json=CEL, headers=ho).status_code == 409
    assert k.post(f"{url}/status", json={"status": "porzucony"}, headers=hp).status_code == 409


def test_status_tylko_postepu(k, h):
    cel = _nowy(k, h)
    url = f"/api/cele/{cel['id']}/status"
    assert k.post(url, json={"status": "zatwierdzony"}, headers=h("przelozony1")).status_code == 422
    r = k.post(url, json={"status": "porzucony"}, headers=h("przelozony1"))
    assert r.status_code == 200 and r.json()["status"] == "porzucony"


def test_bez_edycji_pracownika_cele_tworzy_przelozony(k_bez, h_bez):
    ho, hp = h_bez("oceniany"), h_bez("przelozony1")
    assert k_bez.post(URL, json=CEL, headers=ho).status_code == 403
    assert k_bez.get(URL, headers=ho).json()["pracownik_moze_edytowac"] is False

    cel = _nowy(k_bez, h_bez, login="przelozony1")
    assert cel["status"] == "propozycja" and cel["autor"] == "przelozony1"
    url = f"/api/cele/{cel['id']}"
    assert k_bez.put(url, json={**CEL, "nazwa": "Inna"}, headers=ho).status_code == 403

    k_bez.post(f"{url}/zatwierdz", headers=hp)
    # Postęp pracownik oznacza w obu trybach.
    r = k_bez.post(f"{url}/status", json={"status": "w_realizacji"}, headers=ho)
    assert r.status_code == 200 and r.json()["status"] == "w_realizacji"
    r = k_bez.post(f"{url}/status", json={"status": "osiągnięty"}, headers=ho)
    assert r.json()["zgloszono_osiagniecie"] is True


def test_uprawnienia(k, h):
    cel = _nowy(k, h)
    url = f"/api/cele/{cel['id']}"
    # HR: tylko odczyt.
    assert k.get(URL, headers=h("hr")).status_code == 200
    assert k.post(URL, json=CEL, headers=h("hr")).status_code == 403
    assert k.post(f"{url}/zatwierdz", headers=h("hr")).status_code == 403
    # Przełożony innej osoby nie widzi i nie zmienia celów P-101.
    assert k.get(URL, headers=h("przelozony2")).status_code == 403
    assert k.post(f"{url}/zatwierdz", headers=h("przelozony2")).status_code == 403
    # Pracownik nie widzi celów innej osoby.
    assert k.get("/api/pracownicy/P-102/cele", headers=h("oceniany")).status_code == 403
    assert k.get("/api/cele/999999/historia", headers=h("przelozony1")).status_code == 404


def test_wskaznik_musi_byc_w_modelu(k, h):
    assert k.post(URL, json={**CEL, "wskaznik_id": "nie-ma-takiego"}, headers=h("oceniany")).status_code == 422


def _proces_z_ocenami(kl, hd, poziomy: list[int]) -> tuple[int, list[str]]:
    """Proces P-101 z krokiem 2 i ocenami pierwszych wskaźników na podanych poziomach."""
    hp = hd("przelozony1")
    r = kl.post("/api/procesy", json={"osoba_id": "P-101", "sciezka": "okresowa"}, headers=hp)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    p = kl.get(f"/api/procesy/{pid}/krok2", headers=hp).json()
    wsk = {kr["kompetencja_id"]: [w["wskaznik_id"] for w in kr["wskazniki"][:2]]
           for kr in p["kryteria"] if kr["rodzaj"] == "OBOWIAZKOWE"}
    assert kl.put(f"/api/procesy/{pid}/krok2", json={"wskazniki": wsk}, headers=hp).status_code == 200
    ids = [w for lista in wsk.values() for w in lista][: len(poziomy)]
    r = kl.put(f"/api/procesy/{pid}/ocena/wskazniki", headers=hp,
               json={"wskazniki": {w: {"poziom": p} for w, p in zip(ids, poziomy)}})
    assert r.status_code == 200, r.text
    return pid, ids


def test_podpowiedzi_regulowe_nie_tworza_celow(ustawienia, tmp_path_factory):
    with _klient(ustawienia, tmp_path_factory, True) as kl:
        hd = _naglowki(kl)
        hp, ho = hd("przelozony1"), hd("oceniany")
        url = f"{URL}/podpowiedzi"
        assert kl.get(url, headers=hp).json()["podpowiedzi"] == []  # brak ocenionego procesu

        pid, (slaby, sredni, mocny) = _proces_z_ocenami(kl, hd, [3, 5, 7])
        r = kl.get(url, headers=hp)
        assert r.status_code == 200, r.text
        wynik = r.json()
        assert wynik["proces_id"] == pid
        assert [p["wskaznik_id"] for p in wynik["podpowiedzi"]] == [slaby]
        pod = wynik["podpowiedzi"][0]
        assert pod["status"] == "propozycja" and pod["zrodlo"] == "reguly"
        assert pod["nazwa"] and pod["miernik"] and pod["regula"] == "rozwoj.obszar-ponizej-oczekiwan"
        assert kl.get(URL, headers=hp).json()["cele"] == []

        # Pracownik zobaczy podpowiedzi z oceny w toku dopiero po przekazaniu samooceny.
        r = kl.get(url, headers=ho).json()
        assert r["podpowiedzi"] == [] and r["komunikat"]
        assert kl.get(url, headers=hd("hr")).status_code == 403
