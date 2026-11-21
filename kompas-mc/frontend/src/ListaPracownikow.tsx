import { useMemo, useState } from "react";
import type { Pracownik } from "./api";
import { Ikona } from "./Ikona";
import type { Sesja } from "./Konto";
import { Inicjaly, SzkieletListy, WierszListy } from "./Lista";
import { useSprawy } from "./Zespol";
import {
  data,
  dni,
  doZrobienia,
  NAZWA_ETAPU,
  NAZWA_SCIEZKI,
  osoby,
  pasuje,
  podzial,
  type FiltrPracownikow,
  type Sprawa,
} from "./zespol-dane";
import "./widoki.css";

/**
 * Pracownicy (makieta v3): „Do zrobienia” (ustalenie kryteriów, ocena końcowa, brak danych) i „Pozostali” (okres
 * oceny). W wierszu czynność i termin z /api/cykl, plakietka „po terminie N dni” albo „za N dni” (≤ 14 dni).
 * Wyszukiwarka i filtr z Zespołu jako znaczniki do zdjęcia. Wiersz otwiera kartę pracownika.
 */
function opisFiltra(f: FiltrPracownikow): string[] {
  const wynik: string[] = [];
  if (f.komorka) wynik.push(podzial(f.komorka).wydzial);
  if (f.termin) wynik.push(f.termin === "po_terminie" ? "po terminie" : "termin w ciągu 14 dni");
  if (f.etap) wynik.push(NAZWA_ETAPU[f.etap]);
  if (f.sciezka) wynik.push(NAZWA_SCIEZKI[f.sciezka]);
  if (f.ocena) wynik.push(f.ocena === "brak" ? "bez oceny okresowej" : `ostatnia ocena ${f.ocena}`);
  return wynik;
}

export function ListaPracownikow({
  sesja,
  filtr,
  onFiltr,
  onWybierz,
  onWyloguj,
}: {
  sesja: Sesja;
  filtr: FiltrPracownikow;
  onFiltr: (f: FiltrPracownikow) => void;
  onWybierz: (p: Pracownik) => void;
  onWyloguj: () => void;
}) {
  const { sprawy, blad } = useSprawy(sesja, onWyloguj);
  const [szukaj, setSzukaj] = useState("");
  const oceniany = sesja.uzytkownik.rola === "oceniany";

  const widoczne = useMemo(() => {
    const q = szukaj.trim().toLowerCase();
    return (sprawy ?? []).filter(
      (s) =>
        pasuje(s, filtr) &&
        (!q || `${s.osoba.imie} ${s.osoba.nazwisko} ${s.osoba.stanowisko} ${s.osoba.komorka}`.toLowerCase().includes(q)),
    );
  }, [sprawy, filtr, szukaj]);

  const znaczniki = opisFiltra(filtr);
  const sekcje: [string, Sprawa[]][] = [
    ["Do zrobienia", widoczne.filter(doZrobienia)],
    ["Pozostali", widoczne.filter((s) => !doZrobienia(s))],
  ];

  return (
    <div className="widok">
      <div className="naglowek-widoku">
        <h1>{oceniany ? "Twoje dane" : "Pracownicy"}</h1>
        {sprawy && (znaczniki.length > 0 || szukaj) && (
          <p className="meta">
            {osoby(widoczne.length)} z {sprawy.length}
          </p>
        )}
      </div>

      {!oceniany && sprawy && sprawy.length > 5 && (
        <label className="pole-zapytania szukaj-pracownika">
          <Ikona nazwa="szukaj" />
          <input
            value={szukaj}
            onChange={(e) => setSzukaj(e.target.value)}
            placeholder="Szukaj po nazwisku, stanowisku albo wydziale…"
            aria-label="Szukaj pracownika"
            autoComplete="off"
          />
        </label>
      )}
      {znaczniki.length > 0 && (
        <div className="filtry etykiety">
          {znaczniki.map((z) => (
            <span key={z} className="znacznik-filtra">
              {z}
            </span>
          ))}
          <button type="button" className="link" onClick={() => onFiltr({})}>
            Pokaż wszystkich
          </button>
        </div>
      )}

      {blad && <p className="blad">{blad}</p>}
      {!blad && !sprawy && <SzkieletListy wiersze={4} />}
      {sprawy && widoczne.length === 0 && <p className="meta">Nikt nie pasuje do wyszukiwania i filtra.</p>}

      {sekcje.map(
        ([tytul, ludzie]) =>
          ludzie.length > 0 && (
            <div key={tytul} className="sekcja">
              <h2>{tytul}</h2>
              <div className="lista">
                {ludzie.map((s) => (
                  <Wiersz key={s.osoba.osoba_id} s={s} onWybierz={onWybierz} />
                ))}
              </div>
            </div>
          ),
      )}
    </div>
  );
}

/** Plakietka terminu: czerwona po terminie, bursztynowa przy ≤ 14 dniach; dalej nic. */
export function PlakietkaTerminu({ s }: { s: Sprawa }) {
  const c = s.cykl;
  if (!c || c.dni_do_terminu === null) return null;
  if (c.po_terminie) return <span className="status negatywna">po terminie {dni(-c.dni_do_terminu)}</span>;
  if (c.dni_do_terminu === 0) return <span className="status uwaga">dziś</span>;
  if (c.dni_do_terminu <= 14) return <span className="status uwaga">za {dni(c.dni_do_terminu)}</span>;
  return null;
}

function Wiersz({ s, onWybierz }: { s: Sprawa; onWybierz: (p: Pracownik) => void }) {
  const o = s.osoba;
  const c = s.cykl;
  const sciezka = c?.sciezka ?? s.proponowana;
  return (
    <WierszListy
      lewa={<Inicjaly imie={o.imie} nazwisko={o.nazwisko} />}
      tytul={`${o.imie} ${o.nazwisko}`}
      znacznik={<PlakietkaTerminu s={s} />}
      opis={`${o.stanowisko} · ${sciezka ? NAZWA_SCIEZKI[sciezka] : podzial(o.komorka).wydzial}`}
      prawa={
        c && (
          <>
            <strong className="czynnosc-wiersza">{c.czynnosc}</strong>
            {c.termin && (
              <>
                <br />
                do {data(c.termin.data)}
              </>
            )}
          </>
        )
      }
      onClick={() => onWybierz(o)}
    />
  );
}
