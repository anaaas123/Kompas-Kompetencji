import { useEffect, useState } from "react";
import {
  pobierzWnioski,
  type PropozycjaRozwoju,
  type Pracownik,
  type ProcesOceny,
  type SourceRef,
  type WnioskiProcesu,
} from "./api";
import { Zrodla, nazwaKryterium, opisBledu } from "./Krok1";

function Propozycja({ p }: { p: PropozycjaRozwoju }) {
  const [komunikat, setKomunikat] = useState("");
  async function kopiuj() {
    const tekst = [
      `${nazwaKryterium(p.kompetencja)} · ${p.wskaznik}`,
      ...p.przyklady,
      ...p.formy.map((f) => f.nazwa),
      ...p.uwagi,
    ].join("\n");
    try {
      await navigator.clipboard.writeText(tekst);
      setKomunikat("Skopiowano propozycję.");
    } catch {
      setKomunikat("Schowek jest niedostępny. Zaznacz i skopiuj tekst propozycji ręcznie.");
    }
  }
  return (
    <li className="kryterium">
      <strong>{p.wskaznik}</strong>
      <p className="meta">
        {nazwaKryterium(p.kompetencja)}
        {p.poziom !== null && ` · poziom ${p.poziom}`}
      </p>
      {p.przyklady.map((x) => (
        <p key={x}>
          <span className="etykieta">Przykład:</span> {x}
        </p>
      ))}
      <div className="etykiety">
        {p.formy.map((f) => (
          <span key={f.id} className="znacznik">
            {f.nazwa}
          </span>
        ))}
      </div>
      {p.uwagi.map((u) => (
        <p key={u} className="brak">
          {u}
        </p>
      ))}
      <button className="link" type="button" onClick={kopiuj}>Kopiuj propozycję</button>
      <span className="meta" role="status">{komunikat}</span>
    </li>
  );
}

export function Wnioski({
  token,
  osoba,
  proces,
  moznaProwadzic,
  onWstecz,
}: {
  token: string;
  osoba: Pracownik;
  proces: ProcesOceny;
  moznaProwadzic: boolean;
  onWstecz: () => void;
}) {
  return (
    <section className="k7">
      <button type="button" className="link" onClick={onWstecz}>Wróć do oceny na piśmie</button>
      <h1>Propozycje rozwoju</h1>
      <p>{osoba.imie} {osoba.nazwisko} · {proces.sciezka === "okresowa" ? "Ocena okresowa" : "Pierwsza ocena"}</p>
      {moznaProwadzic ? <PropozycjeRozwoju token={token} procesId={proces.id} /> :
        <p>Propozycje rozwoju są dostępne dla przełożonego.</p>}
    </section>
  );
}

function usePropozycje(token: string, procesId: number) {
  const [dane, setDane] = useState<WnioskiProcesu | null>(null);
  const [blad, setBlad] = useState<string | null>(null);

  useEffect(() => {
    let aktywny = true;
    setDane(null);
    setBlad(null);
    pobierzWnioski(token, procesId)
      .then((d) => { if (aktywny) setDane(d); })
      .catch((err) => { if (aktywny) setBlad(opisBledu(err)); });
    return () => { aktywny = false; };
  }, [token, procesId]);

  return { dane, blad };
}

