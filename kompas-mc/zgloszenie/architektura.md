# Technologie i architektura

## Technologie

| Warstwa | Technologia |
|---|---|
| Backend | Python 3.12, **FastAPI** (dokumentacja OpenAPI pod `/docs`), Pydantic, SQLite |
| Interfejs | **React + TypeScript + Vite**, przeglądarka na komputerze i tablecie (bez smartfonów, zgodnie z zadaniem) |
| Dokumenty | ReportLab (PDF z polskimi znakami), pypdf i openpyxl (ekstrakcja z PDF, DOCX i XLSX) |
| AI | BM25 (własna implementacja), opcjonalnie Ollama (model lokalny) za interfejsem `LlmProvider` |
| Jakość | pytest (206 testów backendu MC, 89 testów core), walidator cytatów w GitHub Actions |

Wszystkie biblioteki są open source i nie wymagają płatnych usług.

## Architektura

```
┌──────────── Interfejs (React) ────────────┐
│ logowanie · lista podwładnych · kroki 1–8 │
│ czat asystenta · panel HR · panel źródeł  │
└───────────────────┬───────────────────────┘
                    │ REST/JSON (OpenAPI), token sesji
┌───────────────────▼───────────────────────┐
│ API wersji MC (FastAPI)                   │
│ procesy · kroki 1–8 · arkusze B/C i PDF   │
│ asystent formalny · asystent rozmowy · HR │
│ metodyka (wersje) · źródła i braki        │
├───────────────────────────────────────────┤
│ kompas-core (wspólny, bez treści)         │
│ korpus + walidator cytatów · BM25         │
│ kalendarz terminów · silnik skali § 11    │
│ uwierzytelnianie, role, dziennik zmian    │
│ LlmProvider z walidacją · prymitywy PDF   │
├───────────────────────────────────────────┤
│ Konfiguracja YAML (treść merytoryczna)    │
│ reguły z cytatami · model · FAQ · role    │
└───────────────────────────────────────────┘
      │                        │
  mock QNT (kadry)       mock EZD (rejestracja PDF)
```

- **Mechanizm oddzielony od treści.** `kompas-core` nie zna żadnych przepisów: dostaje je z konfiguracji. Zmiana progów, kryteriów, terminów czy treści oświadczeń to zmiana pliku YAML z cytatami, którą walidator sprawdza w CI. Nie trzeba zmieniać kodu.
- **Wersjonowanie.** Metodyka sugestii ma wersje z zatwierdzeniem, a ocena zapisuje użytą wersję. Wynik można więc odtworzyć po zmianie reguł.
- **Integracje przez udokumentowane interfejsy.** Mock QNT (dane kadrowe) i mock EZD (rejestracja PDF z numerem sprawy i hashem) mają kontrakty w OpenAPI. Prawdziwe systemy podłącza się w miejsce mocków bez zmiany reszty.
- **Bezpieczeństwo w prototypie.** Logowanie kontami demo dostaje token sesji. Role i reguły dostępu egzekwuje API: przełożony widzi swoich podwładnych, oceniany siebie, a HR wszystkich, ale bez treści ocen i notatek. Dziennik zmian zapisuje: kto, kiedy, co, według której wersji reguł.
- **Dokumenty.** PDF arkusza B/C odwzorowuje wzór z rozporządzenia, ma wersję i hash w stopce i miejsca na podpis odręczny. Zatwierdzenie w aplikacji nie jest podpisem i aplikacja to komunikuje.

## Przed wdrożeniem produkcyjnym

| Obszar | Stan w prototypie | Co trzeba zrobić |
|---|---|---|
| Uwierzytelnianie | Konta demo z hasłem w konfiguracji, sesje w pamięci | SSO urzędu (np. Azure AD / Keycloak, OIDC), MFA, wygasanie i unieważnianie sesji |
| Autoryzacja | Role z pliku `role.yaml` | Role i podległość z systemu kadrowego, przegląd uprawnień, zasada najmniejszych uprawnień |
| Dane osobowe | Fikcyjne dane, SQLite bez szyfrowania | Baza z szyfrowaniem w spoczynku i w transmisji (TLS), retencja zgodna z przepisami o aktach osobowych, DPIA, rejestr czynności przetwarzania |
| Integracje | Mock QNT i mock EZD | Prawdziwe API QNT i EZD, uwierzytelnienie usług (mTLS / klucze), obsługa błędów i kolejki |
| AI | Tryb ekstrakcyjny, opcjonalna lokalna Ollama | Model hostowany w infrastrukturze MC (dane nie opuszczają urzędu), testy jakości na pytaniach od ekspertów HR, monitorowanie odpowiedzi i logów |
| Baza wiedzy | Materiały MC bez ustawy | Ustawa o służbie cywilnej i aktualne poradniki KPRM, proces aktualizacji przepisów z zatwierdzaniem |
| Metodyka | Mediana i mapowanie 5→3 jako decyzja projektowa | Zatwierdzenie przez właściciela metodyki w MC (w aplikacji: wersja z osobą i datą) |
| Podpis | PDF do podpisu odręcznego | Ewentualny podpis kwalifikowany lub podpis w EZD, zgodnie z decyzją prawną |
| Dziennik i audyt | Tabela w SQLite | Niezmienialny dziennik audytowy, kopie zapasowe, monitorowanie |
| Dostępność | Interfejs bez audytu WCAG | Audyt WCAG 2.1 AA, testy z użytkownikami |
| Wydajność | Korpus budowany przy starcie | Cache korpusu, wiele instancji API, baza serwerowa (PostgreSQL) |

## Kod i uruchomienie

Instrukcja jest w `kompas-mc/README.md`: API na porcie 8002, interfejs na 5174, testy i walidator jedną komendą.
