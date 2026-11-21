import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  pobierzKrok1,
  pobierzPracownikow,
  pobierzProcesy,
  type Pracownik,
  type ProcesOceny,
  type Sciezka,
} from "./api";
import { Ikona } from "./Ikona";
import { Inicjaly, SzkieletListy, WierszListy } from "./Lista";
import type { Sesja } from "./Konto";

/**
 * Pulpit (strona główna) w stylu mObywatela: jedno pole „znajdź pracownika albo zapytaj”, lista spraw
 * z danych API (procesy w toku, potem osoby z proponowaną ścieżką z analizy kroku 1) i pytania o zasady,
 * które otwierają asystenta formalnego. Terminów API jeszcze nie zwraca, więc pulpit ich nie liczy.
 */
const ZASADY = [
  "Co omawia się na rozmowie oceniającej?",
  "Kiedy ocena okresowa jest negatywna?",
  "Ile dni ma pracownik na sprzeciw od oceny okresowej?",
];
const NAZWA_SCIEZKI: Record<Sciezka, string> = { pierwsza: "pierwsza ocena", okresowa: "ocena okresowa" };

interface Sprawa {
  osoba: Pracownik;
  proces: ProcesOceny | null;
  proponowana: Sciezka | null;
}

function nastepnyKrok(s: Sprawa): string {
  if (s.proces) return `Ocena w toku · krok ${s.proces.krok}`;
  if (s.proponowana === "pierwsza") return "Rozpocznij pierwszą ocenę";
  if (s.proponowana === "okresowa") return "Rozpocznij ocenę okresową";
  return "Ustal ścieżkę oceny";
}

export function Pulpit({
  sesja,
  onWybierz,
  onZapytaj,
  onWyloguj,
}: {
  sesja: Sesja;
  onWybierz: (p: Pracownik) => void;
  onZapytaj: (pytanie: string) => void;
  onWyloguj: () => void;
}) {
  const [sprawy, setSprawy] = useState<Sprawa[] | null>(null);
  const [blad, setBlad] = useState<string | null>(null);
  const [szukaj, setSzukaj] = useState("");
  const rola = sesja.uzytkownik.rola;

  useEffect(() => {
    let aktualne = true;
    (async () => {
      try {
        const [osoby, procesy] = await Promise.all([pobierzPracownikow(sesja.token), pobierzProcesy(sesja.token)]);
        const wynik = await Promise.all(
          osoby.map(async (osoba): Promise<Sprawa> => {
            const proces = procesy.find((p) => p.osoba_id === osoba.osoba_id && p.status === "W_TOKU") ?? null;
            if (proces) return { osoba, proces, proponowana: proces.sciezka };
            // Analiza kroku 1 podaje proponowaną ścieżkę; jej brak nie blokuje pulpitu.
            const analiza = await pobierzKrok1(sesja.token, osoba.osoba_id).catch(() => null);
            return { osoba, proces: null, proponowana: analiza?.sciezka.proponowana ?? null };
          }),
        );
        // Najpierw oceny w toku, potem osoby do rozpoczęcia.
        wynik.sort((a, b) => Number(!!b.proces) - Number(!!a.proces));
        if (aktualne) setSprawy(wynik);
      } catch (err) {
        if (String(err).includes("401")) onWyloguj();
        else if (aktualne) setBlad("Nie udało się pobrać spraw.");
      }
    })();
    return () => {
      aktualne = false;
    };
  }, [sesja.token, onWyloguj]);

  const widoczne = useMemo(() => {
    const q = szukaj.trim().toLowerCase();
    if (!sprawy || !q) return sprawy;
    return sprawy.filter((s) => `${s.osoba.imie} ${s.osoba.nazwisko}`.toLowerCase().includes(q));
  }, [sprawy, szukaj]);

  function wyslij(e: FormEvent) {
    e.preventDefault();
    const q = szukaj.trim();
    if (!q) return;
    // Jedna osoba pasuje do wpisu: otwórz ją; inaczej to pytanie do asystenta.
    if (widoczne && widoczne.length === 1) onWybierz(widoczne[0].osoba);
    else onZapytaj(q);
  }

  return (
    <div className="pulpit">
      <div className="pulpit-glowa">
        <h1>Na dziś</h1>
        <form className="pole-zapytania" role="search" onSubmit={wyslij}>
          <Ikona nazwa="szukaj" />
          <input
            value={szukaj}
            onChange={(e) => setSzukaj(e.target.value)}
            placeholder="Znajdź pracownika albo zapytaj o zasady oceny…"
            aria-label="Znajdź pracownika albo zapytaj o zasady oceny"
            autoComplete="off"
          />
          <button type="submit" className="wyslij" aria-label="Wyślij" disabled={!szukaj.trim()}>
            <Ikona nazwa="gora" />
          </button>
        </form>
      </div>

      <div className="dwie">
        <div className="sekcja">
          <h2>{rola === "przelozony" ? "Do zrobienia" : rola === "hr" ? "Oceny w urzędzie" : "Twoja ocena"}</h2>
          {blad && <p className="blad">{blad}</p>}
          {!blad && widoczne === null && <SzkieletListy />}
          {widoczne?.length === 0 && (
            <p className="meta">{szukaj ? "Nikt nie pasuje do wpisu. Enter wyśle go jako pytanie do asystenta." : "Brak osób w Twoim zakresie."}</p>
          )}
          {widoczne && widoczne.length > 0 && (
            <div className="lista">
              {widoczne.map((s) => (
                <WierszListy
                  key={s.osoba.osoba_id}
                  lewa={<Inicjaly imie={s.osoba.imie} nazwisko={s.osoba.nazwisko} />}
                  tytul={`${s.osoba.imie} ${s.osoba.nazwisko}`}
                  znacznik={
                    s.proponowana && (
                      <span className={`status ${s.proces ? "uwaga" : "neutralna"}`}>{NAZWA_SCIEZKI[s.proponowana]}</span>
                    )
                  }
                  opis={`${nastepnyKrok(s)} · ${s.osoba.stanowisko}`}
                  onClick={() => onWybierz(s.osoba)}
                />
              ))}
            </div>
          )}
        </div>

        <div className="sekcja">
          <h2>Zasady</h2>
          <div className="lista ciasna">
            {ZASADY.map((z) => (
              <WierszListy key={z} maly lewa={<Ikona nazwa="pytanie" />} tytul={z} onClick={() => onZapytaj(z)} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
