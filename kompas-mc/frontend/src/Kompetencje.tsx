import type { MapaKompetencji as Mapa, Pracownik } from "./api";
import { data, osoby as osobyTxt } from "./zespol-dane";

/**
 * Analiza kompetencji (#33): mapa osoby × kryteria z punktami ocen cząstkowych, podsumowanie „do rozwoju”
 * i „mocna strona”, oceny cząstkowe na karcie. Kolor tylko ze znaczeniem (poniżej, na poziomie, powyżej
 * oczekiwań) i zawsze z liczbą w komórce. Źródło przy każdej osobie: ostatnia ocena z akt albo bieżąca ocena.
 */

/** Nazwa kryterium z modelu bywa wersalikami: „KOMUNIKACJA” → „Komunikacja”. */
export const nazwaKryterium = (n: string) => n.charAt(0).toUpperCase() + n.slice(1).toLowerCase();

const ton = (pkt: number, oczekiwany: number) => (pkt < oczekiwany ? "ponizej" : pkt > oczekiwany ? "powyzej" : "na-poziomie");
const zrodloTxt = (o: Mapa["osoby"][number]) =>
  o.zrodlo === "biezaca_ocena" ? "bieżąca ocena" : `ocena z ${o.data ? data(o.data) : "akt"}`;
const srednia = (w: number[]) => w.reduce((a, b) => a + b, 0) / w.length;
const liczba = (x: number) => x.toFixed(1).replace(".", ",");

interface Wniosek {
  nazwa: string;
  tekst: string;
}

/** Kryterium do rozwoju: najwięcej osób poniżej oczekiwań (co najmniej 2); mocna strona: najwyższa średnia > 5. */
function wnioski(m: Mapa, osoby: Mapa["osoby"]): { slabe: Wniosek | null; mocne: Wniosek | null } {
  const staty = m.kryteria
    .map((k) => {
      const w = osoby.map((o) => o.punkty[k.kompetencja_id]).filter((x): x is number => x !== undefined);
      return { k, w, ponizej: w.filter((x) => x < m.poziom_oczekiwan).length };
    })
    .filter((s) => s.w.length > 0);
  const slabe = [...staty].sort((a, b) => b.ponizej - a.ponizej || srednia(a.w) - srednia(b.w))[0];
  const mocne = [...staty].sort((a, b) => srednia(b.w) - srednia(a.w))[0];
  return {
    slabe:
      slabe && slabe.ponizej >= 2
        ? {
            nazwa: nazwaKryterium(slabe.k.nazwa),
            tekst: `${slabe.ponizej} z ${osobyTxt(slabe.w.length)} poniżej oczekiwań (średnio ${liczba(srednia(slabe.w))} pkt)`,
          }
        : null,
    mocne:
      mocne && srednia(mocne.w) > m.poziom_oczekiwan
        ? { nazwa: nazwaKryterium(mocne.k.nazwa), tekst: `średnio ${liczba(srednia(mocne.w))} pkt u ${osobyTxt(mocne.w.length)}` }
        : null,
  };
}

