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
  if (status === 413) return VRSTA.PREVELIKO;
  if (status === 415) return VRSTA.VRSTA_FAJLA;
  if (status === 400 || status === 422) return VRSTA.NEISPRAVAN;
  if (status >= 500) return VRSTA.SERVER;
  return VRSTA.NEISPRAVAN;
}

function saUpitom(putanja, upit) {
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
  return url;
}

/**
 * @param {string} putanja   npr. "/api/predmeti"
 * @param {object} opcije    { upit?: Record<string,string|number>, signal?: AbortSignal }
 */
export async function dohvati(putanja, opcije = {}) {
  const { upit, signal } = opcije;

  const url = saUpitom(putanja, upit);

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


/**
 * Pisanje. Odvojena funkcija od `dohvati` NAMERNO: citanje se sme ponoviti
 * bez posledice, pisanje ne sme. Deljena funkcija sa `metod` parametrom bi tu
 * razliku ucinila nevidljivom na pozivnom mestu.
 *
 * `telo` je obican objekat (salje se kao JSON) ili `FormData` (salje se kao
 * takav, BEZ rucnog Content-Type zaglavlja — granicu mora da postavi
 * pretrazivac, inace multipart telo nije citljivo serveru).
 *
 * Kao i kod citanja, telo greske se NE prosledjuje dalje: moze nositi nazive
 * tabela i kolona. Ekran dobija vrstu greske, ne sirov backend tekst.
 */
export async function posalji(putanja, opcije = {}) {
  const { metod = "POST", telo, upit, signal } = opcije;

  const url = saUpitom(putanja, upit);
  const zaglavlja = { Accept: "application/json" };
  const t = token();
  if (t) zaglavlja.Authorization = "Bearer " + t;

  let sadrzaj;
  if (telo instanceof FormData) {
    sadrzaj = telo;
  } else if (telo !== undefined && telo !== null) {
    zaglavlja["Content-Type"] = "application/json";
    sadrzaj = JSON.stringify(telo);
  }

  let odgovor;
  try {
    odgovor = await fetch(url, {
      method: metod, headers: zaglavlja, body: sadrzaj, signal,
      credentials: "same-origin",
    });
  } catch (e) {
    if (e && e.name === "AbortError") throw new HttpGreska(VRSTA.PREKINUT, 0, "Zahtev otkazan.");
    // KOD PISANJA MREZNI KVAR NIJE DOKAZ DA SE NISTA NIJE UPISALO: zahtev je
    // mogao stici do servera i proci, a odgovor se izgubiti. Zato poruka nikad
    // ne tvrdi da izmena nije sacuvana — samo da ishod nije poznat.
    throw new HttpGreska(VRSTA.MREZA, 0, "Veza je prekinuta pre nego što je stigao odgovor.");
  }

  if (!odgovor.ok) {
    throw new HttpGreska(vrstaZaStatus(odgovor.status), odgovor.status, `HTTP ${odgovor.status}`);
  }
  if (odgovor.status === 204) return null;
  try {
    return await odgovor.json();
  } catch (e) {
    // Pisanje je USPELO (2xx); samo telo nije JSON. Ne pretvarati to u gresku.
    return null;
  }
}
