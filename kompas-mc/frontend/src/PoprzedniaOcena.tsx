import type { Pracownik } from "./api";
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

/** Poprzednia ocena okresowa: wynik, data i punkty za kryteria z arkusza (gdy kadry je mają). */
export function PoprzedniaOcena({ osoba }: { osoba: Pracownik }) {
  const o = osoba.ostatnia_ocena_okresowa;
  if (!o) {
    return (
      <div className="k1-blok">
        <h2>Poprzednia ocena</h2>
        <p className="meta">W kartotece nie ma poprzedniej oceny okresowej.</p>
      </div>
    );
  }
  const kryteria = o.kryteria ?? [];
  const srednia = kryteria.reduce((s, k) => s + k.punkty, 0) / (kryteria.length || 1);
  return (
    <div className="k1-blok">
      <div className="poprzednia-glowa">
        <h2>Poprzednia ocena</h2>
        <span className={`status ${o.wynik}`}>{o.wynik}</span>
        <span className="meta">{data(o.data)}</span>
      </div>
      {kryteria.length > 0 && (
        <>
          <ul className="poprzednia">
            {kryteria.map((k) => (
              <li key={k.kompetencja_id}>
                <span className="poprzednia-nazwa">{k.nazwa}</span>
                <span className="skala" role="img" aria-label={`${k.punkty} z 9 pkt`}>
                  {SKALA.map((s) => (
                    <span key={s} className={s <= k.punkty ? "pelny" : ""} />
                  ))}
                </span>
                <span className="poprzednia-pkt">{k.punkty} pkt</span>
              </li>
            ))}
          </ul>
          <p className="meta">
            Średnia {srednia.toFixed(2).replace(".", ",")} pkt z {kryteria.length} kryteriów · arkusz z akt osobowych
            (§ 12 ust. 2 rozporządzenia z 2016 r.) · dane demo
          </p>
        </>
      )}
    </div>
  );
}
