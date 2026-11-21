"""Krok 1 (#29): analiza OSP, wybór ścieżki i arkusza B/C, start procesu oceny."""

import pytest
from kompas_core.zrodla import cytat_w_korpusie

from kompas_mc.krok1 import KonfiguracjaKroku1, analizuj, proponuj_sciezke, wybierz_arkusz
from kompas_mc.osp import KatalogOsp
from kompas_mc.qnt import MockQnt, PierwszaOcena


@pytest.fixture(scope="module")
def konf(ustawienia):
    return KonfiguracjaKroku1.z_pliku(ustawienia.krok1)


@pytest.fixture(scope="module")
def katalog(korpus_mc):
    return KatalogOsp(korpus_mc)


@pytest.fixture(scope="module")
def qnt(ustawienia):
    return MockQnt.z_pliku(ustawienia.qnt)


def _krok1(klient, naglowek, osoba_id, login="hr"):
    r = klient.get(f"/api/pracownicy/{osoba_id}/krok1", headers=naglowek(login))
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- kryteria akceptacji


@pytest.mark.parametrize(
    ("osoba_id", "symbol", "arkusz"),
    [("P-101", "DSI WWI 5", "C"), ("P-102", "DC WZKSOiC 6", "C"), ("P-001", "DWM WKAM 1", "B")],
)
def test_arkusz_z_osp(klient, naglowek, osoba_id, symbol, arkusz):
    a = _krok1(klient, naglowek, osoba_id)
    assert a["osp"]["symbol"] == symbol
    assert a["sciezka"]["proponowana"] == "okresowa"
    assert a["arkusz_okresowy"]["arkusz"] == arkusz
    assert a["arkusz_okresowy"]["zrodlo"] == "OSP"
    lokalizatory = {x.get("lokalizator") for x in a["arkusz_okresowy"]["adnotacje"]}
    assert ("§ 3 ust. 3" if arkusz == "B" else "§ 3 ust. 4") in lokalizatory


def test_naczelnik_kieruje_5_do_9_osob(klient, naglowek):
    osp = _krok1(klient, naglowek, "P-001")["osp"]
    assert osp["podlegli"]["zaznaczone"] == [
        "bezpośrednio kieruje lub koordynuje pracę od 5 do 9 pracowników"
    ]


def test_osp_pokazuje_cel_zadania_zlozonosc_samodzielnosc_i_kompetencje(klient, naglowek):
    osp = _krok1(klient, naglowek, "P-101")["osp"]
    assert osp["cel"]["tekst"].startswith("Zapewnienie wsparcia merytorycznego")
    assert [z["nr"] for z in osp["zadania_dominujace"]] == [1, 2, 3]
    assert [z["nr"] for z in osp["zadania_pozostale"]] == [4, 5]
    assert osp["zlozonosc"]["opis"] and osp["samodzielnosc"]["opis"]
    assert osp["kompetencje_miekkie"]["lista"] == [
        "organizacja pracy i orientacja na osiąganie celów",
        "wykorzystywanie wiedzy i doskonalenie zawodowe",
        "współpraca",
    ]


def test_przeslanki_ustawowe_jako_objasnienie_z_adnotacja_o_braku_ustawy(klient, naglowek):
    przeslanki = _krok1(klient, naglowek, "P-101")["sciezka"]["przeslanki"]
    assert przeslanki
    for p in przeslanki:
        assert p["uwaga"] == "brak tekstu ustawy w bazie"
        z_poradnika = [a for a in p["adnotacje"] if a["doc_id"].startswith("poradnik-")]
        assert z_poradnika and all(a["kategoria"] == "OBJAŚNIENIE_MATERIAŁU" for a in z_poradnika)
    urzednik = next(p for p in przeslanki if p["id"] == "okresowa.urzednik")
    assert urzednik["spelniona"] is True and urzednik["dane_kadrowe"] == {"korpus": "urzednik_sc"}


def test_pierwsza_ocena_ma_krok_osp_z_adnotacja_par_3_pkt_2(klient, naglowek):
    a = _krok1(klient, naglowek, "P-201")
    assert a["sciezka"]["proponowana"] == "pierwsza"
    assert a["osp"]["symbol"] == "DC WZKSOiC 6"
    uwaga = next(u for u in a["uwagi"] if u["id"] == "rozbieznosc.osp-pierwsza-ocena")
    assert any(x.get("lokalizator") == "§ 3 pkt 2" for x in uwaga["adnotacje"])
    assert any(x["kategoria"] == "BRAK_ŹRÓDŁA" for x in uwaga["adnotacje"])


def test_arkusz_a_poza_zakresem(klient, naglowek):
    a = _krok1(klient, naglowek, "P-101")["arkusz_a"]
    assert a["status"] == "POZA_ZAKRESEM_PROTOTYPU" and a["dotyczy"] is False
    assert "poza zakresem prototypu" in a["komunikat"]


