"""Stan pokazu (#57): ocena okresowa Anny Zielińskiej (P-101) w trakcie, przygotowana jedną komendą przez API.

    python -m kompas_mc.stan_demo --api http://127.0.0.1:8002

Przełożony (przelozony1) zapisuje krok 2 i zamyka część I (data zapoznania na początku okresu), ocenia
większość wskaźników z przykładami sytuacja – działanie – rezultat (jeden poniżej oczekiwań, jeden „brak
podstaw”, jeden pusty do kliknięcia na żywo) i nie podejmuje decyzji. Anna (konto ``oceniany``) przekazuje
samoocenę z jedną rozbieżnością o co najmniej 4 poziomy i proponuje cel rozwojowy; jeden cel jest już
zatwierdzony. Wszystko idzie przez API, więc obowiązują te same reguły i rejestr operacji co w aplikacji.
Drugie uruchomienie niczego nie dubluje: wypisuje stan i kończy się kodem 0.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from collections.abc import Callable

Wywolanie = Callable[[str, str, str | None, object], tuple[int, object]]

OSOBA = "P-101"
DATA_ZAPOZNANIA = "2024-12-20"  # początek okresu po ocenie z 02.12.2024 (kryteria w ciągu 30 dni, § 7)
PRZYKLAD = {
    "sytuacja": "Przygotowanie stanowiska do projektu rozporządzenia w krótkim terminie",
    "dzialanie": "Zebrała uwagi z trzech wydziałów i uzgodniła wspólną wersję",
    "rezultat": "Stanowisko przekazano w terminie, bez uwag dyrektora",
    "powtarzalnosc": "KILKAKROTNE",
    "zlozonosc": "SREDNIA",
}
CELE = (
    ("przelozony1", {"nazwa": "Prowadzenie spotkań uzgodnieniowych z innymi departamentami",
                     "miernik": "3 spotkania z notatką i ustaleniami", "termin": "2027-06-30"}),
    ("oceniany", {"nazwa": "Szkolenie z komunikacji pisemnej w administracji",
                  "miernik": "ukończone szkolenie i 2 pisma przejrzane przez przełożonego", "termin": "2027-03-31"}),
)


def _http(api: str) -> Wywolanie:
    def wywolaj(metoda: str, sciezka: str, token: str | None = None, dane: object = None) -> tuple[int, object]:
        zadanie = urllib.request.Request(
            api.rstrip("/") + sciezka, method=metoda,
            data=json.dumps(dane).encode() if dane is not None else None,
            headers={"Content-Type": "application/json", **({"Authorization": f"Bearer {token}"} if token else {})},
        )
        try:
            with urllib.request.urlopen(zadanie, timeout=60) as r:
                tresc = r.read()
                return r.status, json.loads(tresc) if tresc else None
        except urllib.error.HTTPError as e:
            tresc = e.read()
            return e.code, json.loads(tresc) if tresc else None

    return wywolaj


def _ok(wynik: tuple[int, object], co: str) -> object:
    status, tresc = wynik
    if status >= 400:
        raise RuntimeError(f"{co}: HTTP {status} {tresc}")
    return tresc


def przygotuj(wywolaj: Wywolanie) -> str:
    """Przygotowuje stan pokazu i zwraca opis; drugi raz nic nie zmienia."""
    def token(login: str) -> str:
        return _ok(wywolaj("POST", "/api/auth/login", None, {"login": login, "hasło": "demo"}), f"logowanie {login}")["token"]

    tp, to = token("przelozony1"), token("oceniany")
    procesy = _ok(wywolaj("GET", "/api/procesy", tp, None), "lista procesów")
    w_toku = [p for p in procesy if p["osoba_id"] == OSOBA and p["status"] == "W_TOKU"]
    if w_toku and w_toku[0].get("krok", 0) >= 3:
        return f"Stan demo już jest: proces {w_toku[0]['id']} Anny Zielińskiej, krok {w_toku[0]['krok']}. Nic nie zmieniono."
    proces = w_toku[0] if w_toku else _ok(
        wywolaj("POST", "/api/procesy", tp, {"osoba_id": OSOBA, "sciezka": "okresowa"}), "rozpoczęcie procesu")
    pid = proces["id"]

    k2 = _ok(wywolaj("GET", f"/api/procesy/{pid}/krok2", tp, None), "krok 2")
    wskazniki = {
        k["kompetencja_id"]: [w["wskaznik_id"] for w in k["wskazniki"] if w.get("proponowany")] or [k["wskazniki"][0]["wskaznik_id"]]
        for k in k2["kryteria"] if k["rodzaj"] == "OBOWIAZKOWE"
    }
    _ok(wywolaj("PUT", f"/api/procesy/{pid}/krok2", tp, {"wskazniki": wskazniki, "dodatkowe": []}), "zapis kroku 2")
    _ok(wywolaj("PUT", f"/api/procesy/{pid}/krok2/zapoznanie", tp, {"data": DATA_ZAPOZNANIA}), "zakończenie części I")

    ocena = _ok(wywolaj("GET", f"/api/procesy/{pid}/ocena", tp, None), "ocena")
    kryteria = [[w["wskaznik_id"] for w in kr["wskazniki"]] for kr in ocena["kryteria"]]
    # Pusty wskaźnik i „brak podstaw” w kryteriach z co najmniej 3 wskaźnikami, żeby każde kryterium miało sugestię
    # (próg: połowa wybranych wskaźników oceniona).
    duze = [ws for ws in kryteria if len(ws) >= 3]
    pusty = duze[0][-1] if duze else None
    bez_podstaw = (duze[1] if len(duze) > 1 else duze[0])[-2] if duze else None
    ponizej = kryteria[1][0] if len(kryteria) > 1 else kryteria[0][0]
    poziomy = (5, 7, 5, 7, 9)
    oceny: dict[str, dict] = {}
    for i, w in enumerate(x for ws in kryteria for x in ws):
        if w == pusty:
            continue
        if w == bez_podstaw:
            oceny[w] = {"brak_podstaw": True}
            continue
        poziom = 3 if w == ponizej else poziomy[i % len(poziomy)]
        oceny[w] = {"poziom": poziom, "przyklady": [PRZYKLAD]} if i % 2 == 0 else {"poziom": poziom, "uwagi": "Omówione na rozmowie; potwierdzone w aktach sprawy."}
    _ok(wywolaj("PUT", f"/api/procesy/{pid}/ocena/wskazniki", tp, {"wskazniki": oceny}), "oceny wskaźników")

    samo = _ok(wywolaj("GET", f"/api/procesy/{pid}/samoocena", to, None), "samoocena")
    if samo["status"] != "przekazana":
        pozycje = {
            w["wskaznik_id"]: {"poziom": 7} if w["wskaznik_id"] == ponizej
            else {"poziom": oceny.get(w["wskaznik_id"], {}).get("poziom", 5)}
            for w in samo["wskazniki"]
        }  # rozbieżność: przełożony 3, samoocena 7
        _ok(wywolaj("PUT", f"/api/procesy/{pid}/samoocena", to, {"wskazniki": pozycje}), "szkic samooceny")
        _ok(wywolaj("POST", f"/api/procesy/{pid}/samoocena/przekaz", to, None), "przekazanie samooceny")

    istniejace = _ok(wywolaj("GET", f"/api/pracownicy/{OSOBA}/cele", tp, None), "cele")["cele"]
    for autor, cel in CELE:
        if not any(c["nazwa"] == cel["nazwa"] for c in istniejace):
            nowy = _ok(wywolaj("POST", f"/api/pracownicy/{OSOBA}/cele", tp if autor == "przelozony1" else to, cel), f"cel: {cel['nazwa']}")
            if autor == "przelozony1" and nowy["status"] == "propozycja":  # cel przełożonego zatwierdzony, propozycja Anny czeka
                _ok(wywolaj("POST", f"/api/cele/{nowy['id']}/zatwierdz", tp, None), "zatwierdzenie celu")

    return (f"Gotowe: proces {pid} Anny Zielińskiej (P-101), część I zamknięta {DATA_ZAPOZNANIA}, "
            f"ocenione {len(oceny) - 1} wskaźniki, 1 „brak podstaw”, 1 pusty; samoocena przekazana; cele: {len(CELE)}.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Przygotuj stan pokazu Kompasu (#57).")
    parser.add_argument("--api", default="http://127.0.0.1:8002", help="adres API, np. http://127.0.0.1:8002")
    args = parser.parse_args(argv)
    try:
        print(przygotuj(_http(args.api)))
    except (RuntimeError, urllib.error.URLError) as e:
        print(f"Nie udało się przygotować stanu demo: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
