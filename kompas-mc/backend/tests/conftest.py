from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from kompas_mc.app import utworz_aplikacje
from kompas_mc.korpus_mc import zaladuj
from kompas_mc.ustawienia import Ustawienia


@pytest.fixture(scope="session")
def ustawienia(tmp_path_factory) -> Ustawienia:
    dane = tmp_path_factory.mktemp("dane")
    return replace(Ustawienia.ze_srodowiska(), baza=dane / "test.db", log_llm=dane / "llm.jsonl")


@pytest.fixture(scope="session")
def korpus_mc(ustawienia):
    return zaladuj(ustawienia.manifest)


@pytest.fixture(scope="session")
def klient(ustawienia):
    with TestClient(utworz_aplikacje(ustawienia)) as k:
        yield k


@pytest.fixture(scope="session")
def naglowek(klient):
    """Nagłówek autoryzacji po zalogowaniu kontem demo z ``konfiguracja/role.yaml``."""

    def zaloguj(login: str) -> dict:
        r = klient.post("/api/auth/login", json={"login": login, "hasło": "demo"})
        assert r.status_code == 200
        return {"Authorization": f"Bearer {r.json()['token']}"}

    return zaloguj
