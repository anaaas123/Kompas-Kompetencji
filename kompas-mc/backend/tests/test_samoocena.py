"""Samoocena (#8): uprawnienia, 409 przed krokiem 2 i po przekazaniu, rozbieżność, sugestia bez zmian."""

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from kompas_core.zrodla import cytat_w_korpusie

from kompas_mc.app import utworz_aplikacje
from kompas_mc.samoocena import KonfiguracjaSamooceny, PozycjaSamooceny, rozbieznosc
from kompas_mc.ocena import OcenaWskaznika


@pytest.fixture(scope="module")
def k(ustawienia, tmp_path_factory):
    dane = tmp_path_factory.mktemp("samoocena")
    with TestClient(utworz_aplikacje(replace(ustawienia, baza=dane / "s.db", log_llm=dane / "llm.jsonl"))) as kl:
        yield kl


@pytest.fixture(scope="module")
def h(k):
    def zaloguj(login: str) -> dict:
        r = k.post("/api/auth/login", json={"login": login, "hasło": "demo"})
        assert r.status_code == 200
        return {"Authorization": f"Bearer {r.json()['token']}"}

    return zaloguj


@pytest.fixture(scope="module")
def proces(k, h):
    """Proces P-101 (konto ``oceniany``) prowadzony przez przelozony1; zwraca id przed krokiem 2."""
    r = k.post("/api/procesy", json={"osoba_id": "P-101", "sciezka": "okresowa"}, headers=h("przelozony1"))
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _zapisz_krok2(k, h, pid):
    hp = h("przelozony1")
    p = k.get(f"/api/procesy/{pid}/krok2", headers=hp).json()
    wsk = {kr["kompetencja_id"]: [w["wskaznik_id"] for w in kr["wskazniki"][:2]]
           for kr in p["kryteria"] if kr["rodzaj"] == "OBOWIAZKOWE"}
    r = k.put(f"/api/procesy/{pid}/krok2", json={"wskazniki": wsk}, headers=hp)
    assert r.status_code == 200, r.text


def test_przed_krokiem2_409(k, h, proces):
    url = f"/api/procesy/{proces}/samoocena"
    assert k.get(url, headers=h("oceniany")).status_code == 409
    assert k.put(url, json={"wskazniki": {}}, headers=h("oceniany")).status_code == 409