def test_wszystkie_osoby_demo_maja_oczekiwany_arkusz_i_sciezke(qnt, katalog, konf):
    for p in qnt.pracownicy:
        a = analizuj(p, katalog, konf)
        assert a.sciezka.braki == [], p.osoba_id
        oczekiwana = "pierwsza" if p.pierwsza_ocena else "okresowa"
        assert a.sciezka.proponowana == oczekiwana, p.osoba_id
        if p.oczekiwany_arkusz:
            assert a.arkusz_okresowy.arkusz == p.oczekiwany_arkusz, p.osoba_id


def test_cytaty_kroku1_sa_w_korpusie(klient, naglowek, korpus_mc):
    for osoba_id in ("P-001", "P-101", "P-102", "P-201", "P-204"):
        a = _krok1(klient, naglowek, osoba_id)
        refs = [x for p in a["sciezka"]["przeslanki"] for x in p["adnotacje"]]
        refs += a["arkusz_okresowy"]["adnotacje"] + [x for u in a["uwagi"] for x in u["adnotacje"]]
        osp = a["osp"]
        refs += [osp["cel"]["adnotacja"], osp["kompetencje_miekkie"]["adnotacja"]]
        refs += [z["adnotacja"] for z in osp["zadania_dominujace"] + osp["zadania_pozostale"]]
        for ref in refs:
            if ref.get("cytat_dosłowny"):
                assert cytat_w_korpusie(ref["cytat_dosłowny"], korpus_mc.korpus, ref["doc_id"]), ref


# ---------------------------------------------------------------- niejednoznaczne dane: braki


def test_czas_okreslony_bez_danych_pierwszej_oceny_daje_braki(qnt, konf):
    p = qnt.pracownik("P-201").model_copy(update={"pierwsza_ocena": None})
    s = proponuj_sciezke(p, konf)
    assert s.proponowana is None
    assert [b.pole for b in s.braki] == ["pierwsza_ocena"]


def test_zastepstwo_bez_ustalenia_stron_daje_braki(qnt, konf):
    p = qnt.pracownik("P-204").model_copy(update={"pierwsza_ocena": None})
    s = proponuj_sciezke(p, konf)
    assert s.proponowana is None
    assert any("Zastępstwo" in b.komunikat for b in s.braki)


def test_absolwent_ksap_bez_informacji_o_wniosku_daje_braki(qnt, konf):
    p = qnt.pracownik("P-203").model_copy(update={"wniosek_o_mianowanie": None})
    s = proponuj_sciezke(p, konf)
    assert s.proponowana is None and [b.pole for b in s.braki] == ["wniosek_o_mianowanie"]


def test_absolwent_ksap_z_wnioskiem_nie_podlega_pierwszej_ocenie(qnt, konf):
    p = qnt.pracownik("P-203").model_copy(update={"wniosek_o_mianowanie": True})
    s = proponuj_sciezke(p, konf)
    assert s.proponowana is None
    ksap = next(x for x in s.przeslanki if x.id == "pierwsza.wylaczenie-ksap")
    assert ksap.spelniona is True


def test_sprzeczne_dane_obu_sciezek_daja_braki(qnt, konf):
    p = qnt.pracownik("P-201").model_copy(update={"korpus": "urzednik_sc"})
    s = proponuj_sciezke(p, konf)
    assert s.proponowana is None and any(b.pole == "sciezka" for b in s.braki)


def test_okresowa_ocena_u_osoby_na_pierwszej_ocenie_daje_braki(qnt, konf):
    p = qnt.pracownik("P-201").model_copy(update={"ostatnia_ocena_okresowa": None})
    assert proponuj_sciezke(p, konf).proponowana == "pierwsza"
    p = qnt.pracownik("P-201").model_copy(
        update={"ostatnia_ocena_okresowa": qnt.pracownik("P-101").ostatnia_ocena_okresowa}
    )
    s = proponuj_sciezke(p, konf)
    assert s.proponowana is None and any(b.pole == "ostatnia_ocena_okresowa" for b in s.braki)


def test_osp_i_qnt_sprzeczne_co_do_kierowania_daja_braki(qnt, katalog, konf):
    p = qnt.pracownik("P-101").model_copy(update={"kieruje_pracownikami": True})
    a = wybierz_arkusz(p, katalog.po_symbolu(p.symbol_osp), konf)
    assert a.arkusz is None and [b.pole for b in a.braki] == ["kieruje_pracownikami"]


def test_brak_osp_arkusz_z_qnt_z_oznaczeniem(klient, naglowek):
    a = _krok1(klient, naglowek, "P-002")
    assert a["osp"] is None
    assert a["arkusz_okresowy"]["arkusz"] == "B" and a["arkusz_okresowy"]["zrodlo"] == "QNT"
    assert any(x["kategoria"] == "BRAK_ŹRÓDŁA" for x in a["arkusz_okresowy"]["adnotacje"])
    assert any(u["id"] == "brak.osp" for u in a["uwagi"])


