import { useEffect, useState } from "react";
import {
  pobierzWnioski,
  type PropozycjaRozwoju,
  type Pracownik,
  type ProcesOceny,
  type SourceRef,
  type WnioskiProcesu,
} from "./api";
import { Zrodla, opisBledu } from "./Krok1";

function Propozycja({ p }: { p: PropozycjaRozwoju }) {
  const [komunikat, setKomunikat] = useState("");
  async function kopiuj() {
    const tekst = [
      `${p.kompetencja} · ${p.wskaznik}`,
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
        {p.kompetencja}
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
  const [dane, setDane] = useState<WnioskiProcesu | null>(null);
  const [blad, setBlad] = useState<string | null>(null);

  useEffect(() => {
    if (!moznaProwadzic) return;
    let aktywny = true;
    pobierzWnioski(token, proces.id)
      .then((d) => { if (aktywny) setDane(d); })
      .catch((err) => { if (aktywny) setBlad(opisBledu(err)); });
    return () => { aktywny = false; };
  }, [token, proces.id, moznaProwadzic]);

  const naglowek = (
    <section>
      <div className="wiersz">
        <div>
          <div className="etykieta">Krok 8 z 8 · Wnioski rozwojowe</div>
          <h2>
            {osoba.imie} {osoba.nazwisko}
          </h2>
          <p className="opis">
            {proces.sciezka === "okresowa" ? "ocena okresowa" : "pierwsza ocena"}
            {dane && ` · wynik oceny: ${dane.wynik_oceny ?? "jeszcze nie ma (krok 5 niekompletny)"}`}
          </p>
        </div>
        <button type="button" className="link" onClick={onWstecz}>
          Wróć do kroku 7
        </button>
      </div>
      {!moznaProwadzic && <p className="brak">Propozycje rozwoju przygotowuje i widzi tylko przełożony. Wnioski są w arkuszu (krok 7).</p>}
      {dane && (
        <p className="brak">
          {dane.propozycje.status}. Asystent niczego nie wpisuje: treść wniosków pisze przełożony.
        </p>
      )}
      {blad && <p className="blad">{blad}</p>}
      {moznaProwadzic && !dane && !blad && <p className="meta">Wczytuję propozycje…</p>}
    </section>
  );
  if (!dane) return naglowek;

  const pr = dane.propozycje;
  const obszary = pr.propozycje.filter((p) => p.typ === "OBSZAR_ROZWOJOWY");
  const mocne = pr.propozycje.filter((p) => p.typ === "MOCNA_STRONA");
  const formy = new Map<string, { nazwa: string; adnotacje: SourceRef[] }>();
  pr.propozycje.forEach((p) => p.formy.forEach((f) => formy.set(f.id, f)));

  return (
    <>
      {naglowek}

      {!pr.dostepne && pr.komunikat && (
        <section>
          <p className="brak">{pr.komunikat}</p>
        </section>
      )}

      {pr.dostepne && (
        <section>
          <h2>Propozycje z kroków 3–5</h2>
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
