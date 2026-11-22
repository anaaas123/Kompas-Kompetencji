import { useEffect, useState, type ReactNode } from "react";

// Czas animacji wyjścia z ocena.css (.zwijane.zamyka); przy „ogranicz ruch” treść znika od razu.
const WYJSCIE_MS = 160;

/** Treść rozwijana z animacją wejścia i wyjścia (opacity + przesunięcie, bez animowania wysokości). */
export function Zwijane({ otwarte, children }: { otwarte: boolean; children: ReactNode }) {
  const [widoczne, setWidoczne] = useState(otwarte);
  useEffect(() => {
    if (otwarte) {
      setWidoczne(true);
      return;
    }
    const bezRuchu = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const t = window.setTimeout(() => setWidoczne(false), bezRuchu ? 0 : WYJSCIE_MS);
    return () => window.clearTimeout(t);
  }, [otwarte]);
  if (!otwarte && !widoczne) return null;
  return <div className={`zwijane ${otwarte ? "" : "zamyka"}`}>{children}</div>;
}
