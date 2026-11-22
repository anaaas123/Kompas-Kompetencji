import pytest

from kompas_mc.ustawienia import KATALOG_MC

ZRODLA_MC = KATALOG_MC.parent / "materialy mc"
WYMAGANE = {
    "brak.ustawa",
    "brak.pytania-i-odpowiedzi",
    "brak.arkusz-a",
    "duplikat.rozp-2016-okresowe",
    "rozbieznosc.skala-5-3",
    "brak.agregacja-modelu",
    "rozbieznosc.osp-pierwsza-ocena",
}


_HR: dict = {}


@pytest.fixture(autouse=True)
def _token_hr(naglowek):
    _HR.update(naglowek("hr"))


def _panel(klient):
    r = klient.get("/api/braki", headers=_HR)
    assert r.status_code == 200, r.text
    return r.json()


def test_panel_tylko_dla_hr(klient, naglowek):
    assert klient.get("/api/braki").status_code == 401
    assert klient.get("/api/braki", headers=naglowek("przelozony1")).status_code == 403
    assert klient.get("/api/braki", headers=naglowek("oceniany")).status_code == 403


def test_panel_ma_wszystkie_braki_z_ticketu(klient):
    assert WYMAGANE <= {b["id"] for b in _panel(klient)["braki"]}


def test_kazdy_brak_ma_opis_i_odwolanie_do_istniejacego_pliku(klient):
    pliki_mc = {p.name for p in ZRODLA_MC.rglob("*") if p.is_file()}
    for b in _panel(klient)["braki"]:
        assert b["opis"].strip(), b["id"]
        assert b["pliki"], f"{b['id']}: brak odwołania do pliku"
        assert set(b["pliki"]) <= pliki_mc, b["id"]


def test_kazdy_cytat_panelu_jest_w_korpusie(klient):
    for b in _panel(klient)["braki"]:
        for a in b["adnotacje"]:
            assert a["cytat_w_korpusie"] in (True, None), (b["id"], a["adnotacja"])


def test_rozbieznosci_maja_flage_i_dwie_adnotacje(klient):
    for b in _panel(klient)["braki"]:
        if b["typ"] == "ROZBIEŻNOŚĆ":
            assert b["rozbieznosc"] and len(b["adnotacje"]) >= 2, b["id"]


def test_duplikat_wykryty_w_korpusie(klient):
    dup = next(b for b in _panel(klient)["braki"] if b["typ"] == "DUPLIKAT")
    assert "Rozporządzenie o ocenach okresowych z 2016 r. (4).pdf" in dup["pliki"]
    assert "nie jest osobnym źródłem" in dup["opis"]


def test_pytania_do_mentorow_widoczne_i_powiazane(klient):
    panel = _panel(klient)
    ids = {b["id"] for b in panel["braki"]}
    pytania = panel["pytania_do_mentorow"]
    assert len(pytania) >= 5
    assert all(p["dotyczy"] in ids and p["pytanie"].strip() for p in pytania)


def test_tresc_zadania_jest_w_korpusie_ale_nie_w_asystencie(klient, naglowek):
    zrodla = {d["doc_id"]: d for d in klient.get("/api/zrodla").json()["dokumenty"]}
    assert zrodla["zadanie-mc"]["w_asystencie"] is False
    r = klient.post("/api/asystent", headers=naglowek("przelozony1"), json={"pytanie": "Baza powinna obejmować ustawę o służbie cywilnej"}
    ).json()
    assert all(c["doc_id"] != "zadanie-mc" for c in r["cytaty"])
