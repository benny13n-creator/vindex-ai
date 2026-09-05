/* Vindex V2 — Predmeti, pristup podacima.
 *
 * Jedini poziv u celom Wave 1. Koristi Z014 ugovor:
 *   view=summary  -> osam kolona koje ekran stvarno prikazuje
 *   limit/offset  -> STRANICENJE NA SERVERU
 *   q             -> PRETRAGA NA SERVERU
 *
 * Bez `view=summary` odgovor nosi 17 kolona po predmetu, ukljucujuci polja koja
 * ovaj ekran ne prikazuje. Projekcija nije optimizacija nego granica: ono sto
 * ne stigne u pretrazivac ne moze ni da iscuri iz njega.
 */

import { dohvati } from "../../platform/http.js";
import { uStranu } from "../../domain/predmeti.js";

export const PO_STRANI = 50;

export async function ucitajStranu({ upitTeksta = "", offset = 0, limit = PO_STRANI, signal }) {
  const odgovor = await dohvati("/api/predmeti", {
    upit: { view: "summary", limit, offset, q: upitTeksta.trim() },
    signal,
  });
  return uStranu(odgovor, limit, offset);
}
