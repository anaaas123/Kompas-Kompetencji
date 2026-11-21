from kompas_core.zrodla import StatusEkstrakcji


def test_oba_rozporzadzenia_w_korpusie(korpus_mc):
    statusy = {w.doc_id: w.status for w in korpus_mc.korpus.raport}
    assert statusy["rozp-2015-pierwsza"] is StatusEkstrakcji.OK
    assert statusy["rozp-2016-okresowe"] is StatusEkstrakcji.OK
    assert all(s is StatusEkstrakcji.OK for s in statusy.values()), statusy
    lokalizatory = {
        f.lokalizator for f in korpus_mc.korpus.fragmenty if f.doc_id == "rozp-2015-pierwsza"
    }
    assert {"§ 3", "§ 4 ust. 1", "§ 10 ust. 1"} <= lokalizatory


def test_duplikat_rozporzadzenia_jest_fragmentem_a_nie_zrodlem(korpus_mc):
    (dup,) = korpus_mc.duplikaty
    assert dup.plik.name == "Rozporządzenie o ocenach okresowych z 2016 r. (4).pdf"
    assert dup.duplikat_z == "rozp-2016-okresowe"
    assert dup.potwierdzony and dup.pokrycie >= 0.8
    assert dup.plik not in {d.plik for d in korpus_mc.dokumenty.values()}
    assert all("(4)" not in w.plik for w in korpus_mc.korpus.raport)


def test_poradniki_podzielone_na_strony(korpus_mc):
    f = [f for f in korpus_mc.korpus.fragmenty if f.doc_id == "poradnik-pierwsza"]
    assert f and all(x.lokalizator == f"s. {x.strona}" for x in f)


def test_filtr_sciezki(korpus_mc):
    pierwsza = set(korpus_mc.doc_ids_dla("pierwsza"))
    assert "rozp-2015-pierwsza" in pierwsza and "rozp-2016-okresowe" not in pierwsza
    assert "model-kompetencji" in pierwsza
