import type { ReactNode } from "react";
import { Ikona } from "./Ikona";

/** Wiersz listy jak w mObywatelu: jasne tło (--k-wiersz), ikona albo inicjały z lewej, strzałka z prawej. */
export function WierszListy({
  lewa,
  tytul,
  znacznik,
  opis,
  prawa,
  onClick,
  maly,
}: {
  lewa?: ReactNode;
  tytul: ReactNode;
  znacznik?: ReactNode;
  opis?: ReactNode;
  prawa?: ReactNode;
  onClick?: () => void;
  maly?: boolean;
}) {
  const tresc = (
    <>
      {lewa && <span className="pozycja-lewa">{lewa}</span>}
      <span className="pozycja-srodek">
        <span className="pozycja-tytul">
          {tytul}
          {znacznik}
        </span>
        {opis && <span className="pozycja-opis">{opis}</span>}
      </span>
      {prawa && <span className="pozycja-prawa">{prawa}</span>}
      {onClick && (
        <span className="pozycja-strzalka">
          <Ikona nazwa="dalej" rozmiar={24} />
        </span>
      )}
    </>
  );
  const klasa = `pozycja ${maly ? "mala" : ""}`;
  return onClick ? (
    <button type="button" className={klasa} onClick={onClick}>
      {tresc}
    </button>
  ) : (
    <div className={klasa}>{tresc}</div>
  );
}

export function Inicjaly({ imie, nazwisko }: { imie: string; nazwisko: string }) {
  return (
    <span className="inicjaly" aria-hidden="true">
      {imie.charAt(0)}
      {nazwisko.charAt(0)}
    </span>
  );
}

/** Szkielet listy na czas wczytywania: kształt wierszy, bez kręcącego się wskaźnika. */
export function SzkieletListy({ wiersze = 3 }: { wiersze?: number }) {
  return (
    <div className="lista" aria-busy="true" aria-label="Wczytuję">
      {Array.from({ length: wiersze }, (_, i) => (
        <div key={i} className="pozycja szkielet" />
      ))}
    </div>
  );
}
