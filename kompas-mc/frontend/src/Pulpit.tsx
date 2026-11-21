import { FormEvent, useMemo, useState } from "react";
import type { Pracownik } from "./api";
import { Ikona } from "./Ikona";
import type { Sesja } from "./Konto";
import { Inicjaly, SzkieletListy, WierszListy } from "./Lista";
import { Kafel } from "./Wykresy";
import { useSprawy } from "./Zespol";
import { data, kiedy, NAZWA_SCIEZKI, nastepnyKrok, osoby, wedlugKomorek } from "./zespol-dane";
import "./widoki.css";

/**
 * Pulpit (strona główna) w stylu mObywatela, jedna wyśrodkowana kolumna: liczby na dziś (z podstawą),
 * „Do zrobienia”, zespół według wydziałów, pytania o zasady, a na samym dole jedno pole
 * „znajdź pracownika albo zapytaj”, które przy jednej pasującej osobie otwiera ją, a inaczej pyta asystenta.
 */
const ZASADY = [
  "Co omawia się na rozmowie oceniającej?",
  "Kiedy ocena okresowa jest negatywna?",
  "Ile dni ma pracownik na sprzeciw od oceny okresowej?",
];

export function Pulpit({
  sesja,
  onWybierz,
  onZapytaj,
  onWyloguj,
  onZespol,
}: {
  sesja: Sesja;
  onWybierz: (p: Pracownik) => void;
  onZapytaj: (pytanie: string) => void;
  onWyloguj: () => void;
  onZespol: () => void;
}) {
  const { sprawy, blad } = useSprawy(sesja, onWyloguj);
  const [szukaj, setSzukaj] = useState("");
  const rola = sesja.uzytkownik.rola;
  const zespol = rola !== "oceniany";

  const widoczne = useMemo(() => {
    const q = szukaj.trim().toLowerCase();
    if (!sprawy || !q) return sprawy;
    return sprawy.filter((s) => `${s.osoba.imie} ${s.osoba.nazwisko}`.toLowerCase().includes(q));
  }, [sprawy, szukaj]);

  function wyslij(e: FormEvent) {
    e.preventDefault();
    const q = szukaj.trim();
    if (!q) return;
    // Jedna osoba pasuje do wpisu: otwórz ją; inaczej to pytanie do asystenta.
    if (widoczne && widoczne.length === 1) onWybierz(widoczne[0].osoba);
    else onZapytaj(q);
    setSzukaj("");
  }

  const wToku = sprawy?.filter((s) => s.proces) ?? [];
  const doRozpoczecia = sprawy?.filter((s) => !s.proces && s.proponowana) ?? [];
  const najblizszy = wToku
    .map((s) => s.termin)
    .filter((t) => t?.najblizszy_termin && t.dni_do_terminu !== null)
    .sort((a, b) => a!.dni_do_terminu! - b!.dni_do_terminu!)[0];
  const grupy = sprawy ? wedlugKomorek(sprawy, (s) => s.osoba.komorka) : [];

  return (
    <div className="pulpit-srodek">
      <h1>Na dziś</h1>

      {zespol && sprawy && (
        <div className="kafle">
          <Kafel
            etykieta="Oceny w toku"
            wartosc={wToku.length}
            ton={najblizszy?.zagrozony ? "uwaga" : undefined}
            opis={
              najblizszy?.najblizszy_termin ? (
                <>
                  Najbliższy termin: {najblizszy.najblizszy_termin.nazwa}, {data(najblizszy.najblizszy_termin.data)} (
                  {kiedy(najblizszy.dni_do_terminu!)}) · {najblizszy.osoba}
                </>
              ) : wToku.length ? (
                "Bez terminu w regułach ścieżki"
              ) : (
                "Żadna ocena nie jest rozpoczęta"
              )
            }
          />
          <Kafel
            etykieta="Do rozpoczęcia"
            wartosc={doRozpoczecia.length}
            opis={`Z ${osoby(sprawy.length)} w zespole; ścieżka z analizy opisu stanowiska`}
          />
        </div>
      )}

      <div className="sekcja">
        <h2>{rola === "przelozony" ? "Do zrobienia" : rola === "hr" ? "Oceny w urzędzie" : "Twoja ocena"}</h2>
        {blad && <p className="blad">{blad}</p>}
        {!blad && widoczne === null && <SzkieletListy />}
        {widoczne?.length === 0 && (
          <p className="meta">{szukaj ? "Nikt nie pasuje do wpisu. Enter wyśle go jako pytanie do asystenta." : "Brak osób w Twoim zakresie."}</p>
        )}
        {widoczne && widoczne.length > 0 && (
          <div className="lista">
            {widoczne.map((s) => (
              <WierszListy
                key={s.osoba.osoba_id}
                lewa={<Inicjaly imie={s.osoba.imie} nazwisko={s.osoba.nazwisko} />}
                tytul={`${s.osoba.imie} ${s.osoba.nazwisko}`}
                znacznik={
                  s.proponowana && (
                    <span className={`status ${s.proces ? "uwaga" : "neutralna"}`}>{NAZWA_SCIEZKI[s.proponowana]}</span>
                  )
                }
                opis={`${nastepnyKrok(s)} · ${s.osoba.stanowisko}`}
                prawa={
                  s.termin?.najblizszy_termin && (
                    <>
                      do {data(s.termin.najblizszy_termin.data)}
                      <br />
                      {kiedy(s.termin.dni_do_terminu!)}
                    </>
                  )
                }
                onClick={() => onWybierz(s.osoba)}
              />
            ))}
          </div>
        )}
      </div>

      {zespol && grupy.length > 0 && (
        <div className="sekcja">
          <h2>{rola === "hr" ? "Komórki" : "Mój zespół"}</h2>
          <div className="lista">
            {grupy.flatMap((g) =>
              g.wydzialy.map((w) => {
                const toku = w.ludzie.filter((s) => s.proces).length;
                return (
                  <WierszListy
                    key={`${g.departament}/${w.wydzial}`}
                    lewa={<Ikona nazwa="osoby" />}
                    tytul={w.wydzial}
                    opis={g.departament}
                    prawa={
                      <>
                        {osoby(w.ludzie.length)}
                        <br />
                        {toku ? `${toku} w toku` : "bez ocen w toku"}
                      </>
                    }
                    onClick={onZespol}
                  />
                );
              }),
            )}
          </div>
        </div>
      )}

      <div className="sekcja">
        <h2>Zasady</h2>
        <div className="lista ciasna">
          {ZASADY.map((z) => (
            <WierszListy key={z} maly lewa={<Ikona nazwa="pytanie" />} tytul={z} onClick={() => onZapytaj(z)} />
          ))}
        </div>
      </div>

      <div className="pasek-dol">
      <form className="pole-zapytania" role="search" onSubmit={wyslij}>
        <Ikona nazwa="szukaj" />
        <input
          value={szukaj}
          onChange={(e) => setSzukaj(e.target.value)}
          placeholder="Znajdź pracownika albo zapytaj o zasady oceny…"
          aria-label="Znajdź pracownika albo zapytaj o zasady oceny"
          autoComplete="off"
        />
        <button type="submit" className="wyslij" aria-label="Wyślij" disabled={!szukaj.trim()}>
          <Ikona nazwa="gora" />
        </button>
      </form>
      </div>
    </div>
  );
}
