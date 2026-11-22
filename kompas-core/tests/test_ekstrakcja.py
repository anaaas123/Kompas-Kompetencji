from kompas_core.zrodla import StatusEkstrakcji, TypZmiany, ekstrahuj


def test_pdf_strona_po_stronie_z_lokalizatorem(pdf_z_tekstem):
    w = ekstrahuj(pdf_z_tekstem, "ustawa", "2024")
    assert w.status is StatusEkstrakcji.OK
    assert w.strony_bez_tekstu == [2]
    assert "brak tekstu" in w.komunikat
    lok = {f.lokalizator: f for f in w.fragmenty}
    assert lok["art. 81 ust. 1"].strona == 1
    assert "zatrudnio-\nnego" in lok["art. 81 ust. 1"].tekst
    assert lok["art. 81 ust. 2"].tekst.startswith("2. Ocene")
    assert lok["art. 83 ust. 1"].strona == 1
    assert lok["art. 83 § 11 ust. 1"].strona == 3
    assert w.fragmenty[0].id == "ustawa@2024#1"
    assert lok["zał. 1 poz. 2"].tekst == "2. KREATYWNOSC - opis"
    assert lok["zał. 1 poz. 2"].strona == 4


def test_pdf_od_strony_pomija_wstep_i_jego_lokalizator(pdf_z_tekstem):
    w = ekstrahuj(pdf_z_tekstem, "ustawa", "2024", od_strony=3)
    assert w.status is StatusEkstrakcji.OK and w.strony_bez_tekstu == []
    assert min(f.strona for f in w.fragmenty) == 3
    assert w.fragmenty[0].id == "ustawa@2024#1"
    # Bez pominięcia strona 3 dziedziczy „art. 83” ze strony 1 („art. 83 § 11 ust. 1”).
    assert w.fragmenty[0].lokalizator == "§ 11 ust. 1"


def test_pdf_bez_warstwy_tekstowej_jest_raportowany(pdf_bez_tekstu):
    w = ekstrahuj(pdf_bez_tekstu, "skan")
    assert w.status is StatusEkstrakcji.BRAK_TEKSTU
    assert w.fragmenty == []
    assert w.strony_bez_tekstu == [1, 2]
    assert "brak tekstu" in w.komunikat


def test_docx_sledzone_zmiany_osobno(docx_ze_zmianami):
    w = ekstrahuj(docx_ze_zmianami, "arkusz")
    assert w.status is StatusEkstrakcji.OK
    data = next(f for f in w.fragmenty if f.tekst.startswith("Data oceny"))
    assert data.tekst == "Data oceny: 14.06.2024"
    assert [(z.typ, z.tekst, z.autor) for z in data.zmiany] == [
        (TypZmiany.USUNIECIE, "14.046.2024", "Kadry"),
        (TypZmiany.WSTAWKA, "14.06.2024", "Kadry"),
    ]
    assert w.fragmenty[0].lokalizator == "§ 4"
    komorka = next(f for f in w.fragmenty if f.lokalizator == "tabela 1 w1 k2")
    assert komorka.tekst == "Zażółć gęślą jaźń"


def test_xlsx_komorki_z_adresem(xlsx):
    w = ekstrahuj(xlsx, "excel")
    adresy = {f.lokalizator: f.tekst for f in w.fragmenty}
    assert adresy["Część II!A2"] == "Komunikacja"
    assert adresy["Część II!B2"] == "7"
    assert adresy["Część II!B3"] == "3.3"
    assert adresy["Wskaźniki!C5"] == "Rzetelność i terminowość"


def test_nieobslugiwany_plik_jest_raportowany(tmp_path):
    p = tmp_path / "Thumbs.db"
    p.write_bytes(b"\x00")
    assert ekstrahuj(p, "x").status is StatusEkstrakcji.NIEOBSLUGIWANY


def test_uszkodzony_plik_daje_blad_a_nie_wyjatek(tmp_path):
    p = tmp_path / "zly.docx"
    p.write_bytes(b"to nie jest zip")
    w = ekstrahuj(p, "zly")
    assert w.status is StatusEkstrakcji.BLAD
    assert w.komunikat
