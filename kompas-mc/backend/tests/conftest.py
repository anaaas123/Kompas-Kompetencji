from dataclasses import replace

import pytest
import yaml
from fastapi.testclient import TestClient

from kompas_mc.app import utworz_aplikacje
from kompas_mc.korpus_mc import zaladuj
from kompas_mc.ustawienia import Ustawienia


@pytest.fixture(scope="session")
def ustawienia(tmp_path_factory) -> Ustawienia:
    dane = tmp_path_factory.mktemp("dane")
    ustawienia = Ustawienia.ze_srodowiska()
    # Pełny zestaw testów jest zawsze offline. Testy łańcucha dostawców korzystają
    # jawnie z produkcyjnej konfiguracji i atrap HTTP.
    konfiguracja = yaml.safe_load(ustawienia.konfiguracja_asystenta.read_text(encoding="utf-8"))
    konfiguracja["llm"] = {"dostawcy": [{"typ": "ekstrakcyjny", "k": 3}]}
    konfiguracja["faq"] = str(ustawienia.konfiguracja_asystenta.parent / konfiguracja["faq"])
    asystent = dane / "asystent-offline.yaml"
    asystent.write_text(yaml.safe_dump(konfiguracja, allow_unicode=True), encoding="utf-8")
    return replace(
        ustawienia,
        baza=dane / "test.db",
        log_llm=dane / "llm.jsonl",
        konfiguracja_asystenta=asystent,
    )


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
