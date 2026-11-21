import { useEffect, useState } from "react";
import { pobierzOpisOsoby, type OpisOsoby as Opis, type Pracownik } from "./api";
import type { Sesja } from "./Konto";
import "./karta.css";

/**
 * Opis osoby pod nazwiskiem (#55): 2–4 zdania z danych (kadry, opis stanowiska, etap cyklu, ostatnia ocena),
 * każde z podstawą. Domyślnie szablon bez modelu (od razu); „Opisz z pomocą modelu” woła łańcuch dostawców
 * (dane identyfikujące nie trafiają do modelu). Podpis „Sugestia asystenta – do edycji”: nic się nie zapisuje.
 */
export function OpisOsoby({ sesja, osoba }: { sesja: Sesja; osoba: Pracownik }) {
  const [opis, setOpis] = useState<Opis | null>(null);
  const [blad, setBlad] = useState(false);
  const [podstawa, setPodstawa] = useState(false);
  const [czekam, setCzekam] = useState(false);

  useEffect(() => {
    let aktualne = true;
    setOpis(null);
    pobierzOpisOsoby(sesja.token, osoba.osoba_id, false)
      .then((o) => aktualne && setOpis(o))
      .catch(() => aktualne && setBlad(true));
    return () => {
      aktualne = false;
    };
  }, [sesja.token, osoba.osoba_id]);

  async function zModelu() {
    setCzekam(true);
    try {
      setOpis(await pobierzOpisOsoby(sesja.token, osoba.osoba_id, true));
    } catch {
      setBlad(true);
    } finally {
      setCzekam(false);
    }
  }

  if (blad && !opis) return null;
  if (!opis) return <p className="opis-osoby szkielet-tekstu" aria-busy="true" />;

  const zModeluTryb = opis.tryb !== "SZABLON";
  return (
    <div className="opis-osoby" role="region" aria-label="Opis osoby">
      <p className="zdania-opisu">{opis.zdania.map((z) => z.tekst).join(" ")}</p>
      <p className="podpis-opisu">
        <span>
          {opis.oznaczenie} · {zModeluTryb ? `model ${opis.dostawca ?? ""}`.trim() : "z danych, bez modelu"}
        </span>
        <button type="button" className="link" aria-expanded={podstawa} onClick={() => setPodstawa(!podstawa)}>
          {podstawa ? "Ukryj podstawę" : "Pokaż podstawę"}
        </button>
        {!zModeluTryb && opis.odrzucone.length === 0 && (
          <button type="button" className="link" disabled={czekam} onClick={zModelu}>
            {czekam ? "Model pisze…" : "Opisz z pomocą modelu"}
          </button>
        )}
      </p>
      {!zModeluTryb && opis.odrzucone.length > 0 && (
        <p className="meta zero">Model niedostępny, pokazuję opis z danych.</p>
      )}
      {podstawa && (
        <ul className="podstawa-opisu">
          {opis.zdania.map((z, i) => (
            <li key={i}>
              <span>{z.tekst}</span>
              <span className="meta">Źródło: {[...new Set(z.fakty.map((f) => f.zrodlo))].join("; ")}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