def test_pelny_przebieg(k, h, proces):
    _zapisz_krok2(k, h, proces)
    url = f"/api/procesy/{proces}/samoocena"
    ho, hp = h("oceniany"), h("przelozony1")

    s = k.get(url, headers=ho).json()
    assert s["status"] == "brak" and s["wybrano"] >= 2 and len(s["wskazniki"][0]["poziomy"]) == 5
    w1, w2 = s["wskazniki"][0]["wskaznik_id"], s["wskazniki"][1]["wskaznik_id"]
    reszta = [w["wskaznik_id"] for w in s["wskazniki"][2:]]

    # Przełożony ocenia w1 na 3 (krok 3); sugestia przed samooceną.
    url_oc = f"/api/procesy/{proces}/ocena"
    r = k.put(f"{url_oc}/wskazniki", headers=hp, json={"wskazniki": {w1: {"poziom": 3}, w2: {"poziom": 5}}})
    assert r.status_code == 200, r.text
    sugestie_przed = [kr["sugestia"] for kr in r.json()["kryteria"]]

    # Pracownik nie widzi oceny przełożonego, dopóki nie przekaże samooceny.
    assert k.get(url_oc, headers=ho).status_code == 403

    # Szkic: poziom, „brak zdania”, przykład; wskaźnik spoza kroku 2 → 422.
    przyklad = {"sytuacja": "Nowa ustawa", "dzialanie": "Przygotowałam analizę", "rezultat": "Przyjęta bez uwag"}
    r = k.put(url, headers=ho, json={"wskazniki": {w1: {"poziom": 9, "przyklad": przyklad}, w2: {"brak_zdania": True}}})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "szkic" and r.json()["wypelniono"] == 2
    assert k.put(url, headers=ho, json={"wskazniki": {"obcy-wskaznik": {"poziom": 5}}}).status_code == 422
    assert k.put(url, headers=ho, json={"wskazniki": {w1: {"poziom": 5, "brak_zdania": True}}}).status_code == 422

    # Przełożony nie widzi szkicu: tylko status; /ocena bez treści samooceny.
    s = k.get(url, headers=hp).json()
    assert s["status"] == "szkic" and s["tresc_widoczna"] is False and s["wypelniono"] == 0
    oc = k.get(url_oc, headers=hp).json()
    assert oc["samoocena_status"] == "szkic"
    assert all(w["samoocena"] is None for kr in oc["kryteria"] for w in kr["wskazniki"])

    # Przekazanie niepełnej → 422; po uzupełnieniu → przekazana, dalsze zmiany → 409.
    if reszta:
        assert k.post(f"{url}/przekaz", headers=ho).status_code == 422
        r = k.put(url, headers=ho, json={"wskazniki": {w: {"poziom": 5} for w in reszta}})
        assert r.status_code == 200
    r = k.post(f"{url}/przekaz", headers=ho)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "przekazana" and r.json()["przekazano"]
    assert k.put(url, headers=ho, json={"wskazniki": {w1: {"poziom": 5}}}).status_code == 409
    assert k.post(f"{url}/przekaz", headers=ho).status_code == 409

    # Po przekazaniu pracownik widzi ocenę przełożonego, ale bez pól porównania (te są dla przełożonego).
    r = k.get(url_oc, headers=ho)
    assert r.status_code == 200 and r.json()["samoocena_status"] is None

    # Przełożony widzi treść i rozbieżność (9 − 3 = 6 ≥ 4); „brak zdania” nie daje rozbieżności.
    oc = k.get(url_oc, headers=hp).json()
    assert oc["samoocena_status"] == "przekazana"
    po_id = {w["wskaznik_id"]: w for kr in oc["kryteria"] for w in kr["wskazniki"]}
    assert po_id[w1]["samoocena"]["poziom"] == 9 and po_id[w1]["rozbieznosc"] is True
    assert po_id[w1]["samoocena"]["przyklad"]["rezultat"] == "Przyjęta bez uwag"
    assert po_id[w2]["samoocena"]["brak_zdania"] is True and po_id[w2]["rozbieznosc"] is None

    # Sugestia identyczna z samooceną i bez niej.
    assert [kr["sugestia"] for kr in oc["kryteria"]] == sugestie_przed


def test_uprawnienia(k, h, proces):
    url = f"/api/procesy/{proces}/samoocena"
    assert k.get(url, headers=h("hr")).status_code == 403
    assert k.put(url, json={"wskazniki": {}}, headers=h("hr")).status_code == 403
    assert k.put(url, json={"wskazniki": {}}, headers=h("przelozony1")).status_code == 403
    assert k.get(url, headers=h("przelozony2")).status_code == 403  # nie jego podwładna
    assert "samoocena_status" not in k.get(f"/api/procesy/{proces}/ocena", headers=h("hr")).text or \
        k.get(f"/api/procesy/{proces}/ocena", headers=h("hr")).status_code == 403
    assert k.get(url).status_code == 401


def test_oceniany_tylko_wlasny_proces(k, h):
    hp = h("przelozony1")
    r = k.post("/api/procesy", json={"osoba_id": "P-104", "sciezka": "okresowa"}, headers=hp)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    _zapisz_krok2(k, h, pid)
    assert k.get(f"/api/procesy/{pid}/samoocena", headers=h("oceniany")).status_code == 403
    assert k.put(f"/api/procesy/{pid}/samoocena", json={"wskazniki": {}}, headers=h("oceniany")).status_code == 403


@pytest.mark.parametrize(("samo", "ocena", "wynik"), [(9, 3, True), (7, 3, True), (5, 3, False), (1, 5, True), (None, 5, None)])
def test_rozbieznosc(samo, ocena, wynik):
    s = PozycjaSamooceny(poziom=samo) if samo else PozycjaSamooceny(brak_zdania=True)
    assert rozbieznosc(s, OcenaWskaznika(poziom=ocena), 4) is wynik


def test_regula_ma_adnotacje_decyzji_projektowej(ustawienia, korpus_mc):
    konf = KonfiguracjaSamooceny.z_pliku(ustawienia.samoocena)
    assert konf.prog_rozbieznosci == 4 and konf.poziomy == [1, 3, 5, 7, 9]
    assert [a.kategoria for a in konf.regula.adnotacje] == ["DECYZJA_PROJEKTOWA"]
    for a in konf.regula.adnotacje:
        if a.cytat_doslowny:
            assert cytat_w_korpusie(a.cytat_doslowny, korpus_mc.korpus, a.doc_id)
