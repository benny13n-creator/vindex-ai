/* Vindex V2 — Kancelarija, pristup podacima.
 *
 * Cetiri nezavisna izvora, `allSettled` a NIKAD `all`: nalog, klijenti,
 * naplata i tim padaju odvojeno. Sa `all` bi jedan pad ugasio ceo prostor —
 * advokat koji ne moze da vidi fakture ne sme zbog toga da izgubi i spisak
 * klijenata.
 *
 * Svaki deo nosi sopstveno stanje: `podaci` ili `pao`. Ekran zbog toga moze
 * da kaze „ovo nije ucitano" umesto da prikaze prazno i time slaze da nema
 * nicega.
 */

import { dohvati } from "../../platform/http.js";
import { jePrekid } from "../../platform/errors.js";
import { ucitajNaplatu } from "./naplata.js";

function deo(r) {
  if (r.status === "fulfilled") return { podaci: r.value, pao: false };
  return { podaci: null, pao: true, greska: r.reason };
}

export async function ucitajKancelariju({ signal } = {}) {
  const [nalog, klijenti, naplata, tim, rad] = await Promise.allSettled([
    dohvati("/api/me", { signal }),
    dohvati("/klijenti", { upit: { limit: 100, offset: 0 }, signal }),
    dohvati("/billing/pregled", { signal }),
    dohvati("/api/kancelarija/moja", { signal }),
    ucitajNaplatu({ signal }),
  ]);

  for (const r of [nalog, klijenti, naplata, tim, rad]) {
    if (r.status === "rejected" && jePrekid(r.reason)) throw r.reason;
  }

  return {
    nalog: deo(nalog),
    klijenti: deo(klijenti),
    naplata: deo(naplata),
    tim: deo(tim),
    // Tajmer, evidentiran rad i fakture. Pad ovog dela ne sme da obori
    // pregled naplate — to su dva razlicita izvora o istoj temi.
    rad: rad.status === "fulfilled" ? rad.value : null,
  };
}