export function MapaKompetencji({
  mapa,
  ludzie,
  onWybierz,
}: {
  mapa: Mapa;
  /** Osoby w wybranej komórce (zakres Zespołu); mapa pokazuje tylko je. */
  ludzie: Pracownik[];
  onWybierz?: (p: Pracownik) => void;
}) {
  const poId = new Map(ludzie.map((p) => [p.osoba_id, p]));
  const osoby = mapa.osoby.filter((o) => poId.has(o.osoba_id));
  const bez = ludzie.length - osoby.length;
  const kryteria = mapa.kryteria.filter((k) => osoby.some((o) => o.punkty[k.kompetencja_id] !== undefined));
  const { slabe, mocne } = wnioski({ ...mapa, kryteria }, osoby);
  const pokazRozbieznosci = osoby.some((o) => o.rozbieznosci !== null);

  return (
    <section className="mapa-kompetencji">
      <h2>Kompetencje zespołu</h2>
      {osoby.length === 0 ? (
        <p className="meta zero">Nikt w tej komórce nie ma jeszcze oceny z punktami za kryteria.</p>
      ) : (
        <>
          <div className="wnioski-mapy">
            {slabe && (
              <p className="wniosek do-rozwoju">
                <span className="kafel-etykieta">Do rozwoju w zespole</span>
                <strong>{slabe.nazwa}</strong>
                <span>{slabe.tekst}</span>
              </p>
            )}
            {mocne && (
              <p className="wniosek mocna">
                <span className="kafel-etykieta">Mocna strona zespołu</span>
                <strong>{mocne.nazwa}</strong>
                <span>{mocne.tekst}</span>
              </p>
            )}
          </div>
          <div className="tabela-mapy" role="region" aria-label="Mapa kompetencji: osoby i kryteria" tabIndex={0}>
            <table>
              <thead>
                <tr>
                  <th scope="col">Osoba</th>
                  {kryteria.map((k) => (
                    <th key={k.kompetencja_id} scope="col">
                      {nazwaKryterium(k.nazwa)}
                    </th>
                  ))}
                  {pokazRozbieznosci && <th scope="col">Samoocena: do omówienia</th>}
                </tr>
              </thead>
              <tbody>
                {osoby.map((o) => {
                  const p = poId.get(o.osoba_id)!;
                  return (
                    <tr key={o.osoba_id}>
                      <th scope="row">
                        {onWybierz ? (
                          <button type="button" className="link" onClick={() => onWybierz(p)}>
                            {p.imie} {p.nazwisko}
                          </button>
                        ) : (
                          `${p.imie} ${p.nazwisko}`
                        )}
                        <span className="meta">{zrodloTxt(o)}</span>
                      </th>
                      {kryteria.map((k) => {
                        const v = o.punkty[k.kompetencja_id];
                        return v === undefined ? (
                          <td key={k.kompetencja_id} className="brak-kryterium" title="kryterium spoza arkusza tej osoby">
                            –
                          </td>
                        ) : (
                          <td key={k.kompetencja_id} className={`komorka-mapy ${ton(v, mapa.poziom_oczekiwan)}`}>
                            {v}
                          </td>
                        );
                      })}
                      {pokazRozbieznosci && <td>{o.rozbieznosci ?? "–"}</td>}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="legenda-mapy">
            <span className="probka ponizej" aria-hidden="true" /> poniżej oczekiwań (1, 3)
            <span className="probka na-poziomie" aria-hidden="true" /> na poziomie (5)
            <span className="probka powyzej" aria-hidden="true" /> powyżej (7, 9)
            <span className="meta">
              Punkty ocen cząstkowych ({mapa.skala.join(", ")}): z ostatniej oceny okresowej w aktach albo z bieżącej oceny.
              {bez > 0 && ` Bez oceny z punktami: ${osobyTxt(bez)}.`}
            </span>
          </p>
        </>
      )}
    </section>
  );
}

/** Karta pracownika: oceny cząstkowe ostatniej oceny z akt (bieżącą pokazuje sekcja ocen kryteriów). */
export function OcenyCzastkowe({ mapa, osoba }: { mapa: Mapa | null; osoba: Pracownik }) {
  const o = mapa?.osoby.find((x) => x.osoba_id === osoba.osoba_id && x.zrodlo === "ostatnia_ocena");
  if (!mapa || !o) return null;
  const max = Math.max(...mapa.skala);
  return (
    <div className="sekcja">
      <h2>Ostatnia ocena: kryteria</h2>
      <p className="meta zero">
        Oceny cząstkowe z oceny okresowej {o.data ? `z ${data(o.data)}` : ""} (akta), skala 1–{max} pkt
      </p>
      <ul className="slupki">
        {mapa.kryteria
          .filter((k) => o.punkty[k.kompetencja_id] !== undefined)
          .map((k) => {
            const v = o.punkty[k.kompetencja_id];
            return (
              <li key={k.kompetencja_id}>
                <span className="nazwa-slupka">{nazwaKryterium(k.nazwa)}</span>
                <span className="tor" title={`${v} z ${max} pkt`}>
                  <span className={`wypelnienie ${ton(v, mapa.poziom_oczekiwan)}`} style={{ width: `${(v / max) * 100}%` }} />
                </span>
                <strong className="wartosc-slupka">{v}</strong>
              </li>
            );
          })}
      </ul>
    </div>
  );
}
