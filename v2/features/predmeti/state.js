/* Vindex V2 — Predmeti, stanje ekrana.
 *
 * Lokalno stanje, bez globalnog store-a i bez event bus-a. Ekran je jedini
 * vlasnik svog stanja i jedini ga menja.
 *
 * ODBRANA OD ZASTARELOG ODGOVORA — dva sloja, oba potrebna:
 *   1. AbortController prekida zahtev koji vise nikoga ne zanima
 *   2. `generacija` odbacuje odgovor koji je ipak stigao posle prekida
 *
 * Samo prvi sloj nije dovoljan: `abort()` ne garantuje da promise nece biti
 * razresen u trci. Bez drugog sloja korisnik koji brzo kuca vidi rezultate
 * starijeg upita — bag koji se u testu skoro nikad ne reprodukuje, a kod
 * korisnika se vidi svaki put.
 */

export const STANJE = Object.freeze({
  UCITAVANJE: "ucitavanje",
  SPREMNO: "spremno",
  PRAZNO: "prazno",
  GRESKA: "greska",
});

export function napraviStanje(poStrani) {
  return {
    status: STANJE.UCITAVANJE,
    upit: "",
    offset: 0,
    limit: poStrani,
    strana: null,        // rezultat domain/predmeti.uStranu
    greska: null,
    generacija: 0,
    prekidac: null,      // AbortController tekuceg zahteva
  };
}

/** Otvara novu generaciju i prekida prethodni zahtev. Vraca svoj broj i signal. */
export function novaGeneracija(s) {
  if (s.prekidac) s.prekidac.abort();
  s.prekidac = new AbortController();
  s.generacija += 1;
  return { broj: s.generacija, signal: s.prekidac.signal };
}

export function jeAktuelna(s, broj) {
  return s.generacija === broj;
}
