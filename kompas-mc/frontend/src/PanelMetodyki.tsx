import { useCallback, useEffect, useState } from "react";
import { pobierzMetodyke, utworzWersjeMetodyki, zatwierdzMetodyke, type WersjaMetodyki } from "./api";
import { opisBledu } from "./Krok1";
import { Wybor } from "./Ocena";
import { PoleDaty, poprawnaData } from "./Wynik";

const POZIOMY = ["1", "3", "5", "7", "9"];
const SKALA_PIERWSZEJ = [3, 5, 7];
const STATUS: Record<WersjaMetodyki["status"], { klasa: string; tekst: string }> = {
  PROJEKT: { klasa: "uwaga", tekst: "projekt" },
  ZATWIERDZONA: { klasa: "pozytywna", tekst: "zatwierdzona" },
  ZASTĄPIONA: { klasa: "neutralna", tekst: "zastąpiona" },
};

const data = (iso: string) => iso.slice(0, 10).split("-").reverse().join(".");
const mapowanie = (m: Record<string, number>) => POZIOMY.map((p) => `${p}→${m[p]}`).join(", ");

function Zatwierdzanie({ w, token, onGotowe }: { w: WersjaMetodyki; token: string; onGotowe: () => void }) {
  const [osoba, setOsoba] = useState("");
  const [dzien, setDzien] = useState<string | null>(null);
  const [blad, setBlad] = useState<string | null>(null);
  const [czekam, setCzekam] = useState(false);
  return (
    <div className="nowy-przyklad">
      <div className="siatka-dat">
        <label className="etykieta">
          Kto zatwierdza (imię, nazwisko, funkcja)
          <input value={osoba} placeholder="domyślnie login" onChange={(e) => setOsoba(e.target.value)} />
        </label>
        <PoleDaty nazwa="Dzień zatwierdzenia (domyślnie dziś)" wartosc={dzien} onZmiana={setDzien} />
      </div>
      <div className="wiersz">
        <span className="meta">Poprzednia zatwierdzona wersja zostanie zastąpiona. Oceny w toku zostają przy swojej wersji.</span>
        <button
          type="button"
          disabled={czekam || !poprawnaData(dzien)}
          onClick={async () => {
            setCzekam(true);
            setBlad(null);
            try {
              await zatwierdzMetodyke(token, w.id, { osoba: osoba.trim() || null, dzien });
              onGotowe();
            } catch (err) {
              setBlad(opisBledu(err));
            } finally {
              setCzekam(false);
            }
          }}
        >
          {czekam ? "Zatwierdzam…" : `Zatwierdź ${w.id}`}
        </button>
      </div>
      {blad && <p className="blad">{blad}</p>}
    </div>
  );
}

