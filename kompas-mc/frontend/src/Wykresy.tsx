import { useLayoutEffect, useRef, useState, type ReactNode } from "react";
import type { EtapOsoby } from "./api";

/** Elementy wizualne pulpitu, zespołu i karty: kafel z liczbą, pasek udziałów, oś terminów, postęp kroków. Kolor tylko ze znaczeniem. */

export function Kafel({
  etykieta,
  wartosc,
  opis,
  ton,
  onClick,
  wybrany,
}: {
  etykieta: string;
  wartosc: ReactNode;
  /** Podstawa liczby: z czego wychodzi. */
  opis: ReactNode;
  ton?: "uwaga" | "zle";
  onClick?: () => void;
  /** Kafel działa jak filtr listy: włączony stan widać na kaflu (aria-pressed). */
  wybrany?: boolean;
}) {
  const tresc = (
    <>
      <span className="kafel-etykieta">{etykieta}</span>
      <span className={`kafel-wartosc ${ton ?? ""}`}>{wartosc}</span>
      <span className="kafel-opis">{opis}</span>
    </>
  );
  return onClick ? (
    <button type="button" className="kafel" aria-pressed={wybrany} onClick={onClick}>
      {tresc}
    </button>
  ) : (
    <div className="kafel">{tresc}</div>
  );
}

export type Ton = "dobrze" | "zle" | "uwaga" | "info" | "pusty" | EtapOsoby["etap"];

export interface Udzial {
  nazwa: string;
  liczba: number;
  /** Klasa koloru z tokenów: dobrze, zle, uwaga, info, pusty albo etap cyklu (kolory etapów w zespol.css). */
  ton: Ton;
  /** Kliknięcie odcinka albo pozycji legendy (np. przejście do listy z filtrem). */
  onClick?: () => void;
}

/** Poziomy pasek udziałów z legendą; liczby zawsze w legendzie, nie tylko w kolorze. */
export function PasekUdzialow({ tytul, udzialy, podstawa }: { tytul: string; udzialy: Udzial[]; podstawa: string }) {
  const suma = udzialy.reduce((a, u) => a + u.liczba, 0);
  return (
    <figure className="udzialy">
      <figcaption>
        <span className="kafel-etykieta">{tytul}</span>
        <span className="meta">{podstawa}</span>
      </figcaption>
      {/* Odcinki klikalne myszą i palcem (cel 44 px); klawiatura i czytnik idą przez legendę, więc odcinki są poza tabulacją. */}
      <div className="pasek-klik" role="img" aria-label={udzialy.map((u) => `${u.nazwa}: ${u.liczba}`).join(", ")}>
        {suma > 0 &&
          udzialy
            .filter((u) => u.liczba > 0)
            .map((u) =>
              u.onClick ? (
                <button key={u.nazwa} type="button" tabIndex={-1} title={`${u.nazwa}: ${u.liczba}`} style={{ flexGrow: u.liczba }} onClick={u.onClick}>
                  <span className={`odcinek ${u.ton}`} />
                </button>
              ) : (
                <span key={u.nazwa} className="bez-klik" style={{ flexGrow: u.liczba }}>
                  <span className={`odcinek ${u.ton}`} />
                </span>
              ),
            )}
      </div>
      <ul className="legenda">
        {udzialy.map((u) => (
          <li key={u.nazwa}>
            {u.onClick && u.liczba > 0 ? (
              <button type="button" className="pozycja-legendy" onClick={u.onClick}>
                <span className={`kropka ${u.ton}`} aria-hidden="true" />
                {u.nazwa} <strong>{u.liczba}</strong>
              </button>
            ) : (
              <>
                <span className={`kropka ${u.ton}`} aria-hidden="true" />
                {u.nazwa} <strong>{u.liczba}</strong>
              </>
            )}
          </li>
        ))}
      </ul>
    </figure>
  );
}

/** Postęp procesu: odcinek na każdy krok, zrobione wypełnione, bieżący w kolorze akcji. */
export function PostepKrokow({ krok, krokow, etykieta }: { krok: number; krokow: number; etykieta: string }) {
  return (
    <div className="postep" role="img" aria-label={`${etykieta}: krok ${krok} z ${krokow}`}>
      {Array.from({ length: krokow }, (_, i) => (
        <span key={i} className={i + 1 < krok ? "zrobiony" : i + 1 === krok ? "biezacy" : ""} />
      ))}
    </div>
  );
}

export interface PunktOsi {
  klucz: string;
  /** Inicjały w kółku. */
  znak: string;
  /** Imię i nazwisko: pierwsza linia dymka. */
  tytul: string;
  /** Czynność, data i etap: kolejne linie dymka (rozdzielone „ · ”) i opis dla czytnika. */
  opis: string;
  /** Dni do terminu; ujemne = po terminie. */
  dni: number;
  ton: Ton;
  onClick?: () => void;
}

const CEL = 44; // cel dotyku i odstęp punktów w pasie
const POL = CEL / 2;
const DZIEN = 86_400_000;

