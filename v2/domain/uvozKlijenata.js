/* Vindex V2 — uvoz klijenata iz CSV (E10), domenski sloj.
 *
 * Backend (`klijenti/router.py::import_klijenti_csv`) je STVARAN CLIENT
 * import (ime/prezime/firma/email/telefon/adresa/tip, tenant-izolovan
 * preko user_id na svakom redu, max 500 redova, malformed red se
 * preskace uz gresku PO REDU, ne obara ceo uvoz). Ovo NIJE isto sto i
 * routers/csv_import.py (kripto-transakciona CARF/DAC8 klasifikacija) --
 * ta zamena bi bila pogresan capability pod istim imenom.
 *
 * POZNAT JAZ (nije popravljen ovde, dokumentovan): backend NE proverava
 * duplikate (isti email/firma) pre upisa -- ponovljen uvoz istog CSV-a
 * pravi duplirane klijente. Ovo je stvarno, prijavljeno ogranicenje
 * postojeceg backend-a, ne izmisljena pretpostavka -- v. UI napomenu.
 */

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

export function uRezultatUvoza(sirov) {
  const o = sirov || {};
  return {
    kreiran: Number.isFinite(o.kreiran) ? o.kreiran : 0,
    ukupnoPokusano: Number.isFinite(o.ukupno_pokusano) ? o.ukupno_pokusano : 0,
    greske: Array.isArray(o.greske) ? o.greske.map(tekst).filter(Boolean) : [],
  };
}

export function jeCsvFajl(fajl) {
  return !!fajl && /\.csv$/i.test(tekst(fajl.name));
}
