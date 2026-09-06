/* Vindex V2 — podnesak sudu (D5), domen.
 *
 * Katalozi (tipovi podnesaka, sudovi) dolaze sa servera i ovde se samo cisti
 * oblik. Spisak prepisan u frontend zastari tiho: nudio bi tip koji server
 * odbija, i to bi se videlo tek posle skupog poziva.
 *
 * MINIMUM OPISA JE 20 ZNAKOVA, jer to trazi `PodnesakReq.opis`. Provera je
 * ovde da bi advokat dobio recenicu koja kaze sta da uradi, umesto 422 sa
 * servera posle cekanja.
 */

/** `PodnesakReq.opis` ima `min_length=20`. Broj se ne pogadja — prepisan je. */
export const MIN_OPIS_PODNESAK = 20;
export const MAX_OPIS_PODNESAK = 5000;

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

export function uTipovePodneska(sirov) {
  const niz = sirov && Array.isArray(sirov.tipovi) ? sirov.tipovi : [];
  return niz
    .map(t => ({ tip: tekst(t && t.tip), naziv: tekst(t && t.naziv) }))
    .filter(t => t.tip && t.naziv);
}

/**
 * `/api/courts` vraca `{ sudovi: { "Osnovni sudovi": [...], ... } }` —
 * grupisano po vrsti suda. Grupe se cuvaju: „Osnovni sud u Beogradu" i
 * „Apelacioni sud u Beogradu" nisu zamenljivi, a spljosten spisak bi ih
 * prikazao kao ravnopravne stavke iste vrste.
 */
export function uSudove(sirov) {
  const s = sirov && sirov.sudovi;
  if (!s || typeof s !== "object") return [];
  const ulazi = Array.isArray(s) ? [["Sudovi", s]] : Object.entries(s);
  return ulazi
    .map(([grupa, lista]) => ({
      grupa: tekst(grupa),
      sudovi: (Array.isArray(lista) ? lista : [])
        .map(x => ({
          naziv: tekst(x && x.naziv),
          adresa: tekst(x && x.adresa),
          grad: tekst(x && x.grad),
        }))
        .filter(x => x.naziv),
    }))
    .filter(g => g.grupa && g.sudovi.length);
}

/** Vraca sta nedostaje, na jeziku advokata. */
export function nedostaciPodneska({ tip, opis } = {}) {
  const g = [];
  if (!tekst(tip)) g.push("Izaberite vrstu podneska.");
  const o = tekst(opis);
  if (!o) {
    g.push("Opišite slučaj.");
  } else if (o.length < MIN_OPIS_PODNESAK) {
    g.push(`Opis mora imati najmanje ${MIN_OPIS_PODNESAK} znakova; uneto je ${o.length}.`);
  } else if (o.length > MAX_OPIS_PODNESAK) {
    g.push(`Opis sme imati najviše ${MAX_OPIS_PODNESAK} znakova; uneto je ${o.length}.`);
  }
  return g;
}