/**
 * Oś terminów: dziś, najbliższe `horyzont` dni i strefa „po terminie” z lewej (tylko gdy ktoś jest po terminie).
 * Punkt = osoba w dniu terminu; punkty bliżej niż 44 px idą do wyższego pasa, więc nic nie nachodzi.
 * Lista punktów w kolejności terminów jest zarazem tekstem dla czytnika (każdy punkt ma pełny opis).
 */
export function OsTerminow({ punkty, horyzont }: { punkty: PunktOsi[]; horyzont: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [szer, setSzer] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    setSzer(el.getBoundingClientRect().width);
    const ro = new ResizeObserver(([e]) => setSzer(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const widoczne = punkty.filter((p) => p.dni <= horyzont).sort((a, b) => a.dni - b.dni);
  const po = widoczne.filter((p) => p.dni < 0);
  const strefa = po.length ? Math.max(120, Math.round(szer * 0.16)) : 0;
  const x0 = strefa || POL;
  const xPrzyszly = (d: number) => x0 + (d / horyzont) * (szer - POL - x0);
  const [od, doDni] = [po[0]?.dni ?? -1, po[po.length - 1]?.dni ?? -1];
  const xMiniony = (d: number) => (od === doDni ? strefa / 2 : POL + ((d - od) / (doDni - od)) * (strefa - 2 * POL));

  // Pasy: punkt idzie do najniższego pasa, w którym poprzedni punkt jest co najmniej 44 px wcześniej.
  // ponytail: pasy rosną z gęstością; przy setkach osób w jednym miesiącu grupuj punkty dniami.
  const pasy: number[] = [];
  const ulozone = widoczne.map((p) => {
    const x = p.dni < 0 ? xMiniony(p.dni) : xPrzyszly(p.dni);
    let pas = pasy.findIndex((ostatni) => x - ostatni >= CEL);
    if (pas < 0) pas = pasy.push(x) - 1;
    else pasy[pas] = x;
    return { ...p, x, pas };
  });

  const dzis = new Date();
  dzis.setHours(0, 0, 0, 0);
  const krotko = szer < 600;
  // Kreska na początku każdego miesiąca; nazwa tylko wtedy, gdy mieści się do następnej kreski i do końca osi
  // (szerokość szacowana z liczby znaków: 8 px na znak przy piśmie 14 px).
  const miesiace: { x: number; nazwa: string }[] = [];
  for (let m = new Date(dzis.getFullYear(), dzis.getMonth() + 1, 1); (m.getTime() - dzis.getTime()) / DZIEN <= horyzont; m = new Date(m.getFullYear(), m.getMonth() + 1, 1)) {
    const nazwa = m.toLocaleDateString("pl-PL", { month: krotko ? "short" : "long" });
    miesiace.push({ x: xPrzyszly(Math.round((m.getTime() - dzis.getTime()) / DZIEN)), nazwa: m.getMonth() === 0 ? `${nazwa} ${m.getFullYear()}` : nazwa });
  }
  const zNazwa = miesiace.map((m, i) => ({ ...m, nazwa: m.x + 8 * m.nazwa.length + 8 <= (miesiace[i + 1]?.x ?? szer) ? m.nazwa : "" }));
  const wysokosc = Math.max(1, pasy.length) * CEL;

  return (
    <div ref={ref} className="os-terminow" style={{ height: wysokosc + 2 * 24 }}>
      {szer > 0 && (
        <>
          {strefa > 0 && (
            <div className="strefa-po-terminie" style={{ width: strefa }}>
              po terminie: {po.length}
            </div>
          )}
          <div className="linia-dzis" style={{ left: x0 }} aria-hidden="true">
            <span>dziś, {dzis.toLocaleDateString("pl-PL")}</span>
          </div>
          <div className="podzialka-osi" aria-hidden="true">
            {zNazwa.map((m) => (
              <span key={m.x} style={{ left: m.x }}>
                {m.nazwa}
              </span>
            ))}
          </div>
          <div aria-hidden="true">
            {ulozone.map((p) => (
              <span key={p.klucz} className="trzon" style={{ left: p.x, height: p.pas * CEL + 6 }} />
            ))}
          </div>
          <ul className="punkty-osi" aria-label="Osoby według terminu, od najwcześniejszego">
            {ulozone.map((p) => {
              const tresc = (
                <>
                  <span className={`znak-punktu ${p.ton}`} aria-hidden="true">
                    {p.znak}
                  </span>
                  <span className="dymek-osi" aria-hidden="true">
                    <strong>{p.tytul}</strong>
                    {p.opis.split(" · ").map((linia) => (
                      <span key={linia}>{linia}</span>
                    ))}
                  </span>
                </>
              );
              return (
                <li key={p.klucz} className={p.x > szer / 2 ? "do-lewej" : ""} style={{ left: p.x - POL, bottom: 24 + p.pas * CEL }}>
                  {p.onClick ? (
                    <button type="button" className="punkt-osi" aria-label={`${p.tytul}: ${p.opis}`} onClick={p.onClick}>
                      {tresc}
                    </button>
                  ) : (
                    <span className="punkt-osi" aria-label={`${p.tytul}: ${p.opis}`} role="img">
                      {tresc}
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}