export function PropozycjeZwarte({ token, procesId, wartosc, onZmiana, blokada }: {
  token: string;
  procesId: number;
  wartosc: string | null;
  onZmiana: (tekst: string) => void;
  blokada: boolean;
}) {
  const { dane, blad } = usePropozycje(token, procesId);
  if (blad) return <p className="blad" role="alert">{blad}</p>;
  if (!dane?.propozycje.dostepne) return null;
  const lista = dane.propozycje.propozycje;
  const propozycje = [
    ...lista.filter((p) => p.typ === "OBSZAR_ROZWOJOWY"),
    ...lista.filter((p) => p.typ === "MOCNA_STRONA"),
  ].slice(0, 4);
  if (!propozycje.length) return null;

  function dodaj(tekst: string) {
    const separator = wartosc && !wartosc.endsWith("\n") ? "\n" : "";
    onZmiana((wartosc ?? "") + separator + tekst);
  }

  return (
    <div className="k7-propozycje">
      <h2>Propozycje rozwoju</h2>
      <ul>
        {propozycje.map((p, i) => {
          const nazwa = p.wskaznik || nazwaKryterium(p.kompetencja);
          const forma = p.formy[0]?.nazwa;
          const tekst = forma ? `${nazwa} — ${forma}` : nazwa;
          const id = "k7-propozycja-" + i;
          return (
            <li key={JSON.stringify([p.kompetencja, p.wskaznik_id ?? p.wskaznik])}>
              <span className="k7-propozycja" id={id} title={tekst}>
                <span>{nazwa}</span>{forma && <span> — {forma}</span>}
              </span>
              <button type="button" className="link" aria-describedby={id} disabled={blokada} onClick={() => dodaj(tekst)}>
                Dodaj do wniosków
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function PropozycjeRozwoju({ token, procesId }: { token: string; procesId: number }) {
  const { dane, blad } = usePropozycje(token, procesId);

  if (blad) return <p className="blad" role="alert">{blad}</p>;
  if (!dane) return <p className="meta">Wczytuję propozycje…</p>;

  const pr = dane.propozycje;
  const obszary = pr.propozycje.filter((p) => p.typ === "OBSZAR_ROZWOJOWY");
  const mocne = pr.propozycje.filter((p) => p.typ === "MOCNA_STRONA");
  const formy = new Map<string, { nazwa: string; adnotacje: SourceRef[] }>();
  pr.propozycje.forEach((p) => p.formy.forEach((f) => formy.set(f.id, f)));

  return (
    <>
      <p className="meta">{pr.status}</p>

      {!pr.dostepne && pr.komunikat && (
        <section>
          <p className="brak">{pr.komunikat}</p>
        </section>
      )}

      {pr.dostepne && (
        <section>
          {pr.propozycje.length === 0 && (
            <p className="meta">Wszystkie ocenione wskaźniki są na poziomie oczekiwań, więc asystent nie ma propozycji. Wnioski pisze przełożony.</p>
          )}
          {obszary.length > 0 && (
            <>
              <div className="etykieta">Obszary rozwojowe ({obszary.length})</div>
              <ul className="wskazniki">
                {obszary.map((p) => (
                  <Propozycja key={(p.wskaznik_id ?? p.wskaznik) + p.typ} p={p} />
                ))}
              </ul>
            </>
          )}
          {mocne.length > 0 && (
            <>
              <div className="etykieta">Mocne strony ({mocne.length})</div>
              <ul className="wskazniki">
                {mocne.map((p) => (
                  <Propozycja key={(p.wskaznik_id ?? p.wskaznik) + p.typ} p={p} />
                ))}
              </ul>
            </>
          )}
          {pr.pominiete.length > 0 && (
            <p className="meta">
              Pominięte: {pr.pominiete.map((x) => `${x.wskaznik} (${x.powod})`).join("; ")}.
            </p>
          )}
        </section>
      )}

      <section>
        <h2>Zasady propozycji</h2>
        <ul className="zadania">
          {pr.reguly.map((r) => (
            <li key={r.id}>
              {r.opis}
              <Zrodla adnotacje={r.adnotacje} />
            </li>
          ))}
        </ul>
        {formy.size > 0 && (
          <details className="pozostale">
            <summary>Skąd formy rozwoju ({pr.wersja_metodyki})</summary>
            <ul className="zadania">
              {[...formy.entries()].map(([id, f]) => (
                <li key={id}>
                  {f.nazwa}
                  <Zrodla adnotacje={f.adnotacje} />
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>
    </>
  );
}
