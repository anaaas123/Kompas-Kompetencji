import { useEffect, useState } from "react";
import {
  pobierzPracownikow,
  pobierzRejestr,
  pobierzRejestrCsv,
  type FiltryRejestru,
  type StronaRejestru,
  type WpisRejestru,
  type WynikOperacji,
} from "./api";
import { opisBledu } from "./Krok1";
import { Wybor } from "./Ocena";
import { PoleDaty, poprawnaData, zapiszPlik } from "./Wynik";

const CZAS = new Intl.DateTimeFormat("pl-PL", { dateStyle: "short", timeStyle: "medium", timeZone: "Europe/Warsaw" });
const WYNIK: Record<WynikOperacji, { tekst: string; klasa: string }> = {
  ok: { tekst: "wykonano", klasa: "pozytywna" },
  odmowa: { tekst: "odmowa", klasa: "uwaga" },
  blad: { tekst: "błąd", klasa: "negatywna" },
};

/** Szczegóły wpisu jednym zdaniem (tryb modelu, zadeklarowany login…), bez treści żądań. */
function szczegoly(w: WpisRejestru): string | null {
  const s = Object.entries(w.szczegoly).filter(([, v]) => v !== null && v !== "" && !(Array.isArray(v) && v.length === 0));
  return s.length ? s.map(([k, v]) => `${k.replace("_", " ")}: ${Array.isArray(v) ? v.join(", ") : String(v)}`).join(" · ") : null;
}

/** Rejestr operacji dla HR (Karol 22.11 02:11): kto, co, komu i z jakim skutkiem. Bez treści ocen i notatek. */
export default function Rejestr({ token }: { token: string }) {
  const [filtry, setFiltry] = useState<FiltryRejestru>({});
  const [strona, setStrona] = useState(1);
  const [dane, setDane] = useState<StronaRejestru | null>(null);
  const [osoby, setOsoby] = useState<Record<string, string>>({});
  const [blad, setBlad] = useState<string | null>(null);
  const [eksport, setEksport] = useState(false);
  const datyPoprawne = poprawnaData(filtry.od) && poprawnaData(filtry.do);

  useEffect(() => {
    pobierzPracownikow(token)
      .then((lista) => setOsoby(Object.fromEntries(lista.map((p) => [p.osoba_id, `${p.imie} ${p.nazwisko}`]))))
      .catch(() => setOsoby({}));
  }, [token]);

  useEffect(() => {
    if (!datyPoprawne) return;
    setBlad(null);
    pobierzRejestr(token, filtry, strona)
      .then(setDane)
      .catch((err) => setBlad(opisBledu(err)));
  }, [token, filtry, strona, datyPoprawne]);

  const ustaw = (zmiana: FiltryRejestru) => {
    setFiltry((f) => ({ ...f, ...zmiana }));
    setStrona(1);
  };

  async function pobierzCsv() {
    setEksport(true);
    try {
      zapiszPlik(await pobierzRejestrCsv(token, filtry), "rejestr-operacji.csv");
    } catch (err) {
      setBlad(opisBledu(err));
    } finally {
      setEksport(false);
    }
  }

  const od = dane && dane.razem > 0 ? (dane.strona - 1) * dane.na_stronie + 1 : 0;
  const doN = dane ? Math.min(dane.strona * dane.na_stronie, dane.razem) : 0;

  return (
    <section className="rejestr">
      <div className="rejestr-filtry">
        <PoleDaty nazwa="Od" wartosc={filtry.od ?? null} onZmiana={(v) => ustaw({ od: v })} />
        <PoleDaty nazwa="Do" wartosc={filtry.do ?? null} onZmiana={(v) => ustaw({ do: v })} />
        <label className="etykieta">
          Użytkownik
          <input value={filtry.uzytkownik ?? ""} placeholder="login" onChange={(e) => ustaw({ uzytkownik: e.target.value.trim() || null })} />
        </label>
        <Wybor
          etykieta="Wynik operacji"
          opcje={[
            { wartosc: "wszystkie", tekst: "wszystkie" },
            { wartosc: "ok", tekst: "wykonane" },
            { wartosc: "odmowa", tekst: "odmowy" },
            { wartosc: "blad", tekst: "błędy" },
          ]}
          wartosc={filtry.wynik ?? "wszystkie"}
          zablokowane={false}
          onWybierz={(w) => ustaw({ wynik: w === "wszystkie" || w === null ? null : (w as WynikOperacji) })}
        />
        <button type="button" className="jasny" disabled={eksport || !datyPoprawne} onClick={pobierzCsv}>
          {eksport ? "Przygotowuję CSV…" : "Pobierz CSV"}
        </button>
      </div>
      {!datyPoprawne && <p className="blad">Podaj datę w formacie RRRR-MM-DD, np. 2026-11-22.</p>}
      {blad && <p className="blad">{blad}</p>}
      {!dane && !blad && <p className="meta">Wczytuję rejestr…</p>}
      {dane?.razem === 0 && <p className="brak">Brak operacji dla tych filtrów.</p>}
      {dane && dane.razem > 0 && (
        <>
          <table className="pracownicy rejestr-tabela">
            <thead>
              <tr>
                <th>Czas</th>
                <th>Użytkownik</th>
                <th>Operacja</th>
                <th>Dotyczy</th>
                <th>Wynik</th>
              </tr>
            </thead>
            <tbody>
              {dane.wpisy.map((w) => (
                <tr key={w.id}>
                  <td className="liczba">{CZAS.format(new Date(w.czas))}</td>
                  <td>
                    {w.aktor_login ?? "niezalogowany"}
                    {w.aktor_rola && <div className="meta">{w.aktor_rola}</div>}
                  </td>
                  <td>
                    {w.etykieta ?? w.akcja}
                    {szczegoly(w) && <div className="meta">{szczegoly(w)}</div>}
                  </td>
                  <td>
                    {w.oceniany_osoba ? (
                      <button type="button" className="link" onClick={() => ustaw({ osoba: w.oceniany_osoba })}>
                        {osoby[w.oceniany_osoba] ?? w.oceniany_osoba}
                      </button>
                    ) : (
                      <span className="meta">—</span>
                    )}
                  </td>
                  <td>
                    <span className={`status ${WYNIK[w.wynik].klasa}`}>{WYNIK[w.wynik].tekst}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="rejestr-strony">
            <span className="meta">
              {od}–{doN} z {dane.razem}
              {filtry.osoba && (
                <>
                  {" · "}
                  <button type="button" className="link" onClick={() => ustaw({ osoba: null })}>
                    pokaż wszystkie osoby
                  </button>
                </>
              )}
            </span>
            <button type="button" className="jasny" disabled={dane.strona <= 1} onClick={() => setStrona((s) => s - 1)}>
              Nowsze
            </button>
            <button type="button" className="jasny" disabled={doN >= dane.razem} onClick={() => setStrona((s) => s + 1)}>
              Starsze
            </button>
          </div>
        </>
      )}
      <p className="meta">Wpisy są tylko dopisywane: zapisy, pobrania dokumentów, odczyty kart i ocen, odmowy dostępu i logowania. Bez treści ocen, notatek i pytań.</p>
    </section>
  );
}
