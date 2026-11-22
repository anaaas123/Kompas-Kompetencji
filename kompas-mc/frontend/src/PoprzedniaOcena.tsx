import { useEffect, useState } from "react";
import { pobierzModelKompetencji, pobierzPoprzedniaOcene, type PoprzedniaOcenaOkresowa, type Pracownik } from "./api";
import { data } from "./zespol-dane";

// ponytail: skala arkuszy B i C z rozp. 2016 (1–9 co 2); przy zmianie przepisu skala przyjdzie z zapisanego arkusza.
const SKALA = [1, 3, 5, 7, 9];

const lata = (od: string) => Math.floor((Date.now() - Date.parse(od)) / (365.25 * 24 * 3600 * 1000));
const lat = (n: number) => (n === 1 ? "rok" : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 12 || n % 100 > 14) ? "lata" : "lat");

/** Jedno zdanie z kartoteki: stanowisko, staż, korpus, umowa, kierowanie zespołem. */
export function zdanieOOsobie(o: Pracownik): string {
  const n = lata(o.data_zatrudnienia);
  return [
    `${o.stanowisko.charAt(0).toUpperCase()}${o.stanowisko.slice(1)} od ${o.data_zatrudnienia.slice(0, 4)} r. (${n < 1 ? "poniżej roku" : `${n} ${lat(n)}`})`,
    `${o.korpus === "urzednik_sc" ? "urzędnik" : "pracownik"} służby cywilnej`,
    `umowa na czas ${o.rodzaj_umowy === "nieokreslony" ? "nieokreślony" : "określony"}`,
    o.kieruje_pracownikami ? "kieruje zespołem." : "nie kieruje zespołem.",
  ].join(", ");
}

// Nazwy kompetencji z modelu (dokument Model_kompetencji.xlsx); pobierane raz na sesję.
let nazwyKompetencji: Promise<Record<string, string>> | null = null;
const nazwy = (token: string) =>
  (nazwyKompetencji ??= pobierzModelKompetencji(token)
    .then((m) => Object.fromEntries(m.kompetencje.map((k) => [k.id, k.nazwa.charAt(0) + k.nazwa.slice(1).toLowerCase()])))
    .catch(() => ({})));

/** Poprzednia ocena z punktami; null, gdy jej nie ma albo użytkownik nie ma dostępu do treści ocen (HR). */
export function usePoprzedniaOcena(token: string, osobaId: string): PoprzedniaOcenaOkresowa | null {
  const [ocena, setOcena] = useState<PoprzedniaOcenaOkresowa | null>(null);
  useEffect(() => {
    let zyje = true;
    pobierzPoprzedniaOcene(token, osobaId)
      .then((o) => zyje && setOcena(o))
      .catch(() => zyje && setOcena(null));
    return () => {
      zyje = false;
    };
  }, [token, osobaId]);
  return ocena;
}

/** Poprzednia ocena okresowa: wynik, data i punkty za kryteria z arkusza (gdy kadry je mają). */
export function PoprzedniaOcena({ token, osoba }: { token: string; osoba: Pracownik }) {
  const ocena = usePoprzedniaOcena(token, osoba.osoba_id);
  const [nazwaKompetencji, setNazwy] = useState<Record<string, string>>({});
  useEffect(() => {
    nazwy(token).then(setNazwy);
  }, [token]);

  const o = ocena ?? osoba.ostatnia_ocena_okresowa;
  if (!o) {
    return (
      <div className="k1-blok">
        <h2>Poprzednia ocena</h2>
        <p className="meta">W kartotece nie ma poprzedniej oceny okresowej.</p>
      </div>
    );
  }
  const punkty = Object.entries(ocena?.punkty ?? {});
  const srednia = punkty.reduce((s, [, p]) => s + p, 0) / (punkty.length || 1);
  return (
    <div className="k1-blok">
      <div className="poprzednia-glowa">
        <h2>Poprzednia ocena</h2>
        <span className={`status ${o.wynik}`}>{o.wynik}</span>
        <span className="meta">{data(o.data)}</span>
      </div>
      {punkty.length > 0 && (
        <>
          <ul className="poprzednia">
            {punkty.map(([id, p]) => (
              <li key={id}>
                <span className="poprzednia-nazwa">{nazwaKompetencji[id] ?? id}</span>
                <span className="skala-pasek" role="img" aria-label={`${p} z 9 pkt`}>
                  {SKALA.map((s) => (
                    <span key={s} className={s <= p ? "pelny" : ""} />
                  ))}
                </span>
                <span className="poprzednia-pkt">{p} pkt</span>
              </li>
            ))}
          </ul>
          <p className="meta">Średnia {srednia.toFixed(2).replace(".", ",")} pkt</p>
        </>
      )}
    </div>
  );
}
