/* Vindex V2 — obavestenja (H7), domen.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * PRAZAN SPISAK NIJE ISTO STO I NEPROCITAN SPISAK
 *
 * `/notifications` na gresku vraca 200 sa praznim nizom. To je do sada bila
 * TVRDNJA da obavestenja nema, nastala iz pale pretrage. Backend sada uz
 * odgovor salje `procitano_uspesno`; ovaj modul ga trazi IZRICITO kao
 * `true`, jer odsutno polje (stariji server) znaci „ne znam", ne „uspelo je".
 *
 * Kad citanje nije dokazano uspesno, ekran kaze „nije procitano" umesto
 * „nemate obavestenja".
 * ─────────────────────────────────────────────────────────────────────────
 *
 * GRUPA NOSI SVE SVOJE ID-JEVE. Backend spaja vise obavestenja istog tipa u
 * jedan red i uz njega salje `ids`. Oznaciti procitanim samo predstavnika
 * ostavilo bi ostale neprocitane, a spisak bi izgledao procitano jer se
 * ponovo skuplja u istog predstavnika (F21).
 */

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

function ceoBroj(v) {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

/** Prioriteti od najviseg ka najnizem — redosled prikaza. */
export const PRIORITET = Object.freeze({
  high: 3, normal: 2, low: 1, info: 0,
});

export function uObavestenje(sirov) {
  const o = sirov || {};
  // Grupa nosi sve svoje id-jeve; pojedinacan red nosi samo svoj.
  const ids = Array.isArray(o.ids) && o.ids.length
    ? o.ids.map(tekst).filter(Boolean)
    : (tekst(o.id) ? [tekst(o.id)] : []);
  return {
    id: tekst(o.id),
    ids,
    tip: tekst(o.tip),
    naslov: tekst(o.naslov),
    poruka: tekst(o.poruka),
    predmetId: tekst(o.predmet_id),
    prioritet: tekst(o.prioritet) || "info",
    // Mora biti izricito `true`. Odsutno polje nije dokaz da je procitano.
    procitano: o.procitano === true,
    kada: tekst(o.created_at),
    koliko: ceoBroj(o.count) || (ids.length > 1 ? ids.length : null),
  };
}

export function uObavestenja(sirov) {
  const o = sirov || {};
  const svi = (Array.isArray(o.notifications) ? o.notifications : [])
    .map(uObavestenje)
    .filter(x => x.naslov || x.poruka)
    .sort((a, b) => {
      const pa = PRIORITET[a.prioritet] === undefined ? -1 : PRIORITET[a.prioritet];
      const pb = PRIORITET[b.prioritet] === undefined ? -1 : PRIORITET[b.prioritet];
      if (pa !== pb) return pb - pa;
      // Unutar istog prioriteta: najnovije prvo.
      if (a.kada === b.kada) return 0;
      if (!a.kada) return 1;
      if (!b.kada) return -1;
      return a.kada < b.kada ? 1 : -1;
    });

  return {
    svi,
    neprocitani: svi.filter(x => !x.procitano),
    // IZRICITO `true`; sve ostalo je „ne znam".
    procitanoUspesno: o.procitano_uspesno === true,
    ukupno: ceoBroj(o.ukupno),
  };
}

/** Svi id-jevi neprocitanih — sto se salje u `read-group`. */
export function idZaOznacavanje(lista) {
  const out = [];
  for (const x of (Array.isArray(lista) ? lista : [])) {
    if (x && !x.procitano) {
      for (const id of (x.ids || [])) if (id && !out.includes(id)) out.push(id);
    }
  }
  return out;
}
