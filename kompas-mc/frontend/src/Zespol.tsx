import { useEffect, useState } from "react";
import { pobierzKrok1, pobierzPracownikow, pobierzProcesy, pobierzTerminy, type Pracownik } from "./api";
import type { Sesja } from "./Konto";
import { Inicjaly, SzkieletListy, WierszListy } from "./Lista";
import { Kafel, PasekUdzialow } from "./Wykresy";
import { lat, lataStazu, stazTekst, NAZWA_SCIEZKI, nastepnyKrok, osoby, wedlugKomorek, type Sprawa } from "./zespol-dane";
import "./widoki.css";

/**
 * Sprawy osób w zakresie użytkownika: przełożony podwładnych, HR wszystkich, oceniany siebie.
 * Proces w toku i termin z API; dla osób bez procesu ścieżka proponowana z analizy kroku 1.
 */
export function useSprawy(sesja: Sesja, onWyloguj: () => void) {
  const [sprawy, setSprawy] = useState<Sprawa[] | null>(null);
  const [blad, setBlad] = useState<string | null>(null);

  useEffect(() => {
    let aktualne = true;
    (async () => {
      try {
        const [ludzie, procesy, terminy] = await Promise.all([
          pobierzPracownikow(sesja.token),
          pobierzProcesy(sesja.token),
          // Brak terminów nie blokuje widoku; kafel powie wtedy, że terminu nie ma.
          pobierzTerminy(sesja.token).catch(() => []),
        ]);
        const wynik = await Promise.all(
          ludzie.map(async (osoba): Promise<Sprawa> => {
            const proces = procesy.find((p) => p.osoba_id === osoba.osoba_id && p.status === "W_TOKU") ?? null;
            const termin = (proces && terminy.find((t) => t.proces_id === proces.id)) || null;
            if (proces) return { osoba, proces, proponowana: proces.sciezka, termin };
            const analiza = await pobierzKrok1(sesja.token, osoba.osoba_id).catch(() => null);
            return { osoba, proces: null, proponowana: analiza?.sciezka.proponowana ?? null, termin: null };
          }),
        );
        // Najpierw oceny w toku (najbliższy termin pierwszy), potem osoby do rozpoczęcia.
        wynik.sort(
          (a, b) =>
            Number(!!b.proces) - Number(!!a.proces) ||
            (a.termin?.dni_do_terminu ?? 9999) - (b.termin?.dni_do_terminu ?? 9999),
        );
        if (aktualne) setSprawy(wynik);
      } catch (err) {
        if (String(err).includes("401")) onWyloguj();
        else if (aktualne) setBlad("Nie udało się pobrać danych zespołu.");
      }
    })();
    return () => {
      aktualne = false;
    };
  }, [sesja.token, onWyloguj]);

  return { sprawy, blad };
}

const PROGI_STAZU: [string, number, number][] = [
  ["do 2 lat", 0, 2],
  ["2–5 lat", 2, 5],
  ["5–10 lat", 5, 10],
  ["ponad 10 lat", 10, 999],
];