/** Wersje metodyki sugestii i mapowania 5→3 (#39): zmiana tworzy projekt, do ocen trafia po zatwierdzeniu. */
export default function PanelMetodyki({ token, mozeZarzadzac }: { token: string; mozeZarzadzac: boolean }) {
  const [stan, setStan] = useState<{ aktywna: string; wersje: WersjaMetodyki[] } | null>(null);
  const [zatwierdzam, setZatwierdzam] = useState<string | null>(null);
  const [udzial, setUdzial] = useState("50");
  const [mapa, setMapa] = useState<Record<string, number>>({});
  const [zmiana, setZmiana] = useState("");
  const [blad, setBlad] = useState<string | null>(null);
  const [czekam, setCzekam] = useState(false);

  const odswiez = useCallback(
    () =>
      pobierzMetodyke(token)
        .then((s) => {
          setStan(s);
          const aktywna = s.wersje.find((w) => w.id === s.aktywna);
          if (aktywna) {
            setUdzial(String(Math.round(aktywna.minimalny_udzial_ocenionych * 100)));
            setMapa(aktywna.mapowanie_pierwsza);
          }
        })
        .catch((err) => setBlad(opisBledu(err))),
    [token],
  );

  useEffect(() => {
    odswiez();
  }, [odswiez]);

  const procent = Number(udzial);
  const zlyUdzial = !Number.isInteger(procent) || procent < 1 || procent > 100;

  async function utworz() {
    setCzekam(true);
    setBlad(null);
    try {
      await utworzWersjeMetodyki(token, { minimalny_udzial_ocenionych: procent / 100, mapowanie_pierwsza: mapa, zmiana: zmiana.trim() });
      setZmiana("");
      await odswiez();
    } catch (err) {
      setBlad(opisBledu(err));
    } finally {
      setCzekam(false);
    }
  }

  return (
    <section>
      <h2>Metodyka sugestii i mapowanie skali 5→3</h2>
      <p className="meta">
        Sugestia poziomu kryterium (kroki 3–5) i przejście ze skali modelu na skalę pierwszej oceny. Zmiana tworzy nową wersję. Do ocen trafia dopiero po
        zatwierdzeniu, a ocena w toku liczy według wersji przypiętej przy pierwszym zapisie kroku 3.
      </p>
      {stan && (
        <p className="meta">
          Aktywna wersja: {stan.aktywna}
          {stan.wersje.find((w) => w.id === stan.aktywna)?.status === "PROJEKT" &&
            " (startowa, czeka na zatwierdzenie; do tego czasu sugestie są oznaczone jako decyzja projektowa)"}
        </p>
      )}
      {blad && <p className="blad">{blad}</p>}
      {stan && (
        <table>
          <thead>
            <tr>
              <th>Wersja</th>
              <th>Parametry</th>
              <th>Zmiana</th>
              <th>Zatwierdzenie</th>
            </tr>
          </thead>
          <tbody>
            {stan.wersje.map((w) => (
              <tr key={w.id}>
                <td>
                  {w.id}
                  <div>
                    <span className={`status ${STATUS[w.status].klasa}`}>
                      {w.id === stan.aktywna && w.status === "PROJEKT" ? "aktywna, do zatwierdzenia" : STATUS[w.status].tekst}
                    </span>
                  </div>
                </td>
                <td className="meta">
                  co najmniej {Math.round(w.minimalny_udzial_ocenionych * 100)}% ocenionych wskaźników
                  <div>mapowanie: {mapowanie(w.mapowanie_pierwsza)}</div>
                </td>
                <td className="meta">
                  {w.zmiana}
                  <div>
                    {w.utworzyl}, {data(w.utworzono)}
                  </div>
                </td>
                <td>
                  {w.zatwierdzil ? (
                    <>
                      {w.zatwierdzil}
                      <div className="meta">{w.data_zatwierdzenia && data(w.data_zatwierdzenia)}</div>
                    </>
                  ) : mozeZarzadzac && w.status === "PROJEKT" ? (
                    <button type="button" className="jasny" onClick={() => setZatwierdzam(zatwierdzam === w.id ? null : w.id)}>
                      Zatwierdź…
                    </button>
                  ) : (
                    <span className="meta">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {stan && zatwierdzam && (
        <Zatwierdzanie
          w={stan.wersje.find((w) => w.id === zatwierdzam)!}
          token={token}
          onGotowe={() => {
            setZatwierdzam(null);
            odswiez();
          }}
        />
      )}

      {mozeZarzadzac && stan && (
        <details className="pozostale">
          <summary>Nowa wersja (projekt)</summary>
          <fieldset className="formularz" disabled={czekam}>
            <label className="etykieta">
              Minimalny udział ocenionych wskaźników, w procentach (1–100)
              <input inputMode="numeric" value={udzial} aria-invalid={zlyUdzial} onChange={(e) => setUdzial(e.target.value.trim())} />
            </label>
            {POZIOMY.map((p) => (
              <div key={p}>
                <div className="etykieta">Poziom modelu {p} w pierwszej ocenie</div>
                <Wybor
                  etykieta={`Mapowanie poziomu ${p}`}
                  opcje={SKALA_PIERWSZEJ.map((x) => ({ wartosc: x, tekst: `${x} pkt` }))}
                  wartosc={mapa[p] ?? null}
                  zablokowane={czekam}
                  onWybierz={(x) => x !== null && setMapa((m) => ({ ...m, [p]: x }))}
                />
              </div>
            ))}
            <label className="etykieta">
              Co i dlaczego się zmienia
              <textarea rows={2} value={zmiana} onChange={(e) => setZmiana(e.target.value)} />
            </label>
            <div className="wiersz">
              <span className="meta">Projekt nie wpływa na oceny, dopóki go nie zatwierdzisz.</span>
              <button type="button" className="jasny" disabled={czekam || zlyUdzial || zmiana.trim().length < 3} onClick={utworz}>
                Utwórz projekt wersji
              </button>
            </div>
          </fieldset>
        </details>
      )}
    </section>
  );
}
