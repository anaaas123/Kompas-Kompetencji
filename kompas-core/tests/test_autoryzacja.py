import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from kompas_core.auth import Autoryzacja, KonfiguracjaRol, Uzytkownik

KONFIG = {
    "konta": [
        {"login": "p1", "hasło": "demo", "rola": "przelozony", "osoba_id": "P1"},
        {"login": "oceniany", "hasło": "demo", "rola": "oceniany", "osoba_id": "O1"},
    ],
    "uprawnienia": {"przelozony": ["czytaj"]},
    "reguły_dostępu": [
        {"zasób": "pracownik", "rola": "przelozony", "pole": "przelozony_id"},
        {"zasób": "pracownik", "rola": "przelozony", "pole": "zastepstwo_ids"},
    ],
}
PRACOWNICY = [
    {"id": "A", "przelozony_id": "P1"},
    {"id": "B", "przelozony_id": "P2"},
    {"id": "C", "przelozony_id": "P2", "zastepstwo_ids": ["P1"]},
]


@pytest.fixture
def klient():
    auth = Autoryzacja(KonfiguracjaRol.model_validate(KONFIG))
    app = FastAPI()
    app.include_router(auth.router())

    @app.get("/pracownicy")
    def lista(uz: Uzytkownik = auth.wymagaj("czytaj")):
        return auth.filtruj(uz, "pracownik", PRACOWNICY, "czytaj")

    @app.get("/pracownicy/{nr}")
    def jeden(nr: int, uz: Uzytkownik = auth.wymagaj("czytaj")):
        auth.sprawdz(uz, "pracownik", PRACOWNICY[nr], "czytaj")
        return PRACOWNICY[nr]

    return TestClient(app)


def naglowek(klient, login):
    odp = klient.post("/auth/login", json={"login": login, "hasło": "demo"})
    assert odp.status_code == 200
    return {"Authorization": f"Bearer {odp.json()['token']}"}


@pytest.mark.parametrize(
    "naglowki", [{}, {"Authorization": "Bearer obcy"}, {"Authorization": "Basic abc"}]
)
def test_bez_tokenu_401(klient, naglowki):
    assert klient.get("/pracownicy", headers=naglowki).status_code == 401


def test_bledne_haslo_401(klient):
    assert klient.post("/auth/login", json={"login": "p1", "hasło": "zle"}).status_code == 401


def test_rola_bez_uprawnienia_403(klient):
    assert klient.get("/pracownicy", headers=naglowek(klient, "oceniany")).status_code == 403


def test_przelozony_widzi_tylko_swoich_podwladnych(klient):
    h = naglowek(klient, "p1")
    assert [p["id"] for p in klient.get("/pracownicy", headers=h).json()] == ["A", "C"]
    assert klient.get("/pracownicy/0", headers=h).status_code == 200
    assert klient.get("/pracownicy/1", headers=h).status_code == 403
    assert klient.get("/pracownicy/2", headers=h).status_code == 200
