import { FormEvent, useEffect, useState } from "react";
import { pobierzJa, pobierzPracownikow, zaloguj, type Pracownik, type Rola, type Uzytkownik } from "./api";

export interface Sesja {
  token: string;
  uzytkownik: Uzytkownik;
}

const KONTA_DEMO = ["przelozony1", "przelozony2", "hr", "oceniany"];
const NAZWA_ROLI: Record<Rola, string> = { przelozony: "przełożony", hr: "HR / administrator", oceniany: "oceniany" };
const TYTUL_LISTY: Record<Rola, string> = { przelozony: "Twoi podwładni", hr: "Pracownicy", oceniany: "Twoje dane" };

const data = (iso: string) => iso.split("-").reverse().join(".");

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
    <section>
      <h2>Logowanie</h2>
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
      <form onSubmit={wyslij} className="wiersz">
        <input aria-label="Login" placeholder="login" value={login} onChange={(e) => setLogin(e.target.value)} />
        <input
          aria-label="Hasło"
          type="password"
          placeholder="hasło"
          value={haslo}
          onChange={(e) => setHaslo(e.target.value)}
        />
        <button disabled={czekam || !login || !haslo}>{czekam ? "Loguję…" : "Zaloguj"}</button>
      </form>
      {blad && <p className="blad">{blad}</p>}
    </section>
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
    <section>
      <div className="wiersz">
        <h2>{TYTUL_LISTY[uz.rola]}</h2>
        <span className="meta">
          {uz.login} · {NAZWA_ROLI[uz.rola]} ·{" "}
          <button type="button" className="link" onClick={onWyloguj}>
            Wyloguj
          </button>
        </span>
      </div>
      {blad && <p className="blad">{blad}</p>}
      {!blad && lista === null && <p className="meta">Wczytuję…</p>}
      {lista?.length === 0 && <p className="brak">Brak osób w Twoim zakresie.</p>}
      {lista && lista.length > 0 && (
        <table className="pracownicy">
          <thead>
            <tr>
              <th>Osoba</th>
              <th>Komórka</th>
              <th>Zatrudnienie</th>
              <th>Ostatnia ocena okresowa</th>
              {onWybierz && <th aria-label="Akcja" />}
            </tr>
          </thead>
          <tbody>
            {lista.map((p) => (
              <tr key={p.osoba_id}>
                <td className="osoba">
                  {p.imie} {p.nazwisko}
                  <div className="meta">{p.stanowisko}</div>
                </td>
                <td className="meta">{p.komorka}</td>
                <td>
                  od {data(p.data_zatrudnienia)}
                  <div className="meta">czas {p.rodzaj_umowy === "nieokreslony" ? "nieokreślony" : "określony"}</div>
                </td>
                <td>
                  {p.ostatnia_ocena_okresowa ? (
                    <>
                      {data(p.ostatnia_ocena_okresowa.data)}
                      <div>
                        <span className={`status ${p.ostatnia_ocena_okresowa.wynik}`}>
                          {p.ostatnia_ocena_okresowa.wynik}
                        </span>
                      </div>
                    </>
                  ) : (
                    "—"
                  )}
                </td>
                {onWybierz && (
                  <td>
                    <button type="button" className="jasny" onClick={() => onWybierz(p)}>
                      {uz.rola === "przelozony" ? "Otwórz ocenę" : "Podgląd oceny"}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
