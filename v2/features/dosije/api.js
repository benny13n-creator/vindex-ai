/* Vindex V2 — Dosije, pristup podacima.
 *
 * Ceo Dosije iz JEDNOG poziva. `/api/predmeti/{id}` vec vraca predmet,
 * dokumente, hronologiju, beleske, istoriju, komentare i povezane klijente —
 * pa nema razloga da ekran ima sedam poziva i sedam stanja ucitavanja.
 *
 * Spremnost je drugi izvor i NIJE obavezna: ako padne, Dosije se i dalje
 * prikazuje, samo bez tog dela. Delimican pad nije prazan ekran.
 */

import { dohvati } from "../../platform/http.js";
import { jePrekid } from "../../platform/errors.js";
import { sastaviDosije } from "../../domain/dosije.js";

export async function ucitajDosije(predmetId, { signal } = {}) {
  const [d, h] = await Promise.allSettled([
    dohvati(`/api/predmeti/${encodeURIComponent(predmetId)}`, { signal }),
    dohvati(`/api/predmeti/${encodeURIComponent(predmetId)}/health`, { signal }),
  ]);

  for (const r of [d, h]) {
    if (r.status === "rejected" && jePrekid(r.reason)) throw r.reason;
  }
  // Predmet je obavezan: bez njega nema Dosijea i greska ide dalje.
  if (d.status === "rejected") throw d.reason;

  const spremnost = h.status === "fulfilled" ? h.value : null;
  return {
    ...sastaviDosije(d.value, spremnost),
    spremnostPala: h.status === "rejected",
  };
}

/** Preuzimanje originalnog spisa — Z014 bezbedni ugovor. */
export function putanjaPreuzimanja(predmetId, spisId) {
  return `/api/predmeti/${encodeURIComponent(predmetId)}/dokumenti/${encodeURIComponent(spisId)}/download`;
}
