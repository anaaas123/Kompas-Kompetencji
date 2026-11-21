import { FormEvent, useEffect, useState } from "react";
import {
  BladApi,
  pobierzKrok1,
  pobierzProcesy,
  rozpocznijProces,
  type AnalizaKroku1,
  type Brak,
  type Pole,
  type Pracownik,
  type ProcesOceny,
  type Przeslanka,
  type Sciezka,
  type SourceRef,
} from "./api";

export const NAZWA_SCIEZKI: Record<Sciezka, string> = { pierwsza: "pierwsza ocena", okresowa: "ocena okresowa" };

export function Zrodla({ adnotacje }: { adnotacje: SourceRef[] }) {
  return (
    <div className="zrodla">
      {adnotacje.map((a, i) => (
        <Zrodlo key={i} a={a} />
      ))}
    </div>
  );
}

function Zrodlo({ a }: { a: SourceRef }) {
  const [otwarte, setOtwarte] = useState(false);
  const cytat = a["cytat_dosłowny"];
  const strona = a.strona && a.lokalizator !== `s. ${a.strona}` ? `s. ${a.strona}` : null;
  const miejsce = [a.doc_id, a.lokalizator, strona].filter(Boolean).join(" · ");
  return (
    <div className="zrodlo">
      <span className={`kategoria ${a.kategoria === "PRZEPIS" ? "przepis" : ""}`}>{a.kategoria}</span>
      {miejsce}
      {cytat && (
        <button type="button" className="link" aria-expanded={otwarte} onClick={() => setOtwarte((v) => !v)}>
          {otwarte ? "ukryj cytat" : "cytat"}
        </button>
      )}
      {!cytat && a.uzasadnienie && <span>{a.uzasadnienie}</span>}
      {otwarte && cytat && <blockquote>{cytat}</blockquote>}
    </div>
  );
}

function Braki({ braki }: { braki: Brak[] }) {
  if (braki.length === 0) return null;
  return (
    <div className="brak">
      <strong>System nie zgaduje, brakuje danych:</strong>
      <ul>
        {braki.map((b) => (
          <li key={b.pole}>{b.komunikat}</li>
        ))}
      </ul>
    </div>
  );
}

const STATUS_PRZESLANKI = (s: boolean | null) =>
  s === true ? ["pozytywna", "spełniona"] : s === false ? ["neutralna", "niespełniona"] : ["uwaga", "brak danych"];

function Przeslanki({ przeslanki }: { przeslanki: Przeslanka[] }) {
  return (
    <ul className="przeslanki">
      {przeslanki.map((p) => {
        const [klasa, napis] = STATUS_PRZESLANKI(p.spelniona);
        return (
          <li key={p.id}>
            <div className="wiersz-przeslanki">
              <span className={`status ${klasa}`}>{napis}</span>
              <span>{p.opis}</span>
              <span className="meta">{NAZWA_SCIEZKI[p.sciezka]}</span>
            </div>
            {p.uwaga && <p className="meta">{p.uwaga}</p>}
            <Zrodla adnotacje={p.adnotacje} />
          </li>
        );
      })}
    </ul>
  );
}

function PoleOsp({ etykieta, pole }: { etykieta: string; pole: Pole | null }) {
  if (!pole) return null;
  return (
    <div className="pole-osp">
      <div className="etykieta">{etykieta}</div>
      <p>{pole.tekst}</p>
      <Zrodla adnotacje={[pole.adnotacja]} />
    </div>
  );
}

