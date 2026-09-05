/* Vindex V2 — dnevnik.
 *
 * Namerno tanak. Jedina stvarna odgovornost je da se osetljivo NE zapise:
 * nikad token, nikad sadrzaj dokumenta, nikad podaci o predmetu, nikad telo
 * odgovora. U dnevnik ide sta se dogodilo i kog je oblika, ne sta pise unutra.
 */

const PREFIKS = "[v2]";

export function upozori(poruka, detalj) {
  if (detalj === undefined) console.warn(PREFIKS, poruka);
  else console.warn(PREFIKS, poruka, detalj);
}

export function greska(poruka, detalj) {
  if (detalj === undefined) console.error(PREFIKS, poruka);
  else console.error(PREFIKS, poruka, detalj);
}
