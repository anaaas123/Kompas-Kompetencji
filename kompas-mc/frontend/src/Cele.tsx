import { useEffect, useState } from "react";
import { pobierzPracownikow, type Pracownik } from "./api";
import { CeleOsoby } from "./CeleOsoby";
import type { Sesja } from "./Konto";
import { SzkieletListy } from "./Lista";

/**
 * Zakładka „Twoje cele” pracownika (#11). Przełożony dochodzi do celów osoby z jej karty
 * (Pracownicy → osoba → „Cele rozwojowe”), więc osobnej strony nie potrzebuje.
 */
export function Cele({ sesja, onWyloguj }: { sesja: Sesja; onWyloguj: () => void }) {
  const [ja, setJa] = useState<Pracownik | null>(null);
  const [blad, setBlad] = useState<string | null>(null);

  useEffect(() => {
    pobierzPracownikow(sesja.token)
      .then((l) => setJa(l[0] ?? null))
      .catch((e) => (String(e).includes("401") ? onWyloguj() : setBlad("Nie udało się pobrać danych.")));
  }, [sesja.token, onWyloguj]);

  return (
    <div className="widok">
      <div className="naglowek-widoku">
        <h1>Twoje cele rozwojowe</h1>
        <p className="meta">Cele omawiasz z przełożonym na początku okresu oceny (rozp. 2016 § 5 ust. 1 pkt 4).</p>
      </div>
      {blad && <p className="blad">{blad}</p>}
      {!blad && !ja && <SzkieletListy wiersze={2} />}
      {ja && <CeleOsoby sesja={sesja} osoba={ja} tytul="Cele" />}
    </div>
  );
}