export function Zespol({
  sesja,
  onWybierz,
  onWyloguj,
}: {
  sesja: Sesja;
  onWybierz: (p: Pracownik) => void;
  onWyloguj: () => void;
}) {
  const { sprawy, blad } = useSprawy(sesja, onWyloguj);
  const hr = sesja.uzytkownik.rola === "hr";

  if (blad) return <p className="blad">{blad}</p>;
  if (!sprawy)
    return (
      <div className="widok">
        <h1>{hr ? "Urząd" : "Mój zespół"}</h1>
        <SzkieletListy wiersze={4} />
      </div>
    );

  const ludzie = sprawy.map((s) => s.osoba);
  const grupy = wedlugKomorek(sprawy, (s) => s.osoba.komorka);
  const wydzialow = grupy.reduce((a, g) => a + g.wydzialy.length, 0);
  const wToku = sprawy.filter((s) => s.proces).length;
  const doRozpoczecia = sprawy.filter((s) => !s.proces && s.proponowana).length;
  const ost = (w: "pozytywna" | "negatywna") => ludzie.filter((p) => p.ostatnia_ocena_okresowa?.wynik === w).length;
  const bezOceny = ludzie.filter((p) => !p.ostatnia_ocena_okresowa).length;
  const staze = ludzie.map((p) => lataStazu(p.data_zatrudnienia));
  const sredniStaz = staze.length ? Math.round(staze.reduce((a, b) => a + b, 0) / staze.length) : 0;

  return (
    <div className="widok">
      <div className="naglowek-widoku">
        <h1>{hr ? "Urząd" : "Mój zespół"}</h1>
        <p className="meta">
          {osoby(ludzie.length)} · {grupy.length} {grupy.length === 1 ? "departament" : "departamenty"} · {wydzialow}{" "}
          {wydzialow === 1 ? "wydział" : "wydziały"} · dane kadrowe z QNT
        </p>
      </div>

      <div className="kafle">
        <Kafel etykieta="Oceny w toku" wartosc={wToku} opis={`z ${osoby(ludzie.length)} w zespole`} />
        <Kafel etykieta="Do rozpoczęcia" wartosc={doRozpoczecia} opis="ścieżka z analizy opisu stanowiska" />
        <Kafel etykieta="Średni staż" wartosc={lat(sredniStaz)} opis="od daty zatrudnienia w QNT" />
      </div>

      <div className="wykresy">
        <PasekUdzialow
          tytul="Ostatnia ocena okresowa"
          podstawa="z kartoteki QNT"
          udzialy={[
            { nazwa: "pozytywna", liczba: ost("pozytywna"), ton: "dobrze" },
            { nazwa: "negatywna", liczba: ost("negatywna"), ton: "zle" },
            { nazwa: "jeszcze bez oceny", liczba: bezOceny, ton: "pusty" },
          ]}
        />
        <PasekUdzialow
          tytul="Stan ocen"
          podstawa="procesy w aplikacji i analiza kroku 1"
          udzialy={[
            { nazwa: "w toku", liczba: wToku, ton: "info" },
            { nazwa: "do rozpoczęcia", liczba: doRozpoczecia, ton: "uwaga" },
            { nazwa: "bez ścieżki", liczba: sprawy.length - wToku - doRozpoczecia, ton: "pusty" },
          ]}
        />
        <PasekUdzialow
          tytul="Staż pracy"
          podstawa="od daty zatrudnienia"
          udzialy={PROGI_STAZU.map(([nazwa, od, do_], i) => ({
            nazwa,
            liczba: staze.filter((s) => s >= od && s < do_).length,
            ton: "info" as const,
          }))}
        />
      </div>

      {grupy.map((g) => (
        <section key={g.departament} className="departament">
          <h2>{g.departament}</h2>
          {g.wydzialy.map((w) => (
            <div key={w.wydzial} className="sekcja">
              <div className="wiersz-tytulu">
                <span className="kafel-etykieta">{w.wydzial}</span>
                <span className="meta">{osoby(w.ludzie.length)}</span>
              </div>
              <div className="lista">
                {w.ludzie.map((s) => (
                  <WierszListy
                    key={s.osoba.osoba_id}
                    lewa={<Inicjaly imie={s.osoba.imie} nazwisko={s.osoba.nazwisko} />}
                    tytul={`${s.osoba.imie} ${s.osoba.nazwisko}`}
                    znacznik={
                      s.osoba.ostatnia_ocena_okresowa && (
                        <span className={`status ${s.osoba.ostatnia_ocena_okresowa.wynik}`}>
                          ostatnio {s.osoba.ostatnia_ocena_okresowa.wynik}
                        </span>
                      )
                    }
                    opis={`${s.osoba.stanowisko} · ${nastepnyKrok(s)}`}
                    prawa={
                      <>
                        {stazTekst(lataStazu(s.osoba.data_zatrudnienia))}
                        <br />
                        {s.proponowana ? NAZWA_SCIEZKI[s.proponowana] : "ścieżka do ustalenia"}
                      </>
                    }
                    onClick={() => onWybierz(s.osoba)}
                  />
                ))}
              </div>
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}
