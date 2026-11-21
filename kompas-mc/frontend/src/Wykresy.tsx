import type { ReactNode } from "react";

/** Elementy wizualne pulpitu, zespołu i karty: kafel z liczbą, pasek udziałów, postęp kroków. Kolor tylko ze znaczeniem. */

export function Kafel({
  etykieta,
  wartosc,
  opis,
  ton,
  onClick,
  wybrany,
}: {
  etykieta: string;
  wartosc: ReactNode;
  /** Podstawa liczby: z czego wychodzi. */
  opis: ReactNode;
  ton?: "uwaga" | "zle";
  onClick?: () => void;
  /** Kafel działa jak filtr listy: włączony stan widać na kaflu (aria-pressed). */
  wybrany?: boolean;
}) {
  const tresc = (
    <>
      <span className="kafel-etykieta">{etykieta}</span>
      <span className={`kafel-wartosc ${ton ?? ""}`}>{wartosc}</span>
      <span className="kafel-opis">{opis}</span>
    </>
  );
  return onClick ? (
    <button type="button" className="kafel" aria-pressed={wybrany} onClick={onClick}>
      {tresc}
    </button>
  ) : (
    <div className="kafel">{tresc}</div>
  );
}

export interface Udzial {
  nazwa: string;
  liczba: number;
  /** Klasa koloru z tokenów: dobrze, zle, uwaga, info, pusty. */
  ton: "dobrze" | "zle" | "uwaga" | "info" | "pusty";
  /** Kliknięcie pozycji legendy (np. przejście do listy z filtrem). */
  onClick?: () => void;
}

/** Poziomy pasek udziałów z legendą; liczby zawsze w legendzie, nie tylko w kolorze. */
export function PasekUdzialow({ tytul, udzialy, podstawa }: { tytul: string; udzialy: Udzial[]; podstawa: string }) {
  const suma = udzialy.reduce((a, u) => a + u.liczba, 0);
  return (
    <figure className="udzialy">
      <figcaption>
        <span className="kafel-etykieta">{tytul}</span>
        <span className="meta">{podstawa}</span>
      </figcaption>
      <div className="pasek" role="img" aria-label={udzialy.map((u) => `${u.nazwa}: ${u.liczba}`).join(", ")}>
        {suma > 0 &&
          udzialy
            .filter((u) => u.liczba > 0)
            .map((u) => <span key={u.nazwa} className={`odcinek ${u.ton}`} style={{ flexGrow: u.liczba }} />)}
      </div>
      <ul className="legenda">
        {udzialy.map((u) => (
          <li key={u.nazwa}>
            {u.onClick && u.liczba > 0 ? (
              <button type="button" className="pozycja-legendy" onClick={u.onClick}>
                <span className={`kropka ${u.ton}`} aria-hidden="true" />
                {u.nazwa} <strong>{u.liczba}</strong>
              </button>
            ) : (
              <>
                <span className={`kropka ${u.ton}`} aria-hidden="true" />
                {u.nazwa} <strong>{u.liczba}</strong>
              </>
            )}
          </li>
        ))}
      </ul>
    </figure>
  );
}

/** Postęp procesu: odcinek na każdy krok, zrobione wypełnione, bieżący w kolorze akcji. */
export function PostepKrokow({ krok, krokow, etykieta }: { krok: number; krokow: number; etykieta: string }) {
  return (
    <div className="postep" role="img" aria-label={`${etykieta}: krok ${krok} z ${krokow}`}>
      {Array.from({ length: krokow }, (_, i) => (
        <span key={i} className={i + 1 < krok ? "zrobiony" : i + 1 === krok ? "biezacy" : ""} />
      ))}
    </div>
  );
}
