import { useEffect, useRef, useState } from "react";
import { makePlayer, STATES } from "./wydra-player.js";
import type { Player, Poza, Stan } from "./wydra-player.js";
import stoi from "./wydra-stoi.webp";
import prosi from "./wydra-prosi.webp";
import sklada from "./wydra-sklada.webp";
import powieki from "./powieki.webp";
import "./wydra.css";

export type PozaWydry = Poza;
export type RuchWydry = Stan;
type Props = {
  poza?: Poza; szerokosc?: number; naStart?: Stan; naKlik?: Stan; samoczynnie?: boolean;
} & Partial<Record<Stan, number>>;

const POZY = { stoi, prosi, sklada };
const RUCHY: Record<Poza, Stan[]> = {
  stoi: ["podskok", "machanie", "nasluchiwanie", "radosc"],
  prosi: ["proszenie"], sklada: ["skupienie", "sennosc"],
};
const losuj = (poza: Poza) => {
  const ruchy = RUCHY[poza];
  return ruchy[Math.floor(Math.random() * ruchy.length)];
};
const preferencja = () => matchMedia("(prefers-reduced-motion: reduce)");

export function Wydra(props: Props) {
  const { poza = "stoi", szerokosc = 160, naStart, naKlik, samoczynnie = true } = props;
  const pierwszy = naStart ?? RUCHY[poza][0];
  const [ruch, ustawRuch] = useState<Stan | null>(
    STATES[pierwszy].pose === poza ? pierwszy : null,
  );
  const warstwa = useRef<HTMLSpanElement>(null);
  const silnik = useRef<null | (() => Promise<Player>)>(null);
  const poprzedniaPoza = useRef(poza);
  const liczniki = useRef<Partial<Record<Stan, number>>>({});
  function rusz(stan: Stan) {
    if (STATES[stan].pose === poza && !preferencja().matches) ustawRuch(obecny => obecny ?? stan);
  }

  useEffect(() => {
    if (poprzedniaPoza.current !== poza) {
      poprzedniaPoza.current = poza;
      ustawRuch(null);
    }
  }, [poza]);
  useEffect(() => {
    for (const stan of Object.keys(STATES) as Stan[]) {
      if (props[stan] && props[stan] !== liczniki.current[stan]) rusz(stan);
      liczniki.current[stan] = props[stan];
    }
  });
  useEffect(() => {
    if (!samoczynnie) return;
    let timer: number;
    function zaplanuj() {
      timer = window.setTimeout(() => {
        if (!document.hidden) rusz(losuj(poza));
        zaplanuj();
      }, 6000 + Math.random() * 6000);
    }
    zaplanuj();
    return () => window.clearTimeout(timer);
  }, [poza, samoczynnie]);

  useEffect(() => {
    const el = warstwa.current;
    if (!el) return;
    const canvas = document.createElement("canvas");
    canvas.width = 650; canvas.height = 786; el.prepend(canvas);
    let wynik: Promise<Player> | undefined;
    let utracony = false;
    const utrata = () => { utracony = true; };
    canvas.addEventListener("webglcontextlost", utrata);
    // Twórz kontekst dopiero przy pierwszym ruchu i używaj go do końca tej pozy.
    silnik.current = () => utracony
      ? Promise.reject(new Error("WebGL context lost"))
      : (wynik ??= makePlayer(canvas, POZY[poza], poza, powieki));
    return () => {
      silnik.current = null;
      void wynik?.then(p => p.dispose(), () => {});
      canvas.removeEventListener("webglcontextlost", utrata);
      canvas.remove();
    };
  }, [poza]);

  useEffect(() => {
    const el = warstwa.current, init = silnik.current;
    if (!ruch || !el || !init || STATES[ruch].pose !== poza) return;
    const motion = preferencja(), stop = () => ustawRuch(null);
    if (motion.matches) { stop(); return; }
    const cancel = new AbortController();
    const stan = ruch, duration = STATES[ruch].ms;
    let raf = 0;
    async function odtworz() {
      try {
        const player = await init!();
        if (cancel.signal.aborted) return;
        const start = performance.now();
        el!.dataset.gra = "canvas";
        function frame(now: number) {
          if (cancel.signal.aborted) return;
          const ms = Math.max(0, now - start);
          if (ms >= duration) { stop(); return; }
          player.draw(stan, ms);
          raf = requestAnimationFrame(frame);
        }
        frame(start);
      } catch {
        // Bez WebGL wydra zostaje w pozie spoczynkowej (zapasowe klipy WebP z paczki pominięte, #75).
        if (!cancel.signal.aborted) stop();
      }
    }
    const zmiana = () => { if (motion.matches) stop(); };
    const utrata = (event: Event) => {
      event.preventDefault();
      if (!cancel.signal.aborted) stop();
    };
    const canvas = el.querySelector("canvas");
    canvas?.addEventListener("webglcontextlost", utrata);
    motion.addEventListener("change", zmiana);
    void odtworz();
    return () => {
      cancel.abort(); cancelAnimationFrame(raf);
      canvas?.removeEventListener("webglcontextlost", utrata);
      motion.removeEventListener("change", zmiana);
      delete el.dataset.gra;
    };
  }, [ruch, poza]);

  return <button type="button" className="wydra" style={{ width: szerokosc }}
    data-poza={poza} data-ruch={ruch ?? undefined} aria-label="Wydra Kompas – odtwórz gest"
    onClick={() => rusz(naKlik ?? RUCHY[poza][0])}
    onPointerEnter={e => { if (e.pointerType === "mouse") rusz(naKlik ?? losuj(poza)); }}>
    <span ref={warstwa} className="wydra__gest" aria-hidden="true" />
    <img className="wydra__spoczynek" src={POZY[poza]} width={578} height={649} alt="" draggable={false} />
  </button>;
}
