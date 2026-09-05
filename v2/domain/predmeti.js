/* Vindex V2 — domenski model predmeta.
 *
 * Preslikava sirovi red iz `view=summary` projekcije u ono sto ekran sme da
 * prikaze. Granica je namerna: `id` prelazi jer ga ruter i backend trebaju,
 * ali NIJE deo vidljivog modela — u pogledu ne postoji polje koje bi ga
 * iscrtalo (Z015 §19, §41).
 *
 * Cist modul: bez DOM-a, bez mreze, bez stanja.
 */

import { nazivStanja, klasaStanja, nazivVrste, datum } from "./labels.js";

/** Zapis koji nedostaje ili nema naziv ne sme oboriti ceo registar. */
export function uZapis(sirov) {
  const r = sirov || {};
  return {
    id: r.id || "",                                  // interno; nikad se ne iscrtava
    naziv: (r.naziv || "").trim() || "Predmet bez naziva",
    broj: (r.broj_predmeta || "").trim(),
    vrsta: nazivVrste(r.tip),
    stanje: nazivStanja(r.status),
    stanjeKlasa: klasaStanja(r.status),
    izmenjeno: datum(r.updated_at || r.created_at),
  };
}

export function uZapise(niz) {
  return Array.isArray(niz) ? niz.map(uZapis) : [];
}

/**
 * Odgovor `/api/predmeti`. `ukupno` je jedini izvor broja rezultata —
 * duzina strane NIJE broj rezultata i ne sme se tako koristiti.
 */
export function uStranu(odgovor, trazenLimit, trazenOffset) {
  const o = odgovor || {};
  const limit = Number.isFinite(o.limit) ? o.limit : trazenLimit;
  const offset = Number.isFinite(o.offset) ? o.offset : trazenOffset;
  const ukupno = Number.isFinite(o.ukupno) ? o.ukupno : 0;
  const zapisi = uZapise(o.predmeti);
  return {
    zapisi,
    ukupno,
    limit,
    offset,
    prvi: ukupno === 0 ? 0 : offset + 1,
    poslednji: offset + zapisi.length,
    imaSledecu: offset + zapisi.length < ukupno,
    imaPrethodnu: offset > 0,
  };
}
