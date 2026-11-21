import { useEffect, useState } from "react";
import stoi from "./wydra-stoi.webp";
import skok from "./wydra-skok.webp";
import macha from "./wydra-macha.webp";
import prosi from "./wydra-prosi.webp";
import sklada from "./wydra-sklada.webp";
import "./wydra.css";

/** Poza spoczynkowa: „stoi” macha łapką, „prosi” wyciąga łapkę w geście „proszę”. */
export type PozaWydry = "stoi" | "prosi";
export type RuchWydry = "podskok" | "machanie" | "proszenie";

// Ruchy dostępne w danej pozie: każdy zaczyna się i kończy na jej klatce spoczynkowej.
const RUCHY: Record<PozaWydry, RuchWydry[]> = {
  stoi: ["podskok", "machanie"],
  prosi: ["proszenie"],
};

// Animacja, której koniec oznacza koniec ruchu (działa też przy ograniczonym ruchu).
const KONIEC: Record<string, RuchWydry> = {
  "wydra-klatka": "podskok",
  "wydra-macha-klatka": "machanie",
  "wydra-proszenie-prosi": "proszenie",
};

type Props = {
  poza?: PozaWydry;
  /** Szerokość w px; wysokość wynika z proporcji klatek (578 × 649). */
  szerokosc?: number;
  /** Zmiana wartości (np. licznik) wywołuje dany ruch z zewnątrz. */
  podskok?: number;
  machanie?: number;
  proszenie?: number;
  /** Jeden ruch przy pierwszym pokazaniu. */
  naStart?: RuchWydry;
  /** Ruch po kliknięciu; domyślnie pierwszy ruch danej pozy. */
  naKlik?: RuchWydry;
};

const KLATKI = [
  ["stoi", stoi],
  ["skok", skok],
  ["macha", macha],
  ["prosi", prosi],
  ["sklada", sklada],
] as const;

export function Wydra({ poza = "stoi", szerokosc = 160, podskok, machanie, proszenie, naStart, naKlik }: Props) {
  const dozwolony = (r?: RuchWydry) => (r && RUCHY[poza].includes(r) ? r : null);
  const [ruch, setRuch] = useState<RuchWydry | null>(dozwolony(naStart));

  // Nowy ruch w trakcie trwającego jest ignorowany: wydra najpierw kończy.
  // Ruch spoza bieżącej pozy też, bo skończyłby się na cudzej klatce.
  const rusz = (r: RuchWydry) => {
    if (dozwolony(r)) setRuch((obecny) => obecny ?? r);
  };

  useEffect(() => { if (podskok) rusz("podskok"); }, [podskok]);
  useEffect(() => { if (machanie) rusz("machanie"); }, [machanie]);
  useEffect(() => { if (proszenie) rusz("proszenie"); }, [proszenie]);
  useEffect(() => setRuch(null), [poza]);

  return (
    <button
      type="button"
      className="wydra"
      style={{ width: szerokosc }}
      aria-label="Wydra Kompas"
      data-poza={poza}
      data-ruch={ruch ?? undefined}
      onClick={() => rusz(naKlik ?? RUCHY[poza][0])}
      onAnimationEnd={(e) => {
        if (KONIEC[e.animationName] === ruch) setRuch(null);
      }}
    >
      <span className="wydra__cien" aria-hidden />
      <span className="wydra__cialo" aria-hidden>
        {KLATKI.map(([nazwa, src]) => (
          <img
            key={nazwa}
            className={`wydra__klatka wydra__klatka--${nazwa}`}
            src={src}
            alt=""
            width={578}
            height={649}
            draggable={false}
          />
        ))}
      </span>
    </button>
  );
}
