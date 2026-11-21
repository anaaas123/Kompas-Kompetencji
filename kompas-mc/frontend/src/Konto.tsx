import { FormEvent, useEffect, useState } from "react";
import { pobierzJa, pobierzPracownikow, zaloguj, type Pracownik, type Rola, type Uzytkownik } from "./api";
import { Inicjaly, SzkieletListy, WierszListy } from "./Lista";
import { Wydra } from "./wydra/Wydra";

export interface Sesja {
  token: string;
  uzytkownik: Uzytkownik;
}

const KONTA_DEMO = ["przelozony1", "przelozony2", "hr", "oceniany"];
const TYTUL_LISTY: Record<Rola, string> = { przelozony: "Twoi podwładni", hr: "Pracownicy", oceniany: "Twoje dane" };

const data = (iso: string) => iso.split("-").reverse().join(".");
// Komórka z QNT ma postać „Departament … / Wydział …”: na liście wystarcza wydział.
const komorka = (pelna: string) => pelna.split(" / ").pop() ?? pelna;

export function Logowanie({ onZalogowano }: { onZalogowano: (s: Sesja) => void }) {
  const [login, setLogin] = useState("");
  const [haslo, setHaslo] = useState("");
  const [blad, setBlad] = useState<string | null>(null);
  const [czekam, setCzekam] = useState(false);

  async function wyslij(e: FormEvent) {
    e.preventDefault();
    setCzekam(true);
    setBlad(null);
    try {
      const { token } = await zaloguj(login, haslo);
      onZalogowano({ token, uzytkownik: await pobierzJa(token) });
    } catch (err) {
      setBlad(String(err).includes("401") ? "Nieprawidłowy login lub hasło." : "Brak połączenia z API (port 8002).");
    } finally {
      setCzekam(false);
    }
  }

  return (
    <div className="logowanie-karta">
      <Wydra poza="stoi" szerokosc={120} naStart="machanie" />
      <h1>Kompas Kompetencji</h1>
      <p className="opis">
        Konta demo:{" "}
        {KONTA_DEMO.map((k, i) => (
          <span key={k}>
            {i > 0 && ", "}
            <button type="button" className="link" onClick={() => { setLogin(k); setHaslo("demo"); }}>
              {k}
            </button>
          </span>
        ))}
        ; hasło <code>demo</code>.
      </p>
      <form onSubmit={wyslij} className="logowanie-formularz">
        <input
          aria-label="Login"
          placeholder="Login…"
          autoComplete="username"
          value={login}
          onChange={(e) => setLogin(e.target.value)}
        />
        <input
          aria-label="Hasło"
          type="password"
          placeholder="Hasło…"
          autoComplete="current-password"
          value={haslo}
          onChange={(e) => setHaslo(e.target.value)}
        />
        <button disabled={czekam || !login || !haslo}>{czekam ? "Loguję…" : "Zaloguj"}</button>
      </form>
      {blad && <p className="blad">{blad}</p>}
    </div>
  );
}

export function Pracownicy({
  sesja,
  onWyloguj,
  onWybierz,
}: {
  sesja: Sesja;
  onWyloguj: () => void;
  onWybierz?: (p: Pracownik) => void;
}) {
  const [lista, setLista] = useState<Pracownik[] | null>(null);
  const [blad, setBlad] = useState<string | null>(null);
  const uz = sesja.uzytkownik;

  useEffect(() => {
    pobierzPracownikow(sesja.token)
      .then(setLista)
      .catch((err) => (String(err).includes("401") ? onWyloguj() : setBlad("Nie udało się pobrać pracowników.")));
  }, [sesja.token, onWyloguj]);

  return (
    <div className="sekcja">
      <h1>{TYTUL_LISTY[uz.rola]}</h1>
      {blad && <p className="blad">{blad}</p>}
      {!blad && lista === null && <SzkieletListy />}
      {lista?.length === 0 && <p className="brak">Brak osób w Twoim zakresie.</p>}
      {lista && lista.length > 0 && (
        <div className="lista">
          {lista.map((p) => (
            <WierszListy
              key={p.osoba_id}
              lewa={<Inicjaly imie={p.imie} nazwisko={p.nazwisko} />}
              tytul={`${p.imie} ${p.nazwisko}`}
              znacznik={
                p.ostatnia_ocena_okresowa && (
                  <span className={`status ${p.ostatnia_ocena_okresowa.wynik}`}>
                    ocena {p.ostatnia_ocena_okresowa.wynik} {data(p.ostatnia_ocena_okresowa.data)}
                  </span>
                )
              }
              opis={`${p.stanowisko} · ${komorka(p.komorka)}`}
              prawa={
                <>
                  od {data(p.data_zatrudnienia)}
                  <br />
                  czas {p.rodzaj_umowy === "nieokreslony" ? "nieokreślony" : "określony"}
                </>
              }
              onClick={onWybierz ? () => onWybierz(p) : undefined}
            />
          ))}
        </div>
      )}
    </div>
  );
}
