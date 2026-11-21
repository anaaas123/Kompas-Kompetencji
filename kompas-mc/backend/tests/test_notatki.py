URL = "/api/pracownicy/P-101/notatki"


def test_przelozony_zapisuje_i_czyta_notatki_podwladnego(klient, naglowek):
    h = naglowek("przelozony1")
    r = klient.post(URL, json={"tresc": "Rzetelnie przygotowała opinię prawną."}, headers=h)
    assert r.status_code == 201 and r.json()["autor"] == "przelozony1"
    assert "Rzetelnie przygotowała opinię prawną." in [
        n["tresc"] for n in klient.get(URL, headers=h).json()
    ]


def test_hr_nie_widzi_tresci_notatek(klient, naglowek):
    h = naglowek("hr")
    assert klient.get(URL, headers=h).status_code == 403
    assert klient.post(URL, json={"tresc": "x"}, headers=h).status_code == 403
    p101 = klient.get("/api/pracownicy/P-101", headers=h).json()
    assert not any("notat" in pole for pole in p101)


def test_cudzy_przelozony_i_oceniany_nie_widza_notatek(klient, naglowek):
    assert klient.get(URL, headers=naglowek("przelozony2")).status_code == 403
    assert klient.get(URL, headers=naglowek("oceniany")).status_code == 403


def test_pusta_notatka_odrzucona(klient, naglowek):
    h = naglowek("przelozony1")
    assert klient.post(URL, json={"tresc": ""}, headers=h).status_code == 422
