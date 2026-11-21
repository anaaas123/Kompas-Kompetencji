import { useCallback, useEffect, useState } from "react";
import { pobierzZrodla, type Zrodla } from "./api";
import AsystentFormalny from "./AsystentFormalny";
import { Logowanie, Pracownicy, type Sesja } from "./Konto";
import { Krok1 } from "./Krok1";
import { Krok2 } from "./Krok2";
import { Ocena } from "./Ocena";
import { Rozmowa } from "./Rozmowa";
import { Wynik } from "./Wynik";
import { Arkusz } from "./Arkusz";
import type { Pracownik, ProcesOceny } from "./api";
import PanelZrodel from "./PanelZrodel";

const PRZYKLADY = [
  "Kiedy przeprowadza się rozmowę wstępną?",
  "Ile kryteriów dodatkowych można wybrać?",
  "Ile dni ma pracownik na sprzeciw od oceny okresowej?",
];
const KLUCZ_SESJI = "kompas-mc-sesja";

type Zakladka = "asystent" | "zrodla";

export default function App() {
  const [blad, setBlad] = useState<string | null>(null);
  const [zrodla, setZrodla] = useState<Zrodla | null>(null);
  const [zakladka, setZakladka] = useState<Zakladka>("asystent");
  const [oceniany, setOceniany] = useState<Pracownik | null>(null);
  const [proces, setProces] = useState<ProcesOceny | null>(null);
  const [etap, setEtap] = useState<"krok2" | "ocena" | "rozmowa" | "wynik" | "arkusz">("krok2");
  const [sesja, setSesja] = useState<Sesja | null>(() => {
    const zapisana = sessionStorage.getItem(KLUCZ_SESJI);
    return zapisana ? (JSON.parse(zapisana) as Sesja) : null;
  });

  const zalogowano = useCallback((s: Sesja) => {
    sessionStorage.setItem(KLUCZ_SESJI, JSON.stringify(s));
    setSesja(s);
  }, []);

  const wyloguj = useCallback(() => {
    sessionStorage.removeItem(KLUCZ_SESJI);
    setSesja(null);
    setZakladka("asystent");
    setOceniany(null);
    setProces(null);
    setEtap("krok2");
  }, []);

  useEffect(() => {
    pobierzZrodla().then(setZrodla).catch(() => setBlad("Brak połączenia z API (port 8002)."));
  }, []);

  // Panel źródeł i braków widzi tylko HR/administrator (API też to egzekwuje).
  const panelDostepny = sesja?.uzytkownik.rola === "hr";
  const widok: Zakladka = panelDostepny ? zakladka : "asystent";

  return (
    <main>
      <header>
        <h1>Kompas Kompetencji</h1>
        <span className="znacznik">wersja MC BDG</span>
      </header>

      {!sesja && <Logowanie onZalogowano={zalogowano} />}
      {sesja && oceniany && !proces && (
        <Krok1
          token={sesja.token}
          osoba={oceniany}
          moznaProwadzic={sesja.uzytkownik.rola === "przelozony"}
          onWroc={() => setOceniany(null)}
          onDalej={setProces}
        />
      )}
      {sesja && oceniany && proces && etap === "krok2" && (
        <Krok2
          token={sesja.token}
          osoba={oceniany}
          proces={proces}
          moznaProwadzic={sesja.uzytkownik.rola === "przelozony"}
          onWstecz={() => setProces(null)}
          onDalej={() => setEtap("ocena")}
        />
      )}
      {sesja && oceniany && proces && etap === "ocena" && (
        <Ocena
          token={sesja.token}
          osoba={oceniany}
          proces={proces}
          moznaProwadzic={sesja.uzytkownik.rola === "przelozony"}
          onWstecz={() => setEtap("krok2")}
          onDalej={() => setEtap("rozmowa")}
        />
      )}
      {sesja && oceniany && proces && etap === "rozmowa" && (
        <Rozmowa
          token={sesja.token}
          osoba={oceniany}
          proces={proces}
          moznaProwadzic={sesja.uzytkownik.rola === "przelozony"}
          onWstecz={() => setEtap("ocena")}
          onDalej={() => setEtap("wynik")}
        />
      )}
      {sesja && oceniany && proces && etap === "wynik" && (
        <Wynik
          token={sesja.token}
          osoba={oceniany}
          proces={proces}
          moznaProwadzic={sesja.uzytkownik.rola === "przelozony"}
          onWstecz={() => setEtap("rozmowa")}
          onDalej={() => setEtap("arkusz")}
        />
      )}
      {sesja && oceniany && proces && etap === "arkusz" && (
        <Arkusz
          token={sesja.token}
          osoba={oceniany}
          proces={proces}
          moznaProwadzic={sesja.uzytkownik.rola === "przelozony"}
          onWstecz={() => setEtap("wynik")}
        />
      )}
      {sesja && !oceniany && (
        <Pracownicy
          sesja={sesja}
          onWyloguj={wyloguj}
          onWybierz={setOceniany}
        />
      )}

      {panelDostepny && (
        <nav className="zakladki" aria-label="Widok">
          <button className={widok === "asystent" ? "" : "jasny"} onClick={() => setZakladka("asystent")}>
            Asystent formalny
          </button>
          <button className={widok === "zrodla" ? "" : "jasny"} onClick={() => setZakladka("zrodla")}>
            Źródła i braki
          </button>
        </nav>
      )}

      {widok === "asystent" && (
        <section>
          <h2>Asystent formalny</h2>
          {blad && <p className="blad">{blad}</p>}
          {/* Na ekranach procesu asystent szuka tylko w rozporządzeniu jego ścieżki (#37). */}
          <AsystentFormalny sciezka={proces?.sciezka} przyklady={PRZYKLADY} />
        </section>
      )}

      {widok === "zrodla" && sesja && <PanelZrodel zrodla={zrodla} token={sesja.token} />}
    </main>
  );
}
