import { useEffect, useState } from "react";
import { pobierzBraki, type PanelBrakow, type Zrodla } from "./api";

const ETYKIETA: Record<string, string> = { BRAK: "brak", "ROZBIEŻNOŚĆ": "rozbieżność", DUPLIKAT: "duplikat" };

export default function PanelZrodel({ zrodla, token }: { zrodla: Zrodla | null; token: string }) {
  const [panel, setPanel] = useState<PanelBrakow | null>(null);
  const [blad, setBlad] = useState<string | null>(null);

  useEffect(() => {
    pobierzBraki(token).then(setPanel).catch((e) => setBlad(String(e)));
  }, [token]);

  return (
    <>
      {blad && <p className="blad">{blad}</p>}

      {panel && (
        <section>
          <h2>Braki i rozbieżności w materiałach MC</h2>
          <p className="opis">Każdy wpis wskazuje plik z „materialy mc”. Cytaty są sprawdzane w korpusie.</p>
          {panel.braki.map((b) => (
            <article key={b.id} className="brak-wpis">
              <div className="zrodlo">
                <span className={`kategoria typ-${b.typ === "ROZBIEŻNOŚĆ" ? "rozbieznosc" : b.typ.toLowerCase()}`}>
                  {ETYKIETA[b.typ]}
                </span>
                <strong>{b.tytul}</strong>
              </div>
              <p>{b.opis}</p>
              {b.wplyw && <p className="opis">Wpływ: {b.wplyw}</p>}
              <p className="opis">Pliki: {b.pliki.join(" · ")}</p>
              {b.adnotacje.map((a, i) => (
                <div key={i} className="adnotacja">
                  <div className="zrodlo">
                    <span className={`kategoria ${a.adnotacja.kategoria === "PRZEPIS" ? "przepis" : ""}`}>
                      {a.adnotacja.kategoria}
                    </span>
                    {a.dokument}
                    {a.adnotacja.lokalizator && <> · {a.adnotacja.lokalizator}</>}
                    {a.cytat_w_korpusie === true && <span className="ok">cytat w korpusie</span>}
                    {a.cytat_w_korpusie === false && <span className="blad">brak pokrycia</span>}
                    {b.rozbieznosc?.zastosowana === i && <span className="ok">zastosowana</span>}
                  </div>
                  {a.adnotacja["cytat_dosłowny"] && <blockquote>{a.adnotacja["cytat_dosłowny"]}</blockquote>}
                  {a.adnotacja.uzasadnienie && <p className="opis">{a.adnotacja.uzasadnienie}</p>}
                </div>
              ))}
              {b.rozbieznosc && (
                <p className="opis">
                  ROZBIEŻNOŚĆ: {b.rozbieznosc.opis}
                  {b.rozbieznosc.uzasadnienie && <> Zastosowano: {b.rozbieznosc.uzasadnienie}</>}
                </p>
              )}
            </article>
          ))}
        </section>
      )}

      {panel && (
        <section>
          <h2>Pytania do mentorów MC</h2>
          <ol>
            {panel.pytania_do_mentorow.map((p) => (
              <li key={p.id}>{p.pytanie}</li>
            ))}
          </ol>
        </section>
      )}

      {zrodla && (
        <section>
          <h2>Inwentarz źródeł</h2>
          <table>
            <thead>
              <tr><th>Dokument</th><th>Ścieżka</th><th>Kategoria</th><th>Fragmenty</th><th>Asystent</th><th>Status</th></tr>
            </thead>
            <tbody>
              {zrodla.dokumenty.map((d) => (
                <tr key={d.doc_id}>
                  <td>{d.nazwa}</td><td>{d.sciezka}</td><td>{d.kategoria}</td><td>{d.fragmenty}</td>
                  <td>{d.w_asystencie ? "tak" : "nie"}</td><td>{d.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {zrodla.duplikaty.map((d) => (
            <p key={d.plik} className="opis">
              Duplikat: {d.plik} → fragment {d.duplikat_z} (pokrycie {Math.round(d.pokrycie * 100)}%)
            </p>
          ))}
          {zrodla.pominiete.map((p) => (
            <p key={p.plik} className="opis">Pominięty: {p.plik} – {p.powod}</p>
          ))}
        </section>
      )}
    </>
  );
}
