/* Vindex V2 — jedini HTTP sloj.
 *
 * Svaki poziv ka Vindex backendu prolazi ovuda. Feature moduli ne zovu `fetch`
 * i ne znaju za zaglavlja. Razlog nije elegancija nego to sto se Authorization,
 * normalizacija gresaka i otkazivanje moraju ponasati isto na svakom ekranu —
 * a to je izvodljivo samo ako postoji jedno mesto.
 *
 * Ovaj sloj NE zna za DOM i NE iscrtava nista.
 */

import { token } from "./auth.js";
import { HttpGreska, VRSTA } from "./errors.js";

function vrstaZaStatus(status) {
  if (status === 401) return VRSTA.NEPRIJAVLJEN;
  if (status === 403) return VRSTA.ZABRANJENO;
  if (status === 404) return VRSTA.NEMA;
  if (status === 400 || status === 422) return VRSTA.NEISPRAVAN;
  if (status >= 500) return VRSTA.SERVER;
  return VRSTA.NEISPRAVAN;
}

/**
 * @param {string} putanja   npr. "/api/predmeti"
 * @param {object} opcije    { upit?: Record<string,string|number>, signal?: AbortSignal }
 */
export async function dohvati(putanja, opcije = {}) {
  const { upit, signal } = opcije;

  let url = putanja;
  if (upit) {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(upit)) {
      if (v === undefined || v === null || v === "") continue;
      p.set(k, String(v));
    }
    const qs = p.toString();
    if (qs) url += (url.includes("?") ? "&" : "?") + qs;
  }

  const zaglavlja = { Accept: "application/json" };
  const t = token();
  if (t) zaglavlja.Authorization = "Bearer " + t;

  let odgovor;
  try {
    odgovor = await fetch(url, { method: "GET", headers: zaglavlja, signal, credentials: "same-origin" });
  } catch (e) {
    // Otkazivanje nije greska — pozivalac ga prepoznaje i cuti.
    if (e && e.name === "AbortError") throw new HttpGreska(VRSTA.PREKINUT, 0, "Zahtev otkazan.");
    throw new HttpGreska(VRSTA.MREZA, 0, "Zahtev nije stigao do servera.");
  }

  if (!odgovor.ok) {
    // Telo greske se NE prosledjuje dalje i NE zapisuje: moze sadrzati nazive
    // tabela i kolona. Ekran dobija vrstu, ne sirovi backend tekst.
    throw new HttpGreska(vrstaZaStatus(odgovor.status), odgovor.status, `HTTP ${odgovor.status}`);
  }

  if (odgovor.status === 204) return null;

  try {
    return await odgovor.json();
  } catch (e) {
    throw new HttpGreska(VRSTA.SERVER, odgovor.status, "Odgovor nije u očekivanom obliku.");
  }
}