function OpisStanowiska({ analiza }: { analiza: AnalizaKroku1 }) {
  const osp = analiza.osp;
  if (!osp) {
    return (
      <section>
        <h2>Opis stanowiska pracy</h2>
        <p className="brak">Brak OSP tej osoby w materiałach MC. Ścieżka i arkusz wynikają z danych kadrowych (QNT).</p>
      </section>
    );
  }
  const zadania = (lista: (Pole & { nr: number })[]) => (
    <ol className="zadania">
      {lista.map((z) => (
        <li key={z.nr} value={z.nr}>
          {z.tekst}
          <Zrodla adnotacje={[z.adnotacja]} />
        </li>
      ))}
    </ol>
  );
  return (
    <section>
      <h2>Opis stanowiska pracy</h2>
      <p className="opis">
        {osp.nazwa} · {osp.komorka.join(" / ")}
      </p>
      <PoleOsp etykieta="Cel istnienia stanowiska" pole={osp.cel} />
      <div className="pole-osp">
        <div className="etykieta">Zadania dominujące</div>
        {zadania(osp.zadania_dominujace)}
      </div>
      {osp.zadania_pozostale.length > 0 && (
        <div className="pole-osp">
          <div className="etykieta">Pozostałe zadania</div>
          {zadania(osp.zadania_pozostale)}
        </div>
      )}
      <div className="pole-osp">
        <div className="etykieta">Liczba podległych pracowników</div>
        <p>{osp.podlegli.zaznaczone}</p>
        <Zrodla adnotacje={[osp.podlegli.adnotacja]} />
      </div>
      <PoleOsp etykieta="Złożoność i kreatywność" pole={osp.zlozonosc.opis} />
      <PoleOsp etykieta="Samodzielność i inicjatywa" pole={osp.samodzielnosc.opis} />
      <div className="pole-osp">
        <div className="etykieta">Kompetencje miękkie</div>
        <div className="etykiety">
          {osp.kompetencje_miekkie.lista.map((k) => (
            <span key={k} className="znacznik">
              {k}
            </span>
          ))}
        </div>
        <Zrodla adnotacje={[osp.kompetencje_miekkie.adnotacja]} />
      </div>
    </section>
  );
}

export function opisBledu(err: unknown): string {
  if (!(err instanceof BladApi)) return "Brak połączenia z API.";
  if (err.status === 409) return "Proces oceny tej osoby już trwa.";
  if (err.status === 403) return "Nie masz uprawnień do rozpoczęcia oceny tej osoby.";
  if (err.status === 422) {
    const d = err.detail;
    if (Array.isArray(d)) return d.map((b) => (typeof b === "string" ? b : (b?.komunikat ?? b?.msg ?? JSON.stringify(b)))).join(" ");
    return typeof d === "string" ? d : "Dane nie pozwalają rozpocząć oceny.";
  }
  return `Błąd API ${err.status}.`;
}

function Rozpoczecie({
  token,
  analiza,
  onRozpoczeto,
}: {
  token: string;
  analiza: AnalizaKroku1;
  onRozpoczeto: (p: ProcesOceny) => void;
}) {
  const proponowana = analiza.sciezka.proponowana;
  const [sciezka, setSciezka] = useState<Sciezka | null>(proponowana);
  const [uzasadnienie, setUzasadnienie] = useState("");
  const [czekam, setCzekam] = useState(false);
  const [blad, setBlad] = useState<string | null>(null);

  const inna = sciezka !== proponowana;
  const brakArkusza = sciezka === "okresowa" && !analiza.arkusz_okresowy.arkusz;
  const gotowe = sciezka !== null && !brakArkusza && (!inna || uzasadnienie.trim() !== "");

  async function wyslij(e: FormEvent) {
    e.preventDefault();
    if (!sciezka) return;
    setCzekam(true);
    setBlad(null);
    try {
      onRozpoczeto(
        await rozpocznijProces(token, {
          osoba_id: analiza.osoba_id,
          sciezka,
          uzasadnienie: inna ? uzasadnienie.trim() : null,
        }),
      );
    } catch (err) {
      setBlad(opisBledu(err));
    } finally {
      setCzekam(false);
    }
  }

  return (
    <section>
      <h2>Rozpoczęcie oceny</h2>
      <p className="opis">Decyzję podejmuje przełożony. Rozpoczęcie zapisuje się w dzienniku zmian.</p>
      <form onSubmit={wyslij}>
        <div className="wybor" role="group" aria-label="Ścieżka oceny">
          {(["pierwsza", "okresowa"] as Sciezka[]).map((s) => (
            <button key={s} type="button" aria-pressed={sciezka === s} onClick={() => setSciezka(s)}>
              {NAZWA_SCIEZKI[s]}
              {s === proponowana && " (propozycja)"}
            </button>
          ))}
        </div>
        {brakArkusza && (
          <p className="brak">Nie ustalono arkusza B ani C, więc oceny okresowej nie można rozpocząć. Uzupełnij dane kadrowe.</p>
        )}
        {sciezka && inna && (
          <>
            <p className="etykieta">
              {proponowana ? "Uzasadnienie wyboru innej ścieżki niż proponowana" : "Uzasadnienie wyboru ścieżki"} (wymagane)
            </p>
            <textarea
              value={uzasadnienie}
              onChange={(e) => setUzasadnienie(e.target.value)}
              rows={2}
              aria-label="Uzasadnienie wyboru ścieżki"
            />
          </>
        )}
        <div className="wiersz">
          <span className="meta">
            {sciezka === "okresowa" && analiza.arkusz_okresowy.arkusz && `Arkusz ${analiza.arkusz_okresowy.arkusz}`}
            {sciezka === "pierwsza" && "Arkusz pierwszej oceny (zał. 2 rozp. 2015)"}
          </span>
          <button disabled={czekam || !gotowe}>{czekam ? "Rozpoczynam…" : "Rozpocznij ocenę"}</button>
        </div>
      </form>
      {blad && <p className="blad">{blad}</p>}
    </section>
  );
}

