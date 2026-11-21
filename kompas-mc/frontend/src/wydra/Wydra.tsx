import { useEffect, useRef, useState } from "react";
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
  /** Jeden ruch przy pierwszym pokazaniu; domyślnie pierwszy ruch danej pozy. */
  naStart?: RuchWydry;
  /** Ruch po kliknięciu; domyślnie pierwszy ruch danej pozy. */
  naKlik?: RuchWydry;
  /** Czy wydra rusza się sama co kilka sekund (domyślnie tak). */
  samoczynnie?: boolean;
};

// Przerwa między samoczynnymi ruchami: losowa, żeby nie wyglądało jak metronom.
const PRZERWA_MIN = 6000;
const PRZERWA_MAX = 12000;

const losuj = <T,>(lista: readonly T[]) => lista[Math.floor(Math.random() * lista.length)];

const malyRuch = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

const KLATKI = [
  ["stoi", stoi],
  ["skok", skok],
  ["macha", macha],
  ["prosi", prosi],
  ["sklada", sklada],
] as const;

export function Wydra({
  poza = "stoi",
  szerokosc = 160,
  podskok,
  machanie,
  proszenie,
  naStart,
  naKlik,
  samoczynnie = true,
}: Props) {
  const dozwolony = (r?: RuchWydry) => (r && RUCHY[poza].includes(r) ? r : null);
  const [ruch, setRuch] = useState<RuchWydry | null>(dozwolony(naStart ?? RUCHY[poza][0]));

  // Nowy ruch w trakcie trwającego jest ignorowany: wydra najpierw kończy.
  // Ruch spoza bieżącej pozy też, bo skończyłby się na cudzej klatce.
  const rusz = (r: RuchWydry) => {
    if (dozwolony(r)) setRuch((obecny) => obecny ?? r);
  };

  useEffect(() => { if (podskok) rusz("podskok"); }, [podskok]);
  useEffect(() => { if (machanie) rusz("machanie"); }, [machanie]);
  useEffect(() => { if (proszenie) rusz("proszenie"); }, [proszenie]);
  // Zmiana pozy przerywa ruch. Porównanie z poprzednią pozą, bo sam efekt
  // odpala się też przy montowaniu i skasowałby ruch startowy.
  const poprzedniaPoza = useRef(poza);
  useEffect(() => {
    if (poprzedniaPoza.current === poza) return;
    poprzedniaPoza.current = poza;
    setRuch(null);
  }, [poza]);

  // Samoczynny ruch co kilka sekund; pomijany przy ograniczonym ruchu i w ukrytej karcie.
  useEffect(() => {
    if (!samoczynnie || malyRuch()) return;
    let licznik: number;
    const zaplanuj = () => {
      licznik = window.setTimeout(() => {
        if (!document.hidden) rusz(losuj(RUCHY[poza]));
        zaplanuj();
      }, PRZERWA_MIN + Math.random() * (PRZERWA_MAX - PRZERWA_MIN));
    };
    zaplanuj();
    return () => window.clearTimeout(licznik);
  }, [samoczynnie, poza]);

  return (
    <button
      type="button"
      className="wydra"
      style={{ width: szerokosc }}
      aria-label="Wydra Kompas"
      data-poza={poza}
      data-ruch={ruch ?? undefined}
      onClick={() => rusz(naKlik ?? RUCHY[poza][0])}
      // Najechanie myszą (nie dotyk, bo tam po dotknięciu przychodzi też klik).
      onPointerEnter={(e) => {
        if (e.pointerType === "mouse") rusz(losuj(RUCHY[poza]));
      }}
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
