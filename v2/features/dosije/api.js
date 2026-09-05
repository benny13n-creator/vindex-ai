/* Vindex V2 — Dosije, pristup podacima.
 *
 * Jezgro Dosijea dolazi iz JEDNOG poziva. `/api/predmeti/{id}` vec vraca
 * predmet, dokumente, hronologiju, beleske, istoriju, komentare i povezane
 * klijente — pa taj deo ekrana ima jedno stanje ucitavanja, ne sedam.
 *
 * Tri izvora su DODATNA i nisu obavezna: spremnost, zadaci i rocista. Idu
 * kroz `allSettled` jer pad bilo kog od njih ne sme da obori Dosije: advokat
 * koji ne moze da vidi zadatke ne sme zbog toga da izgubi i spise i rokove.
 * Svaki pali deo nosi svoju zastavicu, pa ekran moze da kaze „nije ucitano"
 * umesto da prikaze prazno i time slaze da nicega nema.
 */

import { dohvati } from "../../platform/http.js";
import { jePrekid } from "../../platform/errors.js";
import { sastaviDosije } from "../../domain/dosije.js";

export async function ucitajDosije(predmetId, { signal } = {}) {
  const id = encodeURIComponent(predmetId);
  const [d, h, z, r] = await Promise.allSettled([
    dohvati(`/api/predmeti/${id}`, { signal }),
    dohvati(`/api/predmeti/${id}/health`, { signal }),
    dohvati(`/api/zadaci/predmet/${id}`, { signal }),
    dohvati("/api/rocista", { upit: { predmet_id: predmetId }, signal }),
  ]);

  for (const x of [d, h, z, r]) {
    if (x.status === "rejected" && jePrekid(x.reason)) throw x.reason;
  }
  // Predmet je obavezan: bez njega nema Dosijea i greska ide dalje.
  if (d.status === "rejected") throw d.reason;

  return {
    ...sastaviDosije(d.value, h.status === "fulfilled" ? h.value : null),
    spremnostPala: h.status === "rejected",
    zadaci: z.status === "fulfilled" ? (z.value && z.value.zadaci) || [] : [],
    zadaciPali: z.status === "rejected",
    rocista: r.status === "fulfilled" ? (r.value && r.value.rocista) || [] : [],
    rocistaPala: r.status === "rejected",
  };
}

/** Preuzimanje originalnog spisa — Z014 bezbedni ugovor. */
export function putanjaPreuzimanja(predmetId, spisId) {
  return `/api/predmeti/${encodeURIComponent(predmetId)}/dokumenti/${encodeURIComponent(spisId)}/download`;
}
