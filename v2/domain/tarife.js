/* Vindex V2 — tarife (F8).
 *
 * ─────────────────────────────────────────────────────────────────────────
 * PROPISANI IZNOS I MOJ IZNOS SU DVA PODATKA
 *
 * `aks_iznos` je iznos iz Advokatske tarife (bodovi × vrednost boda) — to
 * propisuje tarifa, nije moja odluka. `iznos_rsd` je ono sto se stvarno
 * obracunava: AKS iznos, ili moj sopstveni ako sam ga postavio (`is_custom`).
 *
 * Prikazati samo jedan broj znacilo bi da advokat ne moze da zna da li gleda
 * propisanu vrednost ili nesto sto je sam nekada uneo — a to je razlika na
 * koju se poziva pred klijentom. Zato oba ostaju odvojena polja.
 * ─────────────────────────────────────────────────────────────────────────
 *
 * PODRAZUMEVANA SATNICA NIJE MOJA SATNICA. `source: "default"` znaci da je
 * broj pretpostavka sistema, ne izbor advokata. Prikazati je kao njegovu
 * znacilo bi da naplacuje po iznosu koji nikada nije izabrao.
 */

import { dinar, broj } from "./naplata.js";

function tekst(v) {
  return String(v == null ? "" : v).trim();
}

function ceoBroj(v) {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

export function uSatnicu(sirov) {
  const o = sirov || {};
  return {
    iznos: dinar(o.tarifa_po_satu),
    iznosBroj: broj(o.tarifa_po_satu),
    // Mora biti izricito „custom". Nepoznat izvor se tretira kao NE-moj:
    // fail-closed, jer je pogresno tvrditi da je advokat izabrao iznos.
    sopstvena: tekst(o.source) === "custom",
    izvor: tekst(o.source),
  };
}

export function uStavkuTarife(sirov) {
  const s = sirov || {};
  return {
    sifra: tekst(s.sifra),
    naziv: tekst(s.naziv),
    kategorija: tekst(s.kategorija),
    bodovi: ceoBroj(s.bodovi),
    // Ono sto se obracunava.
    iznos: dinar(s.iznos_rsd),
    iznosBroj: broj(s.iznos_rsd),
    // Ono sto propisuje Advokatska tarifa — prikazuje se UVEK.
    aks: dinar(s.aks_iznos),
    aksBroj: broj(s.aks_iznos),
    // Mora biti izricito `true`. Nepoznato se ne proglasava mojom izmenom.
    moja: s.is_custom === true,
  };
}

export function uStavkeTarife(sirov) {
  const o = sirov || {};
  const svi = (Array.isArray(o.stavke) ? o.stavke : [])
    .map(uStavkuTarife)
    .filter(x => x.sifra);
  return {
    svi,
    mojih: svi.filter(x => x.moja).length,
    bodRsd: broj(o.bod_rsd),
  };
}

/**
 * Iznos se proverava PRE poziva. Server prihvata `ge=0`, ali prazno polje i
 * tekst nisu iznos, a advokat treba recenicu koja kaze sta da ispravi umesto
 * 422 sa servera.
 */
export function nedostaciIznosa(v) {
  const s = tekst(v).replace(/\s/g, "").replace(",", ".");
  if (!s) return ["Unesite iznos."];
  if (!/^\d+(\.\d+)?$/.test(s)) return ["Iznos mora biti broj."];
  const n = Number(s);
  if (!Number.isFinite(n)) return ["Iznos mora biti broj."];
  if (n <= 0) return ["Iznos mora biti veći od nule."];
  if (n > 1000000) return ["Iznos je veći od dozvoljenog (1.000.000)."];
  return [];
}
