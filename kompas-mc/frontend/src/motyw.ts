import { useEffect, useState } from "react";

export type Motyw = "jasny" | "ciemny";

const KLUCZ = "kompas-motyw";
const system = () => window.matchMedia("(prefers-color-scheme: dark)");
const zapisany = (): Motyw | null => {
  const m = localStorage.getItem(KLUCZ);
  return m === "jasny" || m === "ciemny" ? m : null;
};
const zdarzenie = "kompas-motyw";

/** Ustawia `data-motyw` na <html>: wybór z przełącznika, a bez niego ustawienie systemu. Wołane przed renderem. */
export function ustawMotyw(): void {
  document.documentElement.dataset.motyw = zapisany() ?? (system().matches ? "ciemny" : "jasny");
  window.dispatchEvent(new Event(zdarzenie));
}

/** Przełącza motyw i zapamiętuje wybór; kolory przechodzą łagodnie, chyba że użytkownik ogranicza ruch. */
export function przelaczMotyw(): void {
  const nowy: Motyw = document.documentElement.dataset.motyw === "ciemny" ? "jasny" : "ciemny";
  const html = document.documentElement;
  if (!window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
    html.classList.add("motyw-przejscie");
    window.setTimeout(() => html.classList.remove("motyw-przejscie"), 320);
  }
  localStorage.setItem(KLUCZ, nowy);
  ustawMotyw();
}

/** Bieżący motyw do etykiety przełącznika; nadąża za zmianą systemu, gdy nie wybrano ręcznie. */
export function useMotyw(): Motyw {
  const [motyw, setMotyw] = useState<Motyw>(() => (document.documentElement.dataset.motyw as Motyw) ?? "jasny");
  useEffect(() => {
    const odswiez = () => setMotyw((document.documentElement.dataset.motyw as Motyw) ?? "jasny");
    const zSystemu = () => !zapisany() && ustawMotyw();
    window.addEventListener(zdarzenie, odswiez);
    system().addEventListener("change", zSystemu);
    return () => {
      window.removeEventListener(zdarzenie, odswiez);
      system().removeEventListener("change", zSystemu);
    };
  }, []);
  return motyw;
}
