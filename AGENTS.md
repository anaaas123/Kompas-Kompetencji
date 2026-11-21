# AGENTS.md

## Agent skills

### Issue tracker

Issues live in GitHub Issues on harn0ld/HackNation2026 (via the `gh` CLI). See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Branche i miejsca pracy

Repo zawiera dwie niezależne wersje aplikacji i wspólny core. Zanim zaczniesz ticket, sprawdź w tabeli, z którego brancha wyjść, do którego zrobić PR i w którym katalogu pisać.

| Część | Tickety | Spec | Branch bazowy i cel PR | Katalog kodu | Źródła (tylko do odczytu) |
|---|---|---|---|---|---|
| Core (wspólny) | #4–#7 (CORE-1…4) | #2, #3 | `main` | `kompas-core/` | brak; core nie czyta żadnych materiałów |
| Wersja 1 | #8–#26 (V1-1…19) | #2 | `main` | `kompas-v1/` | `materiały/` |
| Wersja MC BDG | #27–#41 (M-1…15) | #3 | `kompas-mc-bdg` | `kompas-mc/` | `materialy mc/` |

**Nazwy branchy ticketów:**
- core i wersja 1: `<nr>-<krótki-opis>`, wychodzi z `main`, PR do `main` (np. `4-core-korpus`);
- wersja MC: `<nr>-mc-<krótki-opis>`, wychodzi z `kompas-mc-bdg`, PR do `kompas-mc-bdg` (np. `28-mc-logowanie`);
- interfejs wersji MC: `<nr>-mc-ui-<krótki-opis>`, wychodzi z brancha backendu tego ticketu, PR do `kompas-mc-bdg` (np. `28-mc-ui-logowanie` z `28-mc-logowanie`).

**Zasady:**
- **Nigdy nie rób PR z `kompas-mc-bdg` do `main`.** Wersje są rozdzielne. Wyjątkiem był jednorazowy PR #42 z materiałami startowymi.
- **Core trafia do wersji MC tylko przez merge `main` → `kompas-mc-bdg`.** Robi to integrator po każdym scalonym PR z core (#4–#7). Nie kopiuj kodu core do `kompas-mc/`.
- **`kompas-core/` zawiera wyłącznie mechanizmy:** adnotacje i walidator, korpus i wyszukiwanie, kalendarz terminów, silnik skali i progów, auth i historia zmian, `LlmProvider`, prymitywy PDF. Treść merytoryczna należy do konfiguracji danej wersji: reguły, kryteria, cytaty, formularze, dane demo.
- **`kompas-v1/` nie importuje niczego z `kompas-mc/` i odwrotnie.** Obie wersje korzystają tylko z `kompas-core/`. Każda ma własną konfigurację, bazę, dane demo i port.
- **Materiały w `materiały/` i `materialy mc/` są tylko do odczytu.** Nie zmieniaj ich nazw ani treści; zmień tylko ścieżkę w konfiguracji wersji.
- **Słowo `Closes #N` zamyka issue automatycznie tylko przy scaleniu do `main`.** Po scaleniu PR do `kompas-mc-bdg` zamknij ticket ręcznie, z komentarzem wskazującym PR.
- **Ticket może się zacząć, gdy wszystkie jego blokery są zamknięte** (sekcja „Blocked by” i zależności w GitHub).

## Podział pracy na 5 osób

Priorytet ma wersja MC BDG (#3), bo to ją ocenia jury. Wersja 1 (#8–#26) czeka do czasu, aż któryś tor skończy pracę.

| Osoba | Tor | Kolejność ticketów |
|---|---|---|
| **A** | źródła, core i integracja | #4 CORE-1 → #7 CORE-4 → #27 M-1 → #39 M-13 → #36 M-10. Przez cały czas integrator: scala PR-y, robi merge `main` → `kompas-mc-bdg`, recenzuje |
| **B** | interfejs wersji MC (`kompas-mc/frontend/`) | #6 CORE-3 → #28 M-2 → ekrany w kolejności ścieżki jurora: #28 → #29 → #30 → #31 → #32 → #37 → #35 → #33 → #36 → #34 → #38 → #39 |
| **C** | reguły i dokumenty | #5 CORE-2 → (w oczekiwaniu na #31: ekstrakcja pól wzorów arkuszy B, C i pierwszej oceny) → #32 M-6 → #33 M-7 → #34 M-8 |
| **D** | asystenci, rozmowa i HR | na start: zestaw pytań kontrolnych dla asystenta (≥15 z oczekiwanym dokumentem i paragrafem + ≥5 spoza bazy) oraz fikcyjni pracownicy dla mocka QNT → #37 M-11 → #35 M-9 → #38 M-12 |
| **E** | ścieżka oceny w MC | #29 M-3 → #30 M-4 → #31 M-5 |
| wszyscy | finał | #40 M-14 (demo i Playwright); #41 M-15 (materiały konkursowe, D i A) |

Wersja 1, jeśli zostanie czas: #8 → #9 → #11 → #12 → #13 (szkielet → profil → wybór procesu → kryteria → wynik § 11).

| Moment | Kto czeka | Na co | Co robi w tym czasie |
|---|---|---|---|
| start | nikt | — | A, B i C robią core, D przygotowuje dane |
| po core | B i D | #27 (A) | zaczynają na branchu wychodzącym z `27-mc-szkielet` |
| środek | C | #31 (E) | ekstrakcja pól formularzy |
| start E | E | #28 (B) | zaczyna #29 na branchu wychodzącym z `28-mc-logowanie` |

### Zasady pracy równoległej

- **Najpierw kontrakt.** W pierwszych 30–45 minutach każdy ticket core wystawia mały PR z samymi typami i interfejsami (`SourceRef`, walidator, API kalendarza, role, `LlmProvider`). Po jego scaleniu pozostali piszą kod pod te interfejsy.
- **Nakładane branche.** Jeśli bloker jest w toku, branch zależnego ticketu wychodzi z brancha blokera (np. `28-mc-logowanie` z `27-mc-szkielet`). PR otwiera się dopiero po scaleniu blokera i rebase na branch bazowy.
- **Osobny folder na ticket.** Każda osoba i każdy agent pracuje w osobnym `git worktree` (`git worktree add ../hn-<nr> <branch>`). Nie przełączaj branchy w folderze, w którym ktoś pracuje. Przed utworzeniem brancha zrób `git fetch` i wyjdź z aktualnego brancha bazowego.
- **Interfejs robi tylko B.** Pozostałe tory zmieniają `kompas-mc/backend/` i `kompas-mc/konfiguracja/`, a `kompas-mc/frontend/` zmienia tylko B. Kontraktem jest API: właściciel ticketu wpisuje w issue endpointy (OpenAPI w `/docs`), a B pisze „Biorę interfejs #N”. Właścicielem ticketu zostaje osoba od backendu i ticket zamyka się po scaleniu PR backendu; PR interfejsu ma `Refs #N` i nie blokuje kolejnych ticketów.
- **Zajmowanie ticketu.** Przed startem `gh issue edit <nr> --add-assignee @me` i wiadomość „Biorę #N” na busie drużyny (zob. `DRUZYNA.md`).
- **Koniec ticketu.** PR do brancha bazowego i „PR #… do odbioru” na busie. Komenda „Skończyłem #N, weź następny ticket z mojego toru” oznacza: następny ticket z tabeli toru, którego blokery są zamknięte. Pełny cykl ticketu opisuje skill `.agents/skills/praca-druzyny`.
- **Ticket bez właściciela.** Gdy tor skończy pracę wcześniej, bierze pierwszy ticket bez przypisanej osoby, którego wszystkie blokery są zamknięte.