def test_kierownik_urzedu_arkusz_a_poza_zakresem(qnt, katalog, konf):
    p = qnt.pracownik("P-002").model_copy(update={"stanowisko": "Kierownik urzędu"})
    a = analizuj(p, katalog, konf)
    assert a.arkusz_a.dotyczy is True and a.arkusz_okresowy.arkusz is None


def test_pierwsza_ocena_bez_egzaminu_nadal_pierwsza(qnt, konf):
    p = qnt.pracownik("P-202").model_copy(
        update={"pierwsza_ocena": PierwszaOcena(egzamin_sluzba_przygotowawcza="brak")}
    )
    assert proponuj_sciezke(p, konf).proponowana == "pierwsza"


# ---------------------------------------------------------------- uprawnienia


def test_uprawnienia_kroku1(klient, naglowek):
    assert klient.get("/api/pracownicy/P-101/krok1").status_code == 401
    assert klient.get("/api/pracownicy/P-101/krok1", headers=naglowek("przelozony2")).status_code == 403
    assert klient.get("/api/pracownicy/P-102/krok1", headers=naglowek("oceniany")).status_code == 403
    assert klient.get("/api/pracownicy/P-101/krok1", headers=naglowek("oceniany")).status_code == 200
    assert klient.get("/api/pracownicy/P-999/krok1", headers=naglowek("hr")).status_code == 404


# ---------------------------------------------------------------- proces oceny


def test_przelozony_rozpoczyna_proces_okresowy(klient, naglowek):
    h = naglowek("przelozony1")
    r = klient.post("/api/procesy", json={"osoba_id": "P-101", "sciezka": "okresowa"}, headers=h)
    assert r.status_code == 201, r.text
    p = r.json()
    assert (p["sciezka"], p["arkusz"], p["krok"], p["status"]) == ("okresowa", "C", 1, "W_TOKU")
    assert p["rozpoczal"] == "przelozony1" and p["zgodna_z_propozycja"] is True
    assert p["krok1"]["osp"]["symbol"] == "DSI WWI 5"

    assert klient.get(f"/api/procesy/{p['id']}", headers=h).json()["id"] == p["id"]
    r = klient.post("/api/procesy", json={"osoba_id": "P-101", "sciezka": "okresowa"}, headers=h)
    assert r.status_code == 409

    historia = klient.app.state.dziennik.historia("proces", str(p["id"]))
    assert historia and historia[0].autor == "przelozony1"


def test_inna_sciezka_niz_propozycja_wymaga_uzasadnienia(klient, naglowek):
    h = naglowek("przelozony1")
    body = {"osoba_id": "P-104", "sciezka": "pierwsza"}
    r = klient.post("/api/procesy", json=body, headers=h)
    assert r.status_code == 422 and r.json()["detail"]["proponowana"] == "okresowa"
    body["uzasadnienie"] = "Test: kadry potwierdziły pierwsze zatrudnienie."
    r = klient.post("/api/procesy", json=body, headers=h)
    assert r.status_code == 201
    p = r.json()
    assert p["arkusz"] == "PIERWSZA" and p["zgodna_z_propozycja"] is False
    assert any(u["id"] == "rozbieznosc.osp-pierwsza-ocena" for u in p["krok1"]["uwagi"])


def test_proces_pierwszej_oceny(klient, naglowek):
    r = klient.post(
        "/api/procesy",
        json={"osoba_id": "P-201", "sciezka": "pierwsza"},
        headers=naglowek("przelozony2"),
    )
    assert r.status_code == 201 and r.json()["arkusz"] == "PIERWSZA"


def test_tylko_przelozony_rozpoczyna_proces(klient, naglowek):
    body = {"osoba_id": "P-102", "sciezka": "okresowa"}
    assert klient.post("/api/procesy", json=body, headers=naglowek("hr")).status_code == 403
    assert klient.post("/api/procesy", json=body, headers=naglowek("oceniany")).status_code == 403
    assert klient.post("/api/procesy", json=body, headers=naglowek("przelozony1")).status_code == 403


def test_lista_procesow_wedlug_roli(klient, naglowek):
    klient.post(
        "/api/procesy",
        json={"osoba_id": "P-103", "sciezka": "okresowa"},
        headers=naglowek("przelozony2"),
    )
    osoby = lambda login: {  # noqa: E731
        p["osoba_id"] for p in klient.get("/api/procesy", headers=naglowek(login)).json()
    }
    assert "P-103" in osoby("przelozony2") and "P-103" not in osoby("przelozony1")
    assert "P-103" in osoby("hr")
    assert osoby("oceniany") <= {"P-101"}


def test_odczyt_procesu_poza_zakresem(klient, naglowek):
    lista = klient.get("/api/procesy", headers=naglowek("przelozony2")).json()
    assert lista
    proces_id = lista[0]["id"]
    assert klient.get(f"/api/procesy/{proces_id}", headers=naglowek("przelozony1")).status_code == 403
    assert klient.get("/api/procesy/99999", headers=naglowek("hr")).status_code == 404
