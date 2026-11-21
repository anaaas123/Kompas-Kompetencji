# AGENTS.md

## Agent skills

### Issue tracker

Issues live in GitHub Issues on `harn0ld/Kompas-Kompetencji` (via the `gh` CLI). See
`docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`,
`ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See
`docs/agents/domain.md`.

## Praca na ticketach

- Każdy ticket powstaje na branchu `<nr>-<krótki-opis>` utworzonym z aktualnego
  `main`.
- Każdy ticket ma osobny `git worktree`; nie przełączaj brancha w katalogu, w
  którym ktoś już pracuje.
- Przed rozpoczęciem sprawdź sekcję `Blocked by`, przypisz się przez
  `gh issue edit <nr> --add-assignee @me` i pobierz aktualny `main`.
- Kod aplikacji znajduje się w `kompas-mc/`, a współdzielone mechanizmy w
  `kompas-core/`. Materiały w `materialy mc/` są tylko do odczytu.
- Pull request kieruj do `main` i umieść w opisie `Closes #N`.
- Przed oddaniem uruchom testy i walidatory właściwe dla zmienianej części.
