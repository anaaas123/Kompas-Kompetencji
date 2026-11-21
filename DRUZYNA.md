# Praca w zespole na HackNation

## Start każdego laptopa

| Co otworzyć | Wpisuje prowadzący po utworzeniu projektu |
|---|---|
| Repo z kodem | … |
| Prywatny wątek „Bus drużyny” | … |
| Issue „Demo i zgłoszenie” | … |
| Discord drużyny | … |

Prowadzący uzupełnia tę kartę w repo po uzgodnieniu dostępu. Przed rozpakowaniem paczki sprawdza, czy projekt ma już szablony GitHub, i łączy je z istniejącymi. Gdy kod będzie udostępniony jurorom lub publicznie, wątek od początku trzymamy w osobnym prywatnym repo zespołu. Link do prywatnego kanału i lista uczestników zostają po stronie prywatnej. Nie zamieszczajcie publicznego zaproszenia. W publicznej kopii karty zostawcie uczestnikom wskazówkę, gdzie otrzymają adres busa.

## Start pracy — Kompas Kompetencji

**Krok 0 (każdy):** `git pull` na `main`, uruchom agenta w folderze repo i wklej mu swoją wiadomość. Tory i kolejność ticketów są w [AGENTS.md](AGENTS.md#podział-pracy-na-5-osób).

**🅰️ A: źródła, core, integracja**
> Jestem osobą A z podziału w AGENTS.md. Biorę #4. Przeczytaj AGENTS.md, DRUZYNA.md i skill praca-druzyny. Przypisz mnie do issue, utwórz worktree dla brancha `4-core-korpus` i zacznij od małego PR z samymi interfejsami (SourceRef, walidator), potem implementacja.

Dalej: #7 → #27 → #39 → #36. A scala PR-y i robi merge `main` → `kompas-mc-bdg` po każdym tickecie core.

**🅱️ B: interfejs wersji MC**
> Jestem osobą B z podziału w AGENTS.md. Kończę #28, potem robię interfejs wersji MC w `kompas-mc/frontend/`. Przeczytaj AGENTS.md, DRUZYNA.md i skill praca-druzyny. Przy każdym ekranie napisz w issue „Biorę interfejs #N” i utwórz worktree dla brancha `<nr>-mc-ui-<opis>` z brancha backendu tego ticketu.

Dalej: ekrany #28 → #29 → #30 → #31 → #32 → #37 → #35 → #33 → #36 → #34 → #38 → #39.

**©️ C: reguły i dokumenty**
> Jestem osobą C z podziału w AGENTS.md. Biorę #5. Przeczytaj AGENTS.md, DRUZYNA.md i skill praca-druzyny. Przypisz mnie do issue, utwórz worktree dla brancha `5-core-kalendarz` i zacznij od małego PR z samymi interfejsami (kalendarz terminów, silnik skali i progów), potem implementacja.

Dalej: ekstrakcja pól arkuszy (w oczekiwaniu na #31) → #32 → #33 → #34.

**🇩 D: asystenci, rozmowa, HR**
> Jestem osobą D z podziału w AGENTS.md. Na start przygotowuję dane bez blokerów: zestaw ≥15 pytań kontrolnych dla asystenta formalnego (z oczekiwanym dokumentem i paragrafem z folderu „materialy mc”) + ≥5 pytań spoza bazy do #37 oraz fikcyjnych pracowników dla mocka QNT do #28. Przeczytaj AGENTS.md, DRUZYNA.md, skill praca-druzyny i issue #37 oraz #28.

Dalej: #37 → #35 → #38.

**🇪 E: ścieżka oceny MC**
> Jestem osobą E z podziału w AGENTS.md. Biorę #29. Przeczytaj AGENTS.md, DRUZYNA.md i skill praca-druzyny. Przypisz mnie do issue, utwórz worktree dla brancha `29-mc-osp` z brancha `28-mc-logowanie` (#28 w toku) i zacznij od endpointów kroku 1, które wpiszesz w issue jako kontrakt dla interfejsu, potem implementacja.

Dalej: #30 → #31.

**Cykl ticketu:**
- Przed startem: przypisz się w GitHub i napisz na busie „Biorę #N”.
- Każdy ticket w osobnym `git worktree`. Czyjś folder zostaje na jego branchu.
- Bloker w toku? Twój branch wychodzi z brancha blokera, PR otwierasz po jego scaleniu.
- Koniec: PR do `main` (core) albo `kompas-mc-bdg` (MC) i „PR #… do odbioru” na busie. Potem powiedz agentowi: „Skończyłem #N, weź następny ticket z mojego toru”.
- PR-y idą zawsze do własnego brancha bazowego; `kompas-mc-bdg` nigdy nie trafia do `main`.
- Blokada: „@osoba BLOKADA #N — czego brakuje”. Bez odpowiedzi w 2 min wołamy głosem.

Na końcu wszyscy: #40 (próba demo) i #41 (opis, prezentacja do 10 slajdów, opis AI — D i A).

## Jak się dogadać

- Rozmowa od razu: przy stole lub na jednym prywatnym kanale Discord drużyny. Przypnijcie w nim kartę zespołu i adres wątku „Bus drużyny”. Sprawdźcie, kto ma dostęp. Ustawcie powiadomienia na wzmianki. Pilny temat kierujcie do jednej osoby.
- Bus dla różnych laptopów i agentów: przypnijcie jedno issue „Bus drużyny”. W jego opisie trzymajcie link do demo i aktualne zależności. Wysyłajcie krótką blokadę, pytanie o zależność albo prośbę o odbiór. „@ola BLOKADA #12 — czy import może zwrócić pustą listę?” Odpowiedź „Biorę” oznacza przejęcie. Po dwóch minutach bez odpowiedzi zawołajcie człowieka. Jedna wiadomość w jednym miejscu wystarczy, na czacie podajcie link, gdy potrzebna jest reakcja od ręki.
- Pamięć: ustalenie dopiszcie do issue zadania. Do PR dołączcie wynik rzeczywistej próby. Przy przekazaniu wystarczą numer issue, wersja lub PR, ostatnia udana próba i następny krok. Przy braku internetu przekażcie blokadę ustnie, zapiszcie wynik lokalnie i po odzyskaniu połączenia uzupełnijcie właściwe issue.

Każdy człowiek i jego asystent używają [tego samego skilla](.agents/skills/praca-druzyny/SKILL.md). Pierwszy komunikat dla agenta może brzmieć „Przeczytaj DRUZYNA.md i podany tam skill. Pomagasz mi przy #12. Sprawdź nowe wiadomości i powiedz, na co ktoś czeka ode mnie”. Podstaw własny numer. Agent z dostępem do powłoki i zalogowanego GitHub CLI może czytać bus po ID ostatniej wiadomości oraz czekać na odpowiedź. Gdy uczestnik nie ma CLI, ten sam adres działa w przeglądarce. Zamknięty agent odczyta zaległości po wznowieniu.

## Próba na dwóch kontach przed kodowaniem · 10 minut

1. Prowadzący sprawdza widoczność prywatnego repo i osoby z dostępem, tworzy issue, wpisuje adres do karty, otwiera link w wylogowanym oknie i sprawdza odmowę dostępu.
2. Ola publikuje nowy komentarz z pytaniem i oznacza drugą osobę. Druga osoba potwierdza z własnego laptopa. Mierzycie czas do potwierdzenia. Potem sprawdzacie wzmiankę na Discordzie z telefonu z zablokowanym ekranem. Jeśli reakcja przekracza dwie minuty, przy pilnej blokadzie wołajcie się głosowo.
3. Agent odczytuje pytanie, podaje autora i ostatnie ID. Wyłączcie połączenie na laptopie odbiorcy. Druga osoba dodaje odpowiedź. Po powrocie sieci uruchomcie nową sesję i odczytajcie z poprzednim ID. Sukces oznacza odnalezienie odpowiedzi i wskazanie następnego kroku bez opowiadania historii od nowa. Na laptopie bez CLI użyjcie przeglądarki. Właściciel może wtedy wkleić agentowi konkretny komentarz.

## Jak poprowadzić projekt

Prowadzący integrację zapisuje w przypiętym issue „Demo i zgłoszenie” jeden scenariusz jurora, kryteria, osobę od zgłoszenia i zastępstwo. Dzielicie pracę na niezależne wyniki. Każde zadanie ma jednego ludzkiego właściciela, przykład wejścia i oczekiwany wynik. Zależne osoby uzgadniają ten sam przykład przed rozpoczęciem implementacji. Recenzent uruchamia próbę z PR. Po scaleniu integrator odtwarza scenariusz jurora na wspólnej wersji. Jeśli dwa repo są rozdzielone, w wiadomościach używajcie pełnego URL issue lub PR z drugiego repo.

Pracujemy przez PR: zmiana powstaje na gałęzi z numerem zadania, robimy z niej PR, a po odbiorze scalamy go z branchem bazowym. Core (#4–#7) i wersja 1 (#8–#26) mają bazę w `main`. Wersja MC BDG (#27–#41) ma bazę w `kompas-mc-bdg` i nigdy nie trafia do `main`. Tabela branchy, katalogów i źródeł jest w [AGENTS.md](AGENTS.md#branche-i-miejsca-pracy). Po każdym scalonym PR z core integrator robi merge `main` → `kompas-mc-bdg`.

Na HackNation 2026 draft w HackTribe jest wymagany do 20:00 w sobotę, a końcowe zgłoszenie do 11:00 w niedzielę. Osoba od zgłoszenia potwierdza draft i finał na platformie.
