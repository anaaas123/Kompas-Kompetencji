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

/**
 * Profil zespołu: średnia na kryterium na skali arkusza (1–9) z linią poziomu oczekiwań. Średnia zaokrąglona
 * do 0,1 decyduje o tonie: poniżej oczekiwań attention, powyżej success, równa neutralny. Przy każdej liczba i podstawa.
 */
function ProfilKompetencji({ mapa, osoby, kryteria }: { mapa: Mapa; osoby: Mapa["osoby"]; kryteria: Mapa["kryteria"] }) {
  const [min, max] = [Math.min(...mapa.skala), Math.max(...mapa.skala)];
  const pozycja = (v: number) => `${((v - min) / (max - min)) * 100}%`;
  return (
    <figure className="udzialy profil">
      <figcaption>
        <span className="kafel-etykieta">Średnia zespołu na kryterium</span>
        <span className="meta">
          skala {min}–{max} pkt; pionowa linia to poziom oczekiwań ({mapa.poziom_oczekiwan} pkt); liczba osób z punktami za kryterium
        </span>
      </figcaption>
      <ul className="profil-lista">
        {kryteria.map((k) => {
          const w = osoby.map((o) => o.punkty[k.kompetencja_id]).filter((x): x is number => x !== undefined);
          const sr = Math.round(srednia(w) * 10) / 10;
          const t = ton(sr, mapa.poziom_oczekiwan);
          const nazwa = nazwaKryterium(k.nazwa);
          return (
            <li key={k.kompetencja_id}>
              <span className="nazwa-slupka">{nazwa}</span>
              <span className="tor-profilu" role="img" aria-label={`${nazwa}: średnio ${liczba(sr)} pkt u ${osobyTxt(w.length)}`}>
                <span className={`wypelnienie-profilu ${t}`} style={{ width: pozycja(sr) }} />
                <span className="linia-oczekiwan" style={{ left: pozycja(mapa.poziom_oczekiwan) }} />
              </span>
              <span className="wartosc-profilu">
                <strong className={t}>{liczba(sr)}</strong>
                <span className="meta">{osobyTxt(w.length)}</span>
              </span>
            </li>
          );
        })}
        <li className="skala-profilu" aria-hidden="true">
          <span />
          <span className="podzialka-profilu">
            {mapa.skala.map((v) => (
              <span key={v} style={{ left: pozycja(v) }}>
                {v}
              </span>
            ))}
          </span>
          <span />
        </li>
      </ul>
    </figure>
  );
}

export function MapaKompetencji({
  mapa,
  ludzie,
  onWybierz,
  czesc,
}: {
  mapa: Mapa;
  /** Osoby w wybranej komórce (zakres Zespołu); mapa pokazuje tylko je. */
  ludzie: Pracownik[];
  onWybierz?: (p: Pracownik) => void;
  /** Pulpit (zgłoszenie 110): „wnioski” = do rozwoju i mocna strona w prawej kolumnie, „szczegoly” = średnie i tabela pod spodem;
   *  bez = całość (Zespół). */
  czesc?: "wnioski" | "szczegoly";
}) {
  const poId = new Map(ludzie.map((p) => [p.osoba_id, p]));
  const osoby = mapa.osoby.filter((o) => poId.has(o.osoba_id));
  const bez = ludzie.length - osoby.length;
  const kryteria = mapa.kryteria.filter((k) => osoby.some((o) => o.punkty[k.kompetencja_id] !== undefined));
  const { slabe, mocne } = wnioski({ ...mapa, kryteria }, osoby);
  const pokazRozbieznosci = osoby.some((o) => o.rozbieznosci !== null);

  return (
    <section className={`mapa-kompetencji${czesc ? ` mapa-${czesc}` : ""}`}>
      <h2>{czesc === "szczegoly" ? "Kompetencje zespołu: kryteria i osoby" : "Kompetencje zespołu"}</h2>
      {osoby.length === 0 ? (
        <p className="meta zero">Nikt w tej komórce nie ma jeszcze oceny z punktami za kryteria.</p>
      ) : (
        <>
          {czesc !== "szczegoly" && (
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
          )}
          {czesc !== "wnioski" && <ProfilKompetencji mapa={mapa} osoby={osoby} kryteria={kryteria} />}
          {czesc !== "wnioski" && (
          <>
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
        </>
      )}
    </section>
  );
}

/** Karta pracownika: oceny cząstkowe ostatniej oceny z akt (bieżącą pokazuje sekcja ocen kryteriów). */
/** `bezNaglowka`: same słupki pod linią poprzedniej oceny na karcie (#55). */
export function OcenyCzastkowe({ mapa, osoba, bezNaglowka }: { mapa: Mapa | null; osoba: Pracownik; bezNaglowka?: boolean }) {
  const o = mapa?.osoby.find((x) => x.osoba_id === osoba.osoba_id && x.zrodlo === "ostatnia_ocena");
  if (!mapa || !o) return null;
  const max = Math.max(...mapa.skala);
  const slupki = (
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
  );
  if (bezNaglowka) return slupki;
  return (
    <div className="sekcja">
      <h2>Ostatnia ocena: kryteria</h2>
      <p className="meta zero">
        Oceny cząstkowe z oceny okresowej {o.data ? `z ${data(o.data)}` : ""} (akta), skala 1–{max} pkt
      </p>
      {slupki}
    </div>
  );
}