export function Krok1({
  token,
  osoba,
  moznaProwadzic,
  onWroc,
  onDalej,
}: {
  token: string;
  osoba: Pracownik;
  moznaProwadzic: boolean;
  onWroc: () => void;
  onDalej: (p: ProcesOceny) => void;
}) {
  const [analiza, setAnaliza] = useState<AnalizaKroku1 | null>(null);
  const [proces, setProces] = useState<ProcesOceny | null>(null);
  const [blad, setBlad] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([pobierzKrok1(token, osoba.osoba_id), pobierzProcesy(token)])
      .then(([a, procesy]) => {
        setAnaliza(a);
        setProces(procesy.find((p) => p.osoba_id === osoba.osoba_id && p.status === "W_TOKU") ?? null);
      })
      .catch((err) =>
        setBlad(String(err).includes("403") ? "Nie masz dostępu do oceny tej osoby." : "Nie udało się pobrać analizy kroku 1."),
      );
  }, [token, osoba.osoba_id]);

  const arkusz = analiza?.arkusz_okresowy;

  return (
    <>
      <section>
        <div className="wiersz">
          <div>
            <div className="etykieta">Krok 1 z 8 · Analiza opisu stanowiska</div>
            <h2>
              {osoba.imie} {osoba.nazwisko}
            </h2>
            <p className="opis">{osoba.stanowisko}</p>
          </div>
          <button type="button" className="link" onClick={onWroc}>
            Wróć do listy
          </button>
        </div>
        {blad && <p className="blad">{blad}</p>}
        {!blad && !analiza && <p className="meta">Wczytuję analizę…</p>}
        {proces && (
          <p className="sukces">
            Proces oceny w toku: {NAZWA_SCIEZKI[proces.sciezka]}, arkusz{" "}
            {proces.arkusz === "PIERWSZA" ? "pierwszej oceny" : proces.arkusz}, krok {proces.krok}. Rozpoczął{" "}
            {proces.rozpoczal}.
          </p>
        )}
        {proces && (
          <div className="wiersz">
            <span className="meta">Następny krok: kryteria i wskaźniki</span>
            <button type="button" onClick={() => onDalej(proces)}>
              Dalej: krok 2
            </button>
          </div>
        )}
      </section>

      {analiza && (
        <>
          <section>
            <h2>Ścieżka oceny</h2>
            <p className="wartosc">
              {analiza.sciezka.proponowana ? NAZWA_SCIEZKI[analiza.sciezka.proponowana] : "nie można ustalić"}
            </p>
            <Braki braki={analiza.sciezka.braki} />
            <Przeslanki przeslanki={analiza.sciezka.przeslanki} />
          </section>

          {arkusz && (analiza.sciezka.proponowana !== "pierwsza" || arkusz.arkusz) && (
            <section>
              <h2>Arkusz oceny okresowej</h2>
              <p className="wartosc">{arkusz.arkusz ? `Arkusz ${arkusz.arkusz}` : "nie można ustalić"}</p>
              <p>{arkusz.uzasadnienie}</p>
              <p className="meta">Źródło danych: {arkusz.zrodlo}</p>
              <Braki braki={arkusz.braki} />
              <Zrodla adnotacje={arkusz.adnotacje} />
              {analiza.arkusz_a.dotyczy && <p className="brak">{analiza.arkusz_a.komunikat}</p>}
            </section>
          )}

          <OpisStanowiska analiza={analiza} />

          {!proces && moznaProwadzic && <Rozpoczecie token={token} analiza={analiza} onRozpoczeto={setProces} />}

          {analiza.uwagi.length > 0 && (
            <section>
              <h2>Uwagi i rozbieżności</h2>
              {analiza.uwagi.map((u) => (
                <div key={u.id} className="pole-osp">
                  <p>{u.komunikat}</p>
                  <Zrodla adnotacje={u.adnotacje} />
                </div>
              ))}
            </section>
          )}
        </>
      )}
    </>
  );
}
